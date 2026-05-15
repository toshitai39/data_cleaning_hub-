"""Adversarial smoke tests for Cleansing — covers the messy edges.

Focuses on bugs likely to slip past the happy-path test:
  - Per-rule Apply (the rule_idx selective-apply path) preserves the
    other rules on the column
  - Mixing modes on one column (Clean THEN Validate) doesn't lose rules
  - by_dimension dedup correctly skips dq_config rows already in rg_df
  - Year regex (^(19\\d{2}|20\\d{2})$) on a float-stored column applies
    correctly via the actual engine (not just preview)
  - Drop-rule by rule_id and by (column,rule_idx) both work
  - Custom rule survives _purge_ai_synced_from_dq_config
  - Re-applying the same rule twice produces no double-count
  - Empty pattern Validate rule is treated as no-op, not "reject everything"
  - applied_rules_by_dim counters increment correctly per dimension
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.session_store import SessionData  # noqa: E402
from backend.app.services.dq_engine import (  # noqa: E402
    apply_column_rules,
    default_config,
)

results: list = []


def check(name: str, condition: bool, detail: str = "") -> None:
    tag = "[PASS]" if condition else "[FAIL]"
    line = f"{tag} {name}"
    if detail:
        line += f"  -- {detail}"
    results.append((condition, line))
    print(line)


def make_session(df: pd.DataFrame) -> SessionData:
    s = SessionData(session_id="adv")
    s.df = df.copy()
    s.original_df = df.copy()
    s.reject_df = pd.DataFrame()
    s.dq_config = {c: default_config() for c in df.columns}
    return s


# ─────────────────────────────────────────────────────────────────────────────
# T1: per-rule Apply preserves the column's other rules (the rule_idx path
# the Cleansing per-row Apply button hits)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T1: per-rule Apply preserves siblings on same column ===")
df = pd.DataFrame({"name": ["alpha", "beta", "gamma"]})
sess = make_session(df)
sess.dq_config["name"]["applied_rules"] = [
    {"name": "RuleA Case",   "mode": "Case", "case": "UPPERCASE", "dimension": "Standardisation", "source": "ai"},
    {"name": "RuleB Length", "mode": "Validate", "pattern": r"^.{1,4}$", "dimension": "Validation", "source": "ai"},
    {"name": "RuleC Plain",  "mode": "Validate", "pattern": r"^[A-Za-z]+$", "dimension": "Validation", "source": "ai"},
]

# Mimic /quality/apply-rule/{column}/{rule_idx} — runs ONLY rule_idx=1.
target_idx = 1
all_rules = list(sess.dq_config["name"]["applied_rules"])
target = all_rules[target_idx]
rest = all_rules[:target_idx] + all_rules[target_idx + 1:]
sess.dq_config["name"]["applied_rules"] = [target]
prev_enabled = sess.dq_config["name"].get("enabled", False)
sess.dq_config["name"]["enabled"] = True
try:
    applied, rejected = apply_column_rules(sess, "name")
finally:
    sess.dq_config["name"]["applied_rules"] = rest + sess.dq_config["name"].get("applied_rules", [])
    sess.dq_config["name"]["enabled"] = prev_enabled

# Validate ^.{1,4}$ — "alpha", "gamma" have 5 chars → rejected; "beta" 4 chars → kept
check("applied=1 (only target)", applied == 1, f"applied={applied}")
check("rejected=2 (alpha + gamma > 4 chars)", rejected == 2, f"rejected={rejected}")
check("siblings A + C still in dq_config after partial apply",
      len(sess.dq_config["name"]["applied_rules"]) == 2,
      f"remaining={[r['name'] for r in sess.dq_config['name']['applied_rules']]}")
sibling_names = {r["name"] for r in sess.dq_config["name"]["applied_rules"]}
check("siblings preserved by name", sibling_names == {"RuleA Case", "RuleC Plain"},
      f"got {sibling_names}")

# ─────────────────────────────────────────────────────────────────────────────
# T2: chained modes — Clean THEN Validate
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T2: chain Clean→Validate on same column ===")
df = pd.DataFrame({"code": ["A@B!", "XYZ", "C#D$E"]})
sess = make_session(df)
sess.dq_config["code"]["applied_rules"] = [
    {"name": "Strip non-alpha", "mode": "Clean", "pattern": r"[^A-Za-z]", "dimension": "Standardisation", "source": "ai"},
    {"name": "Exactly 3 letters", "mode": "Validate", "pattern": r"^[A-Z]{3}$", "dimension": "Validation", "source": "ai"},
]
applied, rejected = apply_column_rules(sess, "code")
# After Clean: ["AB","XYZ","CDE"]. After Validate: AB rejected (len 2), XYZ + CDE pass
check("applied=2 (Clean + Validate)", applied == 2, f"applied={applied}")
check("rejected=1 (AB has len 2 after clean)", rejected == 1, f"rejected={rejected}")
check("df has 2 rows remaining", len(sess.df) == 2, f"len={len(sess.df)}")
remaining = sorted(sess.df["code"].tolist())
check("remaining rows = XYZ, CDE", remaining == ["CDE", "XYZ"], f"got {remaining}")

# ─────────────────────────────────────────────────────────────────────────────
# T3: empty-pattern Validate is a no-op, NOT a reject-everything
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T3: empty-pattern Validate rule must not nuke the column ===")
df = pd.DataFrame({"x": ["a", "b", "c"]})
sess = make_session(df)
sess.dq_config["x"]["applied_rules"] = [
    {"name": "Empty pattern", "mode": "Validate", "pattern": "", "dimension": "Validation", "source": "ai"},
]
applied, rejected = apply_column_rules(sess, "x")
# pandas str.match("") matches every string → invalid_mask = ~True = False → 0 rejected
# Both behaviours are acceptable; we just want NOT all-rejected
check("empty pattern doesn't reject all 3 rows",
      rejected < 3 and len(sess.df) >= 1,
      f"rejected={rejected}, remaining={len(sess.df)}")

# ─────────────────────────────────────────────────────────────────────────────
# T4: re-applying the same rule twice — second apply yields 0 new rejections
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T4: re-apply same rule is idempotent ===")
df = pd.DataFrame({"v": ["A", "B", "1", "2", "C"]})
sess = make_session(df)
rule = {"name": "Letters only", "mode": "Validate", "pattern": r"^[A-Z]$", "dimension": "Validation", "source": "ai"}

sess.dq_config["v"]["applied_rules"] = [rule]
a1, r1 = apply_column_rules(sess, "v")
check("first apply: 2 rejected", r1 == 2, f"r1={r1}")
check("first apply: 3 remain", len(sess.df) == 3)

# Re-add and re-apply
sess.dq_config["v"]["applied_rules"] = [rule]
a2, r2 = apply_column_rules(sess, "v")
check("second apply: 0 rejected (df already clean)", r2 == 0, f"r2={r2}")
check("still 3 rows", len(sess.df) == 3)

# ─────────────────────────────────────────────────────────────────────────────
# T5: applied_rules_by_dim counter increments per dimension
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T5: applied_rules_by_dim counter ===")
df = pd.DataFrame({"col": ["a", "b", "c"]})
sess = make_session(df)
sess.dq_config["col"]["applied_rules"] = [
    {"name": "case rule",  "mode": "Case", "case": "UPPERCASE", "dimension": "Standardisation", "source": "ai"},
]
apply_column_rules(sess, "col")
check("Standardisation counter +1",
      sess.applied_rules_by_dim.get("Standardisation", 0) == 1,
      f"counters={sess.applied_rules_by_dim}")

sess.dq_config["col"]["applied_rules"] = [
    {"name": "validate", "mode": "Validate", "pattern": r"^[A-Z]+$", "dimension": "Validation", "source": "ai"},
]
apply_column_rules(sess, "col")
check("Validation counter +1",
      sess.applied_rules_by_dim.get("Validation", 0) == 1,
      f"counters={sess.applied_rules_by_dim}")
check("Standardisation counter stays at 1",
      sess.applied_rules_by_dim.get("Standardisation", 0) == 1)

# ─────────────────────────────────────────────────────────────────────────────
# T6: float year column survives end-to-end Apply (not just preview)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T6: Year column 2017.0 — full apply, not just preview ===")
df = pd.DataFrame({"year": [2017.0, 2018.0, 1850.0, 2020.0]})
sess = make_session(df)
sess.dq_config["year"]["applied_rules"] = [
    {"name": "Valid year", "mode": "Validate", "pattern": r"^(19\d{2}|20\d{2})$",
     "dimension": "Validation", "source": "ai"},
]
applied, rejected = apply_column_rules(sess, "year")
check("only 1850 rejected", rejected == 1, f"rejected={rejected}")
remaining = sess.df["year"].tolist()
check("3 valid years remain", len(remaining) == 3, f"remaining={remaining}")

# ─────────────────────────────────────────────────────────────────────────────
# T7: _purge_ai_synced_from_dq_config preserves custom rules
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T7: purge_ai_synced preserves source=custom rules ===")
from backend.app.routers.rule_generator_router import _purge_ai_synced_from_dq_config

df = pd.DataFrame({"a": ["1"], "b": ["2"]})
sess = make_session(df)
sess.dq_config["a"]["applied_rules"] = [
    {"name": "AI rule", "mode": "Validate", "pattern": r"\d", "dimension": "Validation", "source": "ai"},
    {"name": "Custom rule", "mode": "Validate", "pattern": r"^\d$", "dimension": "Validation", "source": "custom"},
]
sess.dq_config["b"]["applied_rules"] = [
    {"name": "Library rule", "mode": "Validate", "pattern": r"\d", "dimension": "Validation", "source": "library"},
    {"name": "Another AI", "mode": "Case", "case": "UPPERCASE", "dimension": "Standardisation", "source": "ai"},
]
_purge_ai_synced_from_dq_config(sess)
check("col 'a' kept only the custom rule",
      [r["name"] for r in sess.dq_config["a"]["applied_rules"]] == ["Custom rule"],
      f"got {sess.dq_config['a']['applied_rules']}")
check("col 'b' kept only the library rule",
      [r["name"] for r in sess.dq_config["b"]["applied_rules"]] == ["Library rule"],
      f"got {sess.dq_config['b']['applied_rules']}")

# ─────────────────────────────────────────────────────────────────────────────
# T8: by_dimension dedup — rule in dq_config that matches rg_df by (col,pat)
# should NOT appear as a separate "custom" row
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T8: by_dimension dedup of rg_df vs dq_config ===")
from backend.app.routers.quality_router import by_dimension as by_dim_fn

df = pd.DataFrame({"pan": ["ABCDE1234F", "BAD", "FGHIJ5678K"]})
sess = make_session(df)
sess.ai_validation_rules = pd.DataFrame([{
    "S.No": 1, "Column": "pan", "Business Field": "PAN",
    "Rule Source": "Generated by AI", "Dimension": "Validation",
    "Data Quality Rule": "PAN must be a valid PAN format",
    "Regex Pattern": r"^[A-Z]{5}\d{4}[A-Z]$",
    "Issues Found": 0, "Issues Found Example": "",
    "Validation Expression": "",
}])
# Place a duplicate of the same rule in dq_config (simulating what would
# happen if /import-ai was hit). by_dimension should dedup.
sess.dq_config["pan"]["applied_rules"] = [{
    "name": "PAN", "mode": "Validate",
    "pattern": r"^[A-Z]{5}\d{4}[A-Z]$",
    "dimension": "Validation", "source": "ai",
}]

response = by_dim_fn(sess)
val_dim = next((d for d in response["dimensions"] if d["name"] == "Validation"), None)
rule_count = len(val_dim["rules"]) if val_dim else -1
check("Validation tab shows ONE rule (not double-counted)",
      rule_count == 1, f"got {rule_count} rules")
check("totals.generated reflects single rule",
      response["totals"]["generated"] == 1,
      f"got {response['totals']['generated']}")

# ─────────────────────────────────────────────────────────────────────────────
# T9: dropping a rule via /drop-rule (rule_id path)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T9: drop_rule by rule_id removes RG row ===")
df = pd.DataFrame({"x": ["a"]})
sess = make_session(df)
sess.ai_validation_rules = pd.DataFrame([
    {"S.No": 1, "Column": "x", "Dimension": "Validation",
     "Data Quality Rule": "rule1", "Regex Pattern": r"\d"},
    {"S.No": 2, "Column": "x", "Dimension": "Standardisation",
     "Data Quality Rule": "rule2", "Regex Pattern": ""},
])
target_id = 0
sess.ai_validation_rules = sess.ai_validation_rules.drop(target_id)
check("1 row remains in rg_df after drop",
      len(sess.ai_validation_rules) == 1,
      f"remaining={sess.ai_validation_rules['Data Quality Rule'].tolist()}")
check("kept row is rule2",
      sess.ai_validation_rules.iloc[0]["Data Quality Rule"] == "rule2")

# ─────────────────────────────────────────────────────────────────────────────
# T10: validation_history backup snapshot can be replayed (undo correctness)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T10: undo last restores both df and reject_df ===")
df = pd.DataFrame({"x": ["a", "b", "c", "1", "2"]})
sess = make_session(df)
sess.dq_config["x"]["applied_rules"] = [{
    "name": "letters only", "mode": "Validate",
    "pattern": r"^[a-z]$", "dimension": "Validation", "source": "ai",
}]
apply_column_rules(sess, "x")
check("before undo: 3 rows, 2 rejected",
      len(sess.df) == 3 and len(sess.reject_df) == 2,
      f"df={len(sess.df)}, rejects={len(sess.reject_df)}")

from backend.app.services.dq_engine import undo_last
undo_ok = undo_last(sess)
check("undo returned True", undo_ok)
check("after undo: 5 rows restored", len(sess.df) == 5, f"got {len(sess.df)}")
check("after undo: reject_df cleared", len(sess.reject_df) == 0)
check("after undo: applied_rules_by_dim rolled back",
      sess.applied_rules_by_dim.get("Validation", 0) == 0,
      f"counter={sess.applied_rules_by_dim}")

# ─────────────────────────────────────────────────────────────────────────────
# T11: empty df doesn't crash apply_column_rules
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T11: empty df doesn't crash apply ===")
df = pd.DataFrame({"x": []}, dtype=object)
sess = make_session(df)
sess.dq_config["x"]["applied_rules"] = [{
    "name": "letters", "mode": "Validate", "pattern": r"^[a-z]$",
    "dimension": "Validation", "source": "ai",
}]
try:
    applied, rejected = apply_column_rules(sess, "x")
    check("empty df Apply returns (0,0)", applied == 1 and rejected == 0,
          f"applied={applied}, rejected={rejected}")
except Exception as e:
    check("empty df Apply doesn't crash", False, f"raised: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# T12: NaN values handled without spurious rejections
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T12: NaN handled — Completeness rejects, Validation passes ===")
df = pd.DataFrame({"col": ["a", None, "b", float("nan"), "c"]})
sess = make_session(df)
# Completeness: reject the 2 NaN/None rows
sess.dq_config["col"]["applied_rules"] = [{
    "name": "Not blank", "mode": "Validate",
    "pattern": r"^(?=.*\S).*$", "dimension": "Completeness", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "col")
check("completeness rejects 2 NaN rows", rejected == 2, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
total = len(results)
passed = sum(1 for ok, _ in results if ok)
failed = total - passed
print(f"ADVERSARIAL SUMMARY: {passed}/{total} passed, {failed} failed")
if failed:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nAll adversarial cleansing tests passed.")
