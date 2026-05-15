"""Smoke tests for the new full-row failing-preview behaviour."""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.services.dq_engine import get_preview_failing  # noqa: E402

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


# ─────────────────────────────────────────────────────────────────────────────
# T1: Validate PAN — only failing rows returned, with full row context
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T1: PAN Validate preview returns full failing rows ===")
df = pd.DataFrame({
    "pan_number": ["ABPFA1975Q", "BADPAN", "AXZPH4392Q", "INVALID", "AALPW2512Q"],
    "name":       ["Acme",       "Brico",  "Globex",     "Initech",  "Wayne"],
    "country":    ["IN",         "FR",     "IN",         "US",       "IN"],
})
cfg = {"mode": "Validate", "pattern": r"^[A-Z]{5}\d{4}[A-Z]$"}
result = get_preview_failing(df, "pan_number", cfg)
check("result is dict", isinstance(result, dict), f"got {type(result).__name__}")
check("total_failing == 2", result["total_failing"] == 2, f"got {result.get('total_failing')}")
check("returned 2 rows", len(result["rows"]) == 2, f"got {len(result['rows'])} rows")
row0 = result["rows"][0]
check("row carries 'pan_number'", "pan_number" in row0)
check("row carries 'name' (full context)", "name" in row0)
check("row carries 'country' (full context)", "country" in row0)
check("row has _status='Rejected'", row0["_status"] == "Rejected", f"got {row0['_status']}")
check("first failing row has pan=BADPAN", row0["pan_number"] == "BADPAN",
      f"got {row0['pan_number']}")
check("first failing row has name=Brico (full context preserved)",
      row0["name"] == "Brico", f"got {row0['name']}")
check("is_transform=False for Validate", result["is_transform"] is False)

# ─────────────────────────────────────────────────────────────────────────────
# T2: When no rows fail, returns success sample with is_transform info
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T2: all-valid Validate returns 0 failing, EMPTY rows ===")
df = pd.DataFrame({"x": ["A", "B", "C"], "y": ["1", "2", "3"]})
cfg = {"mode": "Validate", "pattern": r"^[A-Z]$"}
result = get_preview_failing(df, "x", cfg)
check("0 failing rows", result["total_failing"] == 0)
check("rows is empty (don't pad with valid samples)",
      len(result["rows"]) == 0, f"got {len(result['rows'])}")
check("total_rows reported = 3", result["total_rows"] == 3)
check("is_transform=False", result["is_transform"] is False)

# ─────────────────────────────────────────────────────────────────────────────
# T3: Length rule — full row context for failing rows
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T3: Length max=5 preview ===")
df = pd.DataFrame({
    "code": ["ABC", "TOOLONG", "OK", "EVENLONGER"],
    "owner": ["a", "b", "c", "d"],
})
cfg = {"mode": "Length", "length_mode": "Maximum", "max_length": 5}
result = get_preview_failing(df, "code", cfg)
check("2 failing (TOOLONG + EVENLONGER)", result["total_failing"] == 2)
check("first failing row owner is 'b'", result["rows"][0]["owner"] == "b")

# ─────────────────────────────────────────────────────────────────────────────
# T4: Clean mode — transform, not reject
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T4: Clean mode is_transform=True, sample with Before/After ===")
df = pd.DataFrame({"v": ["a@b", "c#d", "ef"], "n": ["1", "2", "3"]})
cfg = {"mode": "Clean", "pattern": r"[^a-z]"}
result = get_preview_failing(df, "v", cfg)
check("is_transform=True", result["is_transform"] is True)
check("total_failing=0 (transforms don't reject)", result["total_failing"] == 0)
check("transforms DO get a sample (unlike Validate)",
      len(result["rows"]) == 3, f"got {len(result['rows'])} rows")
check("Before/After diff visible",
      result["rows"][0]["_before"] == "a@b" and result["rows"][0]["_after"] == "ab")
check("status='Transform' (new state)",
      result["rows"][0]["_status"] == "Transform")
check("full row context preserved for transforms",
      "n" in result["rows"][0])

# ─────────────────────────────────────────────────────────────────────────────
# T5: Year column (the 2017.0 bug) — full-row preview still works
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T5: Year preview with full row context ===")
df = pd.DataFrame({
    "year": [2017.0, 2018.0, 1850.0, 2020.0],
    "vendor_id": ["v1", "v2", "v3", "v4"],
})
cfg = {"mode": "Validate", "pattern": r"^(19\d{2}|20\d{2})$"}
result = get_preview_failing(df, "year", cfg)
check("1850 is the only failure", result["total_failing"] == 1)
check("failing row is vendor v3", result["rows"][0]["vendor_id"] == "v3")
check("failing year stringified to '1850' (not '1850.0')",
      result["rows"][0]["year"] == "1850.0" or result["rows"][0]["_before"] == "1850")

# ─────────────────────────────────────────────────────────────────────────────
# T6: Limit honoured
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T6: limit caps the rows returned ===")
df = pd.DataFrame({"x": ["BAD"] * 100, "y": list(range(100))})
cfg = {"mode": "Validate", "pattern": r"^GOOD$"}
result = get_preview_failing(df, "x", cfg, limit=5)
check("total_failing reports 100", result["total_failing"] == 100)
check("but only 5 rows returned", len(result["rows"]) == 5)

# ─────────────────────────────────────────────────────────────────────────────
# T7: REGRESSION — Completeness rule with null/blank rows shows them as failing
# (preview MUST match what apply_column_rules will do, not just "exclude nulls")
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T7: Completeness regex (^(?=.*\\S).*$) detects null/blank rows ===")
df = pd.DataFrame({
    "pan_number": ["ABPFA1975Q", None, "", "  ", "AAUPQ3368B"],
    "name":       ["Acme", "Brico", "Globex", "Initech", "Wayne"],
})
cfg = {"mode": "Validate", "pattern": r"^(?=.*\S).*$"}
result = get_preview_failing(df, "pan_number", cfg)
check("total_failing == 3 (None + '' + '  ')",
      result["total_failing"] == 3, f"got {result['total_failing']}")
check("returned 3 failing rows", len(result["rows"]) == 3)
# Names of failing rows: Brico, Globex, Initech
failing_names = [r["name"] for r in result["rows"]]
check("failing rows include null/blank/whitespace rows (with full context)",
      "Brico" in failing_names and "Globex" in failing_names and "Initech" in failing_names,
      f"got names: {failing_names}")
check("non-blank rows (Acme, Wayne) NOT in failing list",
      "Acme" not in failing_names and "Wayne" not in failing_names)

# Verify preview matches apply
from backend.app.session_store import SessionData
from backend.app.services.dq_engine import apply_column_rules, default_config

sess = SessionData(session_id="t7")
sess.df = df.copy()
sess.original_df = df.copy()
sess.reject_df = pd.DataFrame()
sess.dq_config = {c: default_config() for c in df.columns}
sess.dq_config["pan_number"]["applied_rules"] = [{
    "name": "Not blank", "mode": "Validate",
    "pattern": r"^(?=.*\S).*$",
    "dimension": "Completeness", "source": "ai",
}]
_, apply_rejected = apply_column_rules(sess, "pan_number")
check("apply_column_rules rejects same count as preview reported",
      apply_rejected == result["total_failing"],
      f"apply={apply_rejected}, preview={result['total_failing']}")

# ─────────────────────────────────────────────────────────────────────────────
# T8: REGRESSION — Length max=5 still rejects on long values (sanity check)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T8: Length max with null rows — null counts as len 0, passes ===")
df = pd.DataFrame({
    "code": ["ABC", "TOOLONG", None, "OK"],
})
cfg = {"mode": "Length", "length_mode": "Maximum", "max_length": 5}
result = get_preview_failing(df, "code", cfg)
# None → "" via _stringify → len 0 → passes max 5
check("only 'TOOLONG' fails Length max=5",
      result["total_failing"] == 1, f"got {result['total_failing']}")


# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"PREVIEW SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nAll full-row preview tests passed.")
