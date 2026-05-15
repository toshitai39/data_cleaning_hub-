"""Smoke tests for regex inference — specifically the allowed-values
parser bug where "must be one of the allowed values: A, B, C" was being
parsed as ["the allowed values: A", "B", "C"], producing a broken
regex that rejected even the valid values.
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.rule_generator.engine import (  # noqa: E402
    _extract_allowed_values,
    infer_regex_pattern_from_rule,
)

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


# ─────────────────────────────────────────────────────────────────────────────
# T1: THE BUG — "must be one of the allowed values: X, Y, Z"
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T1: must be one of the allowed values: X, Y, Z ===")
text = "GST Treatment must be one of the allowed values: business_gst, business_none, overseas"
values = _extract_allowed_values(text)
check("extracted exactly 3 values",
      len(values) == 3, f"got {values}")
check("values are clean (no 'the allowed values:' prefix)",
      values == ["business_gst", "business_none", "overseas"],
      f"got {values}")

regex = infer_regex_pattern_from_rule("Validation", text)
check("regex is (?i)^(business_gst|business_none|overseas)$",
      regex == "(?i)^(business_gst|business_none|overseas)$",
      f"got {regex!r}")

# Verify the inferred regex actually accepts the documented values
import re
pat = re.compile(regex)
check("regex matches 'business_gst'", bool(pat.match("business_gst")))
check("regex matches 'business_none'", bool(pat.match("business_none")))
check("regex matches 'overseas'", bool(pat.match("overseas")))
check("regex rejects 'invalid_value'", not bool(pat.match("invalid_value")))

# ─────────────────────────────────────────────────────────────────────────────
# T2: phrasing variants
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T2: phrasing variants ===")
variants = [
    ("Status must be one of: ACTIVE, INACTIVE", ["ACTIVE", "INACTIVE"]),
    ("Code must be one of the following values: A, B, C", ["A", "B", "C"]),
    ("Tier must be one of the allowed values: gold, silver, bronze",
     ["gold", "silver", "bronze"]),
    ("Region allowed values: APAC, EMEA, NA", ["APAC", "EMEA", "NA"]),
    ("Type must be one of ACTIVE, INACTIVE, PENDING",
     ["ACTIVE", "INACTIVE", "PENDING"]),
]
for text, expected in variants:
    got = _extract_allowed_values(text)
    check(f"parse: {text[:60]}", got == expected, f"got {got}")

# ─────────────────────────────────────────────────────────────────────────────
# T3: malformed inputs should return None, not garbage
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T3: malformed inputs return None ===")
mal = [
    "X must be alphanumeric",
    "X must not be blank",
    "X must be 8 digits long",
    "Just a sentence with no structure",
]
for text in mal:
    got = _extract_allowed_values(text)
    check(f"None for: {text[:60]}", got is None, f"got {got}")

# ─────────────────────────────────────────────────────────────────────────────
# T4: quoted values get stripped
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T4: quoted values get stripped ===")
text = "Mode must be one of: 'manual', 'auto', 'mixed'"
got = _extract_allowed_values(text)
check("quotes stripped", got == ["manual", "auto", "mixed"], f"got {got}")

# ─────────────────────────────────────────────────────────────────────────────
# T5: semicolons also work as separators (some style guides use them)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T5: semicolon-separated values ===")
text = "Bucket must be one of: small; medium; large"
got = _extract_allowed_values(text)
check("semicolons split correctly",
      got == ["small", "medium", "large"], f"got {got}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"REGEX-INFERENCE SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nAll regex-inference tests passed.")
