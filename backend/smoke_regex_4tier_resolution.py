"""Regression suite for the 4-tier regex resolution.

User-reported issue: 4 Validation rules sitting Unmapped even though
the rule text contained a literal regex pattern OR the column had an
AI-classified semantic type:

  • entity_code: "must match the regex pattern ^BY\\d{6}$."
  • entity_type: "must satisfy the allowed values defined for the category."
  • id:          "must satisfy the regex pattern ^[0-9a-f]{8}-..."  (UUID)
  • updated_by:  "must match the format ^[A-Za-z0-9._%+-]+@.+\\.[A-Za-z]{2,}$"

Three of those have the regex literally embedded in the prose. The
fourth would benefit from a semantic-type lookup (if entity_type were
classified as enum_code with known values).

These tests assert:
  T1. Tier 2: embedded ``^...$`` regexes are extracted from rule text
  T2. Tier 3: column's semantic_type → canonical regex from the same
              _FORMAT_CHECKS registry Profile uses
  T3. Priority order: explicit > extracted > semantic > inferred
  T4. Tier 4 still works for natural-language rules
  T5. Cleansing and Profile produce IDENTICAL verdicts for typed columns
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.rule_generator.engine import (  # noqa: E402
    enrich_dataframe_regex_patterns,
    extract_regex_literal_from_text,
    infer_regex_pattern_from_rule,
)
from backend.app.services.dama_assessment import _FORMAT_CHECKS  # noqa: E402

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


# ─────────────────────────────────────────────────────────────────────────────
# T1: TIER 2 — regex literal embedded in rule text
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T1: tier 2 — extract embedded ^...$ regex from rule text ===")

# The four rules from the user's Unmapped screenshot
embedded_rules = {
    "Entity Code must match the regex pattern ^BY\\d{6}$.":
        r"^BY\d{6}$",
    "Unique Identifier must satisfy the regex pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$.":
        r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
    "Updated By must match the format ^[A-Za-z0-9._%+-]+@.+\\.[A-Za-z]{2,}$":
        r"^[A-Za-z0-9._%+-]+@.+\.[A-Za-z]{2,}$",
    "Code must match ^[A-Z]{3}\\d{5}$":
        r"^[A-Z]{3}\d{5}$",
}
for text, expected in embedded_rules.items():
    got = extract_regex_literal_from_text(text)
    check(f"extract from: {text[:55]}", got == expected,
          f"got {got!r}, expected {expected!r}")

# Texts WITHOUT a regex literal should return empty
no_regex_texts = [
    "Entity Type must satisfy the allowed values defined for the category.",
    "Name must not be blank.",
    "Created Time must be a valid datetime.",
]
for text in no_regex_texts:
    got = extract_regex_literal_from_text(text)
    check(f"no-regex returns empty: {text[:55]}", got == "", f"got {got!r}")

# Validate that extracted regexes actually compile
for text, _ in embedded_rules.items():
    got = extract_regex_literal_from_text(text)
    if got:
        try:
            re.compile(got)
            check(f"compiles: {got[:40]}", True, "")
        except re.error as e:
            check(f"compiles: {got[:40]}", False, str(e))

# ─────────────────────────────────────────────────────────────────────────────
# T2: TIER 3 — semantic_type lookup uses _FORMAT_CHECKS
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T2: tier 3 — canonical regex from semantic_type ===")

df = pd.DataFrame([
    {"Column": "pan_number",    "Dimension": "Validation",
     "Data Quality Rule": "PAN must satisfy the prescribed structure",
     "Regex Pattern": ""},
    {"Column": "email_address", "Dimension": "Validation",
     "Data Quality Rule": "Email must be syntactically valid",
     "Regex Pattern": ""},
    {"Column": "billing_country","Dimension": "Validation",
     "Data Quality Rule": "Country must be in the ISO list",
     "Regex Pattern": ""},
    {"Column": "currency",      "Dimension": "Validation",
     "Data Quality Rule": "Currency must be in the ISO list",
     "Regex Pattern": ""},
    {"Column": "mystery_col",   "Dimension": "Validation",
     "Data Quality Rule": "Mystery must follow some rule",
     "Regex Pattern": ""},
])
glossary = {
    "pan_number":      {"semantic_type": "pan"},
    "email_address":   {"semantic_type": "email"},
    "billing_country": {"semantic_type": "iso_country"},
    "currency":        {"semantic_type": "iso_currency"},
    # mystery_col has no entry — should fall through to tier 4
}
result = enrich_dataframe_regex_patterns(df, glossary=glossary)

# Each typed column should get the CANONICAL regex from _FORMAT_CHECKS
expected = {
    "pan_number":      _FORMAT_CHECKS["pan"].pattern,
    "email_address":   _FORMAT_CHECKS["email"].pattern,
    "billing_country": _FORMAT_CHECKS["iso_country"].pattern,
    "currency":        _FORMAT_CHECKS["iso_currency"].pattern,
}
for col, expected_regex in expected.items():
    row = result[result["Column"] == col].iloc[0]
    got = row["Regex Pattern"]
    check(f"{col}: uses canonical {col}'s semantic_type regex",
          got == expected_regex, f"got {got!r}")

# mystery_col falls through to tier 4 (natural-language inference)
mystery_row = result[result["Column"] == "mystery_col"].iloc[0]
# "Mystery must follow some rule" has no inferable trigger — stays empty
check("mystery_col with no semantic_type falls through to tier 4",
      mystery_row["Regex Pattern"] == "",
      f"got {mystery_row['Regex Pattern']!r}")

# ─────────────────────────────────────────────────────────────────────────────
# T3: priority order — explicit > extracted > semantic > inferred
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T3: priority order (explicit > extracted > semantic > inferred) ===")

# Row 1: BOTH explicit pattern AND embedded regex — explicit wins
df_prio = pd.DataFrame([
    {"Column": "pan_number", "Dimension": "Validation",
     "Data Quality Rule": "PAN must match ^EXPLICITLY_DIFFERENT$",
     "Regex Pattern": r"^EXPLICIT_PATTERN$"},
    # Row 2: NO explicit, HAS embedded regex AND known semantic_type —
    # embedded wins over semantic
    {"Column": "pan_number_2", "Dimension": "Validation",
     "Data Quality Rule": "PAN must match ^EXTRACTED_FROM_TEXT$",
     "Regex Pattern": ""},
    # Row 3: NO explicit, NO embedded, HAS semantic_type — semantic wins
    {"Column": "pan_number_3", "Dimension": "Validation",
     "Data Quality Rule": "PAN must follow the right format",
     "Regex Pattern": ""},
])
glossary_prio = {
    "pan_number":    {"semantic_type": "pan"},
    "pan_number_2":  {"semantic_type": "pan"},
    "pan_number_3":  {"semantic_type": "pan"},
}
result = enrich_dataframe_regex_patterns(df_prio, glossary=glossary_prio)
patterns = result.set_index("Column")["Regex Pattern"].to_dict()

check("explicit beats everything",
      patterns["pan_number"] == r"^EXPLICIT_PATTERN$",
      f"got {patterns['pan_number']!r}")
check("embedded beats semantic",
      patterns["pan_number_2"] == r"^EXTRACTED_FROM_TEXT$",
      f"got {patterns['pan_number_2']!r}")
check("semantic kicks in when nothing else does",
      patterns["pan_number_3"] == _FORMAT_CHECKS["pan"].pattern,
      f"got {patterns['pan_number_3']!r}")

# ─────────────────────────────────────────────────────────────────────────────
# T4: tier 4 fallback still works
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T4: tier 4 — natural-language inference still works ===")

df_t4 = pd.DataFrame([
    {"Column": "some_email_col", "Dimension": "Validation",
     "Data Quality Rule": "Some Email must be a valid email address",
     "Regex Pattern": ""},
    {"Column": "some_country",   "Dimension": "Validation",
     "Data Quality Rule": "Some Country must be a valid country code",
     "Regex Pattern": ""},
])
# No glossary — tier 3 doesn't apply; tier 4 should fire
result = enrich_dataframe_regex_patterns(df_t4)
patterns = result.set_index("Column")["Regex Pattern"].to_dict()
check("natural-language email infers", "@" in patterns["some_email_col"])
check("natural-language country infers", "[A-Za-z]" in patterns["some_country"])

# ─────────────────────────────────────────────────────────────────────────────
# T5: end-to-end — Cleansing and Profile agree
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T5: Cleansing and Profile produce identical verdicts ===")

# Build a rule df with typed columns, run through enrichment, then
# check the resulting regex matches what Profile's _FORMAT_CHECKS would
# apply for the same row.
typed_columns = ["pan", "gstin", "email", "iso_country", "iso_currency", "ifsc"]
sample_values = {
    "pan":          ["ABCDE1234F",       "INVALIDPAN"],
    "gstin":        ["33EMEPS9578B1ZO",  "BADGSTIN"],
    "email":        ["a@b.co",           "no-at-sign"],
    "iso_country":  ["IN",               "INDIA"],
    "iso_currency": ["USD",              "DOLLAR"],
    "ifsc":         ["HDFC0000123",      "BAD"],
}

df_t5 = pd.DataFrame([
    {"Column": f"col_{t}", "Dimension": "Validation",
     "Data Quality Rule": f"{t} must follow the right format",
     "Regex Pattern": ""}
    for t in typed_columns
])
glossary_t5 = {f"col_{t}": {"semantic_type": t} for t in typed_columns}
result = enrich_dataframe_regex_patterns(df_t5, glossary=glossary_t5)
patterns = result.set_index("Column")["Regex Pattern"].to_dict()

for t in typed_columns:
    cleansing_rx = re.compile(patterns[f"col_{t}"])
    profile_rx = _FORMAT_CHECKS[t]
    for v in sample_values[t]:
        c_verdict = bool(cleansing_rx.match(v))
        p_verdict = bool(profile_rx.match(v))
        check(f"{t} verdict on {v!r}: both={c_verdict}",
              c_verdict == p_verdict,
              f"cleansing={c_verdict}, profile={p_verdict}")

# ─────────────────────────────────────────────────────────────────────────────
# T6: USER'S BUG — the 4 Unmapped rules from the screenshot
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T6: user's bug — the 4 Unmapped rules should now map ===")

df_t6 = pd.DataFrame([
    {"Column": "entity_code", "Dimension": "Validation",
     "Data Quality Rule": "Entity Code must match the regex pattern ^BY\\d{6}$.",
     "Regex Pattern": ""},
    {"Column": "entity_type", "Dimension": "Validation",
     "Data Quality Rule": "Entity Type must satisfy the allowed values defined for the category.",
     "Regex Pattern": ""},
    {"Column": "id", "Dimension": "Validation",
     "Data Quality Rule": "Unique Identifier must satisfy the regex pattern ^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$.",
     "Regex Pattern": ""},
    {"Column": "updated_by", "Dimension": "Validation",
     "Data Quality Rule": "Updated By must match the format ^[A-Za-z0-9._%+-]+@.+\\.[A-Za-z]{2,}$",
     "Regex Pattern": ""},
])
# Bonus: simulate that the CDE recommender classified updated_by as email
glossary_t6 = {"updated_by": {"semantic_type": "email"}}
result = enrich_dataframe_regex_patterns(df_t6, glossary=glossary_t6)
patterns = result.set_index("Column")["Regex Pattern"].to_dict()

check("entity_code now mapped via embedded regex",
      patterns["entity_code"] == r"^BY\d{6}$",
      f"got {patterns['entity_code']!r}")
check("id now mapped to UUID regex via embedded",
      "0-9a-f" in patterns["id"],
      f"got {patterns['id']!r}")
check("updated_by now mapped via embedded email regex",
      "@" in patterns["updated_by"],
      f"got {patterns['updated_by']!r}")
check("entity_type STILL unmapped (genuinely too vague — no enum values listed)",
      patterns["entity_type"] == "",
      f"got {patterns['entity_type']!r}")

print(f"\n→ 3 of 4 previously-unmapped rules now have regex.")
print(f"→ entity_type remains unmapped because the rule text gives no specifics.")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"4-TIER RESOLUTION SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nCleansing now uses every available signal to auto-map rules, "
      "shares regex registry with Profile.")
