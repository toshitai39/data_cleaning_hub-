"""End-to-end smoke tests for the Cleansing module.

Exercises engine + router-level operations against a synthetic dataset:
  1. Numeric float normalisation (year 2017.0 → "2017")
  2. Max-length regex inference ("maximum length of 255")
  3. Completeness rule (drop blanks)
  4. Validation regex (PAN format)
  5. Clean / Replace / Case modes
  6. Lifecycle status pipeline (actionable / passed / blocked_empty /
     blocked_incomplete / invalid / unmapped / multi_cde)
  7. Custom rule add → preview → apply
  8. Reset all
  9. Drop unmapped
"""
from __future__ import annotations

import re
import sys
import traceback
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.session_store import SessionData  # noqa: E402
from backend.app.services.dq_engine import (  # noqa: E402
    _stringify,
    apply_column_rules,
    default_config,
    get_preview,
)
from features.rule_generator.engine import (  # noqa: E402
    _extract_max_chars,
    infer_regex_pattern_from_rule,
)

PASS = "[PASS]"
FAIL = "[FAIL]"

results: list = []


def check(name: str, condition: bool, detail: str = "") -> None:
    tag = PASS if condition else FAIL
    line = f"{tag} {name}"
    if detail:
        line += f"  -- {detail}"
    results.append((condition, line))
    print(line)


def make_session(df: pd.DataFrame) -> SessionData:
    sess = SessionData(session_id="smoke")
    sess.df = df.copy()
    sess.original_df = df.copy()
    sess.reject_df = pd.DataFrame()
    sess.dq_config = {c: default_config() for c in df.columns}
    return sess


# ─────────────────────────────────────────────────────────────────────────────
# TEST 1: _stringify normalises float-stored integers
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 1: _stringify (numeric float → 'int' string) ===")
s = pd.Series([2017.0, 2018.0, 2019.5, None])
out = _stringify(s).tolist()
check("2017.0 -> '2017'", out[0] == "2017", f"got {out[0]!r}")
check("2018.0 -> '2018'", out[1] == "2018", f"got {out[1]!r}")
check("2019.5 stays '2019.5'", out[2] == "2019.5", f"got {out[2]!r}")
check("None -> '' ", out[3] == "", f"got {out[3]!r}")
str_series = pd.Series(["hello", "world"])
out2 = _stringify(str_series).tolist()
check("string series passthrough", out2 == ["hello", "world"], f"got {out2!r}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 2: regex inference for max-length rules
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 2: regex inference (max-length variants) ===")
cases = [
    ("Company Name must be a string with a maximum length of 255 characters", "^.{0,255}$"),
    ("Field must be max 50 characters", "^.{0,50}$"),
    ("Value must be up to 100 characters", "^.{0,100}$"),
    ("Description must be no more than 500 characters", "^.{0,500}$"),
    ("Comment length should not exceed 1000", "^.{0,1000}$"),
    ("Address must be at most 200 characters", "^.{0,200}$"),
]
for rule, expected in cases:
    got = infer_regex_pattern_from_rule("Validation", rule)
    check(f"infer regex for: {rule[:60]}", got == expected, f"got {got!r} expected {expected!r}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 3: regex inference for exact-length rules (must still work)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 3: regex inference (exact-length, not max) ===")
got = infer_regex_pattern_from_rule("Validation", "PAN must be a string with a length of 10 characters")
check("exact-length 10", got == "^.{10}$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Validation", "Code must be 6 characters long")
check("exact-length 6 ('N chars long')", got == "^.{6}$", f"got {got!r}")

# Edge case: 'maximum' should NOT match exact-length even if 'length of N characters' is present
got = infer_regex_pattern_from_rule(
    "Validation", "Name has length of 50 characters at maximum"
)
check("'at maximum' overrides exact-length", got == "^.{0,50}$", f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 4: get_preview against numeric column (Year 2017.0 should be Valid)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 4: preview YEAR column with regex ^(19\\d{2}|20\\d{2})$ ===")
df = pd.DataFrame({"year_of_establishment": [2017.0, 2018.0, 2019.0, 1850.0, None]})
cfg = {
    "mode": "Validate",
    "pattern": r"^(19\d{2}|20\d{2})$",
    "replace": "", "case": "UPPERCASE",
    "length_mode": "Exact", "min_length": 0, "max_length": 50, "exact_length": 10,
}
rows = get_preview(df, "year_of_establishment", cfg)
statuses = [r["Status"] for r in rows]
check("preview returned 4 rows (None dropped)", len(rows) == 4, f"got {len(rows)} rows")
check("2017.0 is Valid", rows[0]["Status"] == "Valid",
      f"row[0]={rows[0]}")
check("2018.0 is Valid", rows[1]["Status"] == "Valid",
      f"row[1]={rows[1]}")
check("1850.0 is Rejected", rows[3]["Status"] == "Rejected",
      f"row[3]={rows[3]}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 5: apply_column_rules — Validate mode rejects bad rows
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 5: apply Validate PAN rule ===")
df_pan = pd.DataFrame({
    "pan_number": ["ABCDE1234F", "INVALIDPAN", "FGHIJ5678K", "XYZAB9999Z"],
})
sess = make_session(df_pan)
sess.dq_config["pan_number"]["applied_rules"] = [{
    "name": "PAN format",
    "mode": "Validate",
    "pattern": r"^[A-Z]{5}\d{4}[A-Z]$",
    "dimension": "Validation",
    "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "pan_number")
check("1 rule applied", applied == 1, f"applied={applied}")
check("1 row rejected (INVALIDPAN)", rejected == 1, f"rejected={rejected}")
check("3 rows remaining in df", len(sess.df) == 3, f"len(df)={len(sess.df)}")
check("rejected row preserved with reason",
      "Rejection_Reason" in sess.reject_df.columns and len(sess.reject_df) == 1,
      f"reject_df={sess.reject_df.to_dict()}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 6: apply Validate max-length rule (the buggy ^.{255}$ case)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 6: apply max-length rule with corrected ^.{0,255}$ ===")
df_name = pd.DataFrame({
    "name": ["Short", "MediumName", "X" * 100, "X" * 300, "OK"],
})
sess = make_session(df_name)
sess.dq_config["name"]["applied_rules"] = [{
    "name": "Name max 255",
    "mode": "Validate",
    "pattern": r"^.{0,255}$",
    "dimension": "Validation",
    "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "name")
check("1 rule applied", applied == 1, f"applied={applied}")
check("only the 300-char row rejected", rejected == 1, f"rejected={rejected}")
check("4 rows remain", len(sess.df) == 4, f"len(df)={len(sess.df)}")

# Now test the BUGGY pattern that the old code produced to prove our fix matters
print("\n=== TEST 6b: confirm the OLD pattern ^.{255}$ would have nuked everything ===")
df_name2 = pd.DataFrame({"name": ["Short", "MediumName", "OK"]})
sess2 = make_session(df_name2)
sess2.dq_config["name"]["applied_rules"] = [{
    "name": "Name (old buggy)",
    "mode": "Validate",
    "pattern": r"^.{255}$",   # the OLD bad regex
    "dimension": "Validation",
    "source": "ai",
}]
applied, rejected = apply_column_rules(sess2, "name")
check("old pattern rejects ALL 3 rows (proving the bug existed)",
      rejected == 3, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 7: Clean mode strips chars
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 7: Clean mode (strip special chars) ===")
df_c = pd.DataFrame({"code": ["A@B!", "C#D$", "PLAIN"]})
sess = make_session(df_c)
sess.dq_config["code"]["applied_rules"] = [{
    "name": "Strip special",
    "mode": "Clean",
    "pattern": r"[^A-Za-z]",
    "dimension": "Standardisation",
    "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "code")
got = sess.df["code"].tolist()
check("Clean produced AB,CD,PLAIN", got == ["AB", "CD", "PLAIN"], f"got {got!r}")
check("Clean rejects 0 rows", rejected == 0)

# ─────────────────────────────────────────────────────────────────────────────
# TEST 8: Replace mode
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 8: Replace mode ===")
df_r = pd.DataFrame({"key": ["foo_bar", "baz_qux"]})
sess = make_session(df_r)
sess.dq_config["key"]["applied_rules"] = [{
    "name": "Underscore to space",
    "mode": "Replace",
    "pattern": "_",
    "replace": " ",
    "dimension": "Standardisation",
    "source": "ai",
}]
apply_column_rules(sess, "key")
got = sess.df["key"].tolist()
check("Replace produced 'foo bar','baz qux'",
      got == ["foo bar", "baz qux"], f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 9: Case mode
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 9: Case UPPERCASE ===")
df_case = pd.DataFrame({"country": ["india", "Usa", "uk"]})
sess = make_session(df_case)
sess.dq_config["country"]["applied_rules"] = [{
    "name": "To upper",
    "mode": "Case",
    "pattern": "",
    "case": "UPPERCASE",
    "dimension": "Standardisation",
    "source": "ai",
}]
apply_column_rules(sess, "country")
got = sess.df["country"].tolist()
check("Case produced INDIA,USA,UK", got == ["INDIA", "USA", "UK"], f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 10: Lifecycle status — by_dimension pipeline
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 10: lifecycle status pipeline ===")
from backend.app.routers.quality_router import _evaluate_rule_status

df_lc = pd.DataFrame({
    "filled":     ["a", "b", "c", "d", "e", "f", "g", "h", "i", "j"],
    "empty_col":  ["", "", "", "", "", "", "", "", "", ""],
    "sparse":     ["x", "", "", "", "", "", "", "", "", ""],   # 10% filled
})
col_health = {
    "filled":    {"non_empty": 10, "total": 10, "fill_rate": 1.0,  "is_empty": False},
    "empty_col": {"non_empty": 0,  "total": 10, "fill_rate": 0.0,  "is_empty": True},
    "sparse":    {"non_empty": 1,  "total": 10, "fill_rate": 0.1,  "is_empty": False},
}
real_cols = set(df_lc.columns)
empty_set = {"empty_col"}

# Case A: column 100% empty + Validation dim → blocked_empty
rg_row = pd.Series({
    "Column": "empty_col",
    "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "value must be uppercase",
    "Regex Pattern": "^[A-Z]+$",
})
entry = _evaluate_rule_status(rg_row, 0, df_lc, col_health, real_cols, empty_set, set(), {})
check("100%-empty col → blocked_empty", entry["status"] == "blocked_empty",
      f"got {entry['status']}, reason={entry.get('reason')}")

# Case B: column 10% filled + Validation dim → blocked_incomplete
rg_row = pd.Series({
    "Column": "sparse",
    "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "value must be uppercase",
    "Regex Pattern": "^[A-Z]+$",
})
entry = _evaluate_rule_status(rg_row, 1, df_lc, col_health, real_cols, empty_set, set(), {})
check("10%-filled col → blocked_incomplete", entry["status"] == "blocked_incomplete",
      f"got {entry['status']}")

# Case C: column missing → invalid
rg_row = pd.Series({
    "Column": "ghost_col",
    "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "value must be uppercase",
    "Regex Pattern": "^[A-Z]+$",
})
entry = _evaluate_rule_status(rg_row, 2, df_lc, col_health, real_cols, empty_set, set(), {})
check("missing col → invalid", entry["status"] == "invalid",
      f"got {entry['status']}")

# Case D: multi-CDE → multi_cde
rg_row = pd.Series({
    "Column": "filled + sparse",
    "Columns": "filled, sparse",
    "Dimension": "Cross-field Validation",
    "Data Quality Rule": "filled and sparse must agree",
    "Regex Pattern": "",
})
entry = _evaluate_rule_status(rg_row, 3, df_lc, col_health, real_cols, empty_set, set(), {})
check("multi-column → multi_cde", entry["status"] == "multi_cde",
      f"got {entry['status']}")

# Case E: column ok, rule has no executable pattern → unmapped
rg_row = pd.Series({
    "Column": "filled",
    "Columns": "",
    "Dimension": "Accuracy",
    "Data Quality Rule": "filled must accurately reflect the real-world entity",
    "Regex Pattern": "",
})
entry = _evaluate_rule_status(rg_row, 4, df_lc, col_health, real_cols, empty_set, set(), {})
check("Accuracy w/o regex → unmapped", entry["status"] == "unmapped",
      f"got {entry['status']}, reason={entry.get('reason')}")

# Case F: column ok, rule executable, no failures → passed
rg_row = pd.Series({
    "Column": "filled",
    "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "value must be a lowercase letter",
    "Regex Pattern": r"^[a-z]$",
})
entry = _evaluate_rule_status(rg_row, 5, df_lc, col_health, real_cols, empty_set, set(), {})
check("all rows satisfy rule → passed", entry["status"] == "passed",
      f"got {entry['status']}, failure_count={entry['failure_count']}")

# Case G: column ok, rule executable, has failures → actionable
df_x = pd.DataFrame({"filled": ["a", "b", "1", "2", "c", "d", "e", "f", "g", "h"]})
ch_x = {"filled": {"non_empty": 10, "total": 10, "fill_rate": 1.0, "is_empty": False}}
rg_row = pd.Series({
    "Column": "filled",
    "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "value must be a lowercase letter",
    "Regex Pattern": r"^[a-z]$",
})
entry = _evaluate_rule_status(rg_row, 6, df_x, ch_x, {"filled"}, set(), set(), {})
check("2 violating rows → actionable, failure_count=2",
      entry["status"] == "actionable" and entry["failure_count"] == 2,
      f"got {entry['status']}, fc={entry['failure_count']}")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 11: Custom rule round-trip
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 11: custom rule add → apply ===")
df_custom = pd.DataFrame({"email": ["good@x.com", "bad", "ok@y.io"]})
sess = make_session(df_custom)
# Simulate the "Add Custom Rule" flow: append to dq_config with source=custom
sess.dq_config["email"]["applied_rules"].append({
    "name": "Email format (custom)",
    "mode": "Validate",
    "pattern": r"^[^@\s]+@[^@\s]+\.[a-z]+$",
    "dimension": "Validation",
    "source": "custom",
})
applied, rejected = apply_column_rules(sess, "email")
check("custom rule applied", applied == 1, f"applied={applied}")
check("1 row rejected (bad)", rejected == 1, f"rejected={rejected}")
check("source='custom' preserved on rejected row history",
      sess.validation_history[-1]["backup_applied_rules"][0]["source"] == "custom")

# ─────────────────────────────────────────────────────────────────────────────
# TEST 12: Reset-cleansing
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 12: reset_cleansing restores original df ===")
df_reset = pd.DataFrame({"x": ["A", "B", "C", "D"]})
sess = make_session(df_reset)
sess.dq_config["x"]["applied_rules"] = [{
    "name": "validate single letter",
    "mode": "Validate",
    "pattern": r"^[ABC]$",
    "dimension": "Validation",
    "source": "ai",
}]
apply_column_rules(sess, "x")
check("after apply 3 rows remain", len(sess.df) == 3, f"len(df)={len(sess.df)}")

# Reproduce what /quality/reset-cleansing does
sess.df = sess.original_df.copy()
sess.reject_df = pd.DataFrame()
sess.validation_history = []
sess.applied_rules_by_dim = {}
check("reset restores 4 rows", len(sess.df) == 4, f"len(df)={len(sess.df)}")
check("reset clears reject_df", len(sess.reject_df) == 0)
check("reset clears history", len(sess.validation_history) == 0)

# ─────────────────────────────────────────────────────────────────────────────
# TEST 13: drop_unmapped equivalent
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== TEST 13: drop_unmapped removes unmapped AI rules ===")
from backend.app.services.dq_rg_mapping import rg_row_to_applied_rule

rg_df = pd.DataFrame([
    {"Column": "x", "Dimension": "Validation",  "Data Quality Rule": "x must be a single letter",            "Regex Pattern": r"^[A-Z]$"},
    {"Column": "y", "Dimension": "Accuracy",    "Data Quality Rule": "y must reflect the real-world entity", "Regex Pattern": ""},
    {"Column": "z", "Dimension": "Completeness","Data Quality Rule": "z must not be blank",                  "Regex Pattern": r"^(?=.*\S).*$"},
])
sess = SessionData(session_id="smoke")
sess.df = pd.DataFrame({"x": ["A"], "y": ["1"], "z": ["v"]})
sess.ai_validation_rules = rg_df

# Reproduce what /quality/drop-unmapped does
keep_mask = []
for _, row in sess.ai_validation_rules.iterrows():
    mapped = rg_row_to_applied_rule(row)
    keep_mask.append(bool(mapped))
dropped = len(sess.ai_validation_rules) - sum(keep_mask)
sess.ai_validation_rules = sess.ai_validation_rules[keep_mask].reset_index(drop=True)
check("dropped 1 unmapped rule (y)", dropped == 1, f"dropped={dropped}")
check("2 rules remain", len(sess.ai_validation_rules) == 2,
      f"remaining={sess.ai_validation_rules['Column'].tolist()}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
total = len(results)
passed = sum(1 for ok, _ in results if ok)
failed = total - passed
print(f"SUMMARY: {passed}/{total} passed, {failed} failed")
if failed:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nAll cleansing smoke tests passed.")
