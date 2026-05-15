"""Material Master smoke test — joined-view stream (Material × plant).

Different shape from Customer / Vendor entity masters:
  - material_id REPEATS (same material, different plants)
  - composite key is (material_id, plant)
  - numeric fields: standard_price, weights, volumes
  - SAP-style enum codes: material_type (FERT/HALB/ROH/…)
  - EAN-13 / UPC-12 barcodes
  - ABC indicator (A/B/C)
  - Procurement type single-letter codes (F / E / X)
  - Dates: created_on, last_changed_on

Tests exercise every common rule shape against material-domain text so
any field-name-coupling or stream-specific regression surfaces here.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.session_store import SessionData  # noqa: E402
from backend.app.services.dq_engine import (  # noqa: E402
    apply_column_rules, default_config, get_preview_failing,
)
from backend.app.routers.quality_router import _evaluate_rule_status  # noqa: E402
from features.rule_generator.engine import (  # noqa: E402
    _extract_allowed_values, infer_regex_pattern_from_rule,
)

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


def material_dataset() -> pd.DataFrame:
    """Synthetic Material × plant master with deliberate quality issues."""
    return pd.DataFrame({
        # material_id REPEATS across plants — this is normal for joined view
        "material_id": ["MAT-000001", "MAT-000001", "MAT-000002", "MAT-000002",
                        "MAT-000003", "MAT-000003", "MAT-000004", "MAT-000005",
                        "INVALID_ID",  # bad format
                        "MAT-000007"],
        "plant":       ["P001", "P002", "P001", "P003",
                        "P001", "P002", "P001", "P003",
                        "P001", "P002"],
        "material_description": [
            "Bearing housing", "Bearing housing", "Hydraulic pump",
            "Hydraulic pump", "Electric motor", "Electric motor",
            "",  # blank
            None,  # null
            "Test material",
            "Toolset"],
        "base_unit_of_measure": ["EA", "EA", "PC", "PC",
                                 "EA", "EA", "KG", "EA", "EA", "BOX"],
        "material_group": ["MG-001", "MG-001", "MG-002", "MG-002",
                           "MG-003", "MG-003", "MG-004", "MG-005",
                           "INVALID",  # bad format
                           "MG-007"],
        # material_type — SAP standard codes: FERT/HALB/ROH/HIBE/DIEN
        "material_type": ["FERT", "FERT", "HALB", "HALB",
                          "FERT", "FERT", "ROH", "HIBE",
                          "ZZZZ",  # not a valid material type
                          "DIEN"],
        # standard_price — must be a non-negative number with up to 2 decimals
        "standard_price": ["125.50", "125.50", "899.99", "899.99",
                           "2500.00", "2500.00", "-5.00",   # negative invalid
                           "abc",     # non-numeric
                           "10.999",  # too many decimals
                           "75.25"],
        # gross_weight — kg, numeric
        "gross_weight": ["2.5", "2.5", "15.0", "15.0",
                         "45.5", "45.5", "0.5", "1.2",
                         "0",     # zero allowed but borderline
                         "8.75"],
        "weight_unit": ["KG", "KG", "KG", "KG",
                        "KG", "KG", "KG", "KG", "POUND",  # non-ISO
                        "KG"],
        # ean_upc — EAN-13 (13 digits) or UPC-A (12 digits)
        "ean_upc": ["8901234567890", "8901234567890", "012345678905",
                    "012345678905", "8907890123456", "8907890123456",
                    "999",  # too short
                    "", None,
                    "0123456789012"],
        # abc_indicator — strictly A / B / C
        "abc_indicator": ["A", "A", "B", "B",
                          "A", "A", "C", "B",
                          "D",   # invalid
                          "A"],
        # procurement_type — F (external) / E (in-house) / X (both)
        "procurement_type": ["F", "F", "E", "E",
                             "E", "E", "F", "F",
                             "Z",   # invalid
                             "X"],
        # created_on — YYYY-MM-DD
        "created_on": ["2023-01-15", "2023-01-15", "2023-02-20",
                       "2023-02-20", "2022-11-30", "2022-11-30",
                       "2024-03-10",
                       "2024/05/22",  # wrong format
                       "2024-06-01", "2024-07-14"],
    })


def make_session(df: pd.DataFrame) -> SessionData:
    s = SessionData(session_id="material")
    s.df = df.copy()
    s.original_df = df.copy()
    s.reject_df = pd.DataFrame()
    s.dq_config = {c: default_config() for c in df.columns}
    return s


# ─────────────────────────────────────────────────────────────────────────────
# M1: material_id format (MAT-NNNNNN) — repeating IDs are OK across rows
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M1: material_id format ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["material_id"]["applied_rules"] = [{
    "name": "Material ID format", "mode": "Validate",
    "pattern": r"^MAT-\d{6}$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "material_id")
check("rejected the INVALID_ID row", rejected == 1, f"rejected={rejected}")
check("9 rows remain (repeated material_ids preserved)",
      len(sess.df) == 9, f"len={len(sess.df)}")

# ─────────────────────────────────────────────────────────────────────────────
# M2: material_description Completeness — drops null/blank
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M2: material_description Completeness ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["material_description"]["applied_rules"] = [{
    "name": "Description not blank", "mode": "Validate",
    "pattern": r"^(?=.*\S).*$",
    "dimension": "Completeness", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "material_description")
# Row 6 (blank string) + Row 7 (null) = 2 rejections
check("2 missing descriptions rejected (blank + null)",
      rejected == 2, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M3: material_type allowed values (SAP enum)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M3: material_type SAP enum (FERT/HALB/ROH/HIBE/DIEN) ===")
df = material_dataset()
# Test BOTH paths: regex from rule_text + raw regex
rule_text = "Material Type must be one of: FERT, HALB, ROH, HIBE, DIEN"
inferred = infer_regex_pattern_from_rule("Validation", rule_text)
check("infer regex for SAP-style enum",
      inferred == "(?i)^(FERT|HALB|ROH|HIBE|DIEN)$", f"got {inferred!r}")
# Also: must NOT include the prose
values = _extract_allowed_values(rule_text)
check("allowed values are clean (no prose)",
      values == ["FERT", "HALB", "ROH", "HIBE", "DIEN"], f"got {values}")

sess = make_session(df)
sess.dq_config["material_type"]["applied_rules"] = [{
    "name": "Material type enum", "mode": "Validate",
    "pattern": inferred,
    "dimension": "Validation", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "material_type")
check("ZZZZ rejected, valid SAP codes accepted",
      rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M4: standard_price numeric — must be non-negative with up to 2 decimals
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M4: standard_price numeric pattern ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["standard_price"]["applied_rules"] = [{
    "name": "Price format", "mode": "Validate",
    "pattern": r"^\d+(\.\d{1,2})?$",   # non-neg, up to 2 decimals
    "dimension": "Validation", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "standard_price")
# Bad: -5.00 (negative), abc (non-numeric), 10.999 (3 decimals) = 3
check("3 bad prices rejected", rejected == 3, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M5: gross_weight numeric validation
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M5: gross_weight numeric ===")
rule_text = "Gross Weight must be numeric"
inferred = infer_regex_pattern_from_rule("Validation", rule_text)
check("numeric regex inferred",
      inferred == r"^-?\d+(\.\d+)?$", f"got {inferred!r}")

# ─────────────────────────────────────────────────────────────────────────────
# M6: weight_unit allowed values (ISO mass units)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M6: weight_unit allowed values ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["weight_unit"]["applied_rules"] = [{
    "name": "Weight unit", "mode": "Validate",
    "pattern": r"^(KG|G|LB|OZ|TON)$",
    "dimension": "Validation", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "weight_unit")
check("'POUND' rejected (use LB instead)", rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M7: EAN-13 / UPC-A barcode validation (12 or 13 digits)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M7: EAN-13 / UPC-A barcode ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["ean_upc"]["applied_rules"] = [{
    "name": "EAN/UPC barcode", "mode": "Validate",
    "pattern": r"^\d{12,13}$",
    "dimension": "Validation", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "ean_upc")
# Bad: "999" (3 digits), "" empty, None
check("short/empty/null barcodes rejected",
      rejected == 3, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M8: abc_indicator single-letter enum
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M8: ABC indicator (A/B/C) ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["abc_indicator"]["applied_rules"] = [{
    "name": "ABC indicator", "mode": "Validate",
    "pattern": r"^[ABC]$",
    "dimension": "Validation", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "abc_indicator")
check("D rejected", rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M9: procurement_type single-letter enum F/E/X
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M9: procurement_type F/E/X ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["procurement_type"]["applied_rules"] = [{
    "name": "Procurement type", "mode": "Validate",
    "pattern": r"^[FEX]$",
    "dimension": "Validation", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "procurement_type")
check("Z rejected", rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M10: created_on ISO date format
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M10: created_on YYYY-MM-DD ===")
df = material_dataset()
sess = make_session(df)
sess.dq_config["created_on"]["applied_rules"] = [{
    "name": "ISO date", "mode": "Validate",
    "pattern": r"^\d{4}-\d{2}-\d{2}$",
    "dimension": "Validation", "source": "ai",
}]
_, rejected = apply_column_rules(sess, "created_on")
check("'2024/05/22' non-ISO date rejected", rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# M11: lifecycle pipeline — joined-view stream
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M11: lifecycle pipeline on Material data ===")
df = material_dataset()
col_health = {}
for c in df.columns:
    non_empty = int(df[c].dropna().astype(str).str.strip().ne("").sum())
    col_health[c] = {
        "non_empty": non_empty, "total": len(df),
        "fill_rate": non_empty / len(df), "is_empty": non_empty == 0,
    }
real_cols = set(df.columns)
empty_set = {c for c, h in col_health.items() if h["is_empty"]}

# Cross-field rule on Material — composite uniqueness key
rg_row = pd.Series({
    "Column": "material_id + plant", "Columns": "material_id, plant",
    "Dimension": "Cross-field Validation",
    "Data Quality Rule": "(material_id, plant) tuple must be unique",
    "Regex Pattern": "",
})
entry = _evaluate_rule_status(rg_row, 0, df, col_health, real_cols, empty_set, set(), {})
check("composite key rule → multi_cde", entry["status"] == "multi_cde",
      f"status={entry['status']}")

# Missing field rule
rg_row = pd.Series({
    "Column": "ghost_field", "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "ghost_field must be uppercase",
    "Regex Pattern": "^[A-Z]+$",
})
entry = _evaluate_rule_status(rg_row, 1, df, col_health, real_cols, empty_set, set(), {})
check("missing material field → invalid", entry["status"] == "invalid",
      f"status={entry['status']}")

# Format violation present
rg_row = pd.Series({
    "Column": "material_id", "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "material_id must follow MAT-NNNNNN pattern",
    "Regex Pattern": r"^MAT-\d{6}$",
})
entry = _evaluate_rule_status(rg_row, 2, df, col_health, real_cols, empty_set, set(), {})
check("INVALID_ID present → actionable, fc=1",
      entry["status"] == "actionable" and entry["failure_count"] == 1,
      f"status={entry['status']}, fc={entry['failure_count']}")

# All-rows-pass: base_unit_of_measure has only valid values in the test data
rg_row = pd.Series({
    "Column": "base_unit_of_measure", "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "UoM must be 2-3 uppercase chars",
    "Regex Pattern": r"^[A-Z]{2,3}$",
})
entry = _evaluate_rule_status(rg_row, 3, df, col_health, real_cols, empty_set, set(), {})
check("UoM all valid → passed", entry["status"] == "passed",
      f"status={entry['status']}, fc={entry['failure_count']}")

# ─────────────────────────────────────────────────────────────────────────────
# M12: Full row preview shows material context
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M12: preview returns full row context with neighbouring fields ===")
df = material_dataset()
result = get_preview_failing(df, "material_id",
                             {"mode": "Validate", "pattern": r"^MAT-\d{6}$"})
check("1 failing row (INVALID_ID)", result["total_failing"] == 1)
row = result["rows"][0]
check("failing row carries plant context",
      row["plant"] == "P001", f"got plant={row.get('plant')}")
check("failing row carries material_description context",
      "material_description" in row)
check("failing row's _before is the bad value",
      row["_before"] == "INVALID_ID", f"got {row['_before']}")

# ─────────────────────────────────────────────────────────────────────────────
# M13: Apply chained — Case-normalise UoM then Validate enum
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M13: chained Case+Validate on weight_unit ===")
# Inject lowercase weight units to test the case-normalisation chain
df = pd.DataFrame({
    "weight_unit": ["kg", "KG", "Kg", "Lb", "INVALID"],
})
sess = make_session(df)
sess.dq_config["weight_unit"]["applied_rules"] = [
    {"name": "Force uppercase", "mode": "Case", "case": "UPPERCASE",
     "dimension": "Standardisation", "source": "ai"},
    {"name": "Weight unit enum", "mode": "Validate",
     "pattern": r"^(KG|G|LB|OZ|TON)$",
     "dimension": "Validation", "source": "ai"},
]
applied, rejected = apply_column_rules(sess, "weight_unit")
check("chain applies both rules", applied == 2)
# After Case: all uppercase. Then enum validates → INVALID rejected
check("only INVALID rejected after normalisation",
      rejected == 1, f"rejected={rejected}")
remaining = sorted(sess.df["weight_unit"].unique().tolist())
check("kg/Kg normalised to KG", "KG" in remaining and "kg" not in remaining,
      f"got {remaining}")

# ─────────────────────────────────────────────────────────────────────────────
# M14: Regex inference — Material domain prose
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M14: regex inference handles Material-domain prose ===")
got = infer_regex_pattern_from_rule("Validation",
       "Material Description must be no more than 40 characters")
check("max-length inferred", got == "^.{0,40}$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Validation",
       "Material Type must be one of the allowed values: FERT, HALB, ROH, HIBE, DIEN")
check("allowed-values inferred (the bug-fix case)",
      got == "(?i)^(FERT|HALB|ROH|HIBE|DIEN)$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Validation",
       "Standard Price must be numeric")
check("numeric inferred", got == r"^-?\d+(\.\d+)?$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Validation",
       "EAN/UPC must be a 13 digit code")
check("13-digit code inferred", got == r"^\d{13}$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Completeness",
       "Material Description must not be blank")
check("Completeness inferred", got == r"^(?=.*\S).*$", f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# M15: Custom rule on Material — survives purge
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M15: custom material rule survives AI-purge ===")
from backend.app.routers.rule_generator_router import _purge_ai_synced_from_dq_config

df = material_dataset()
sess = make_session(df)
sess.dq_config["material_type"]["applied_rules"] = [
    {"name": "AI material type", "mode": "Validate",
     "pattern": r"^(FERT|HALB)$", "dimension": "Validation", "source": "ai"},
    {"name": "Custom: extended types",
     "mode": "Validate", "pattern": r"^(FERT|HALB|ROH|HIBE|DIEN)$",
     "dimension": "Validation", "source": "custom"},
]
_purge_ai_synced_from_dq_config(sess)
remaining = [r["name"] for r in sess.dq_config["material_type"]["applied_rules"]]
check("custom material rule preserved after purge",
      remaining == ["Custom: extended types"], f"got {remaining}")

# ─────────────────────────────────────────────────────────────────────────────
# M16: REGRESSION — Completeness preview matches apply on null rows
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== M16: Completeness preview = apply (regression) ===")
df = material_dataset()
cfg = {"mode": "Validate", "pattern": r"^(?=.*\S).*$"}
preview = get_preview_failing(df, "material_description", cfg)
check("preview reports 2 failing (blank + null)",
      preview["total_failing"] == 2, f"got {preview['total_failing']}")

sess = make_session(df)
sess.dq_config["material_description"]["applied_rules"] = [{
    "name": "Not blank", "mode": "Validate",
    "pattern": r"^(?=.*\S).*$",
    "dimension": "Completeness", "source": "ai",
}]
_, apply_rejected = apply_column_rules(sess, "material_description")
check("apply rejects same count as preview reported",
      apply_rejected == preview["total_failing"],
      f"apply={apply_rejected}, preview={preview['total_failing']}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"MATERIAL-MASTER SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nMaterial-master cleansing tests passed.")
