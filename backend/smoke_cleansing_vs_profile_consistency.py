"""Regression suite for Cleansing-vs-Profile validation consistency.

User-reported bug: Cleansing tab said "GSTIN: Passed" while Profile
drill-down said "GSTIN: 2 invalid". Same data, opposite verdicts.

Root cause: the AI rule text "GSTIN must be alphanumeric with a length
of 15 characters" matched the generic exact-length branch of the regex
inference, returning ^.{15}$ — which trivially passes for any 15-char
string, including malformed GSTINs. Profile uses the canonical 15-char
structural GSTIN regex, so it correctly flagged the bad rows.

Fix: well-known regulatory identifier formats (CIN / GSTIN / PAN /
IFSC / EORI / DUNS / EIN / Aadhaar / IBAN / SWIFT) are now checked
EARLY in the inference function, taking priority over the exact-length
fallback. The trigger is just the identifier name being mentioned —
overwhelmingly what the user wants.

These tests assert the inferred regex agrees with the canonical
semantic-type regex used by Profile drill-downs.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.rule_generator.engine import (  # noqa: E402
    infer_regex_pattern_from_rule,
)

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


def check_identifier(label, rule_text, samples_should_reject, samples_should_pass):
    """For each rule text, ensure the inferred regex rejects the sample
    malformed values and accepts the sample well-formed ones."""
    pat = infer_regex_pattern_from_rule("Validation", rule_text)
    if not pat:
        check(f"{label} inferred", False, "regex empty")
        return
    try:
        rx = re.compile(pat)
    except re.error as e:
        check(f"{label} compiled", False, str(e))
        return
    for s in samples_should_pass:
        check(f"{label} accepts {s!r}", bool(rx.match(s)),
              f"pattern {pat!r}")
    for s in samples_should_reject:
        check(f"{label} rejects {s!r}", not bool(rx.match(s)),
              f"pattern {pat!r}")


# ─────────────────────────────────────────────────────────────────────────────
# THE EXACT BUG: GSTIN with length-only rule text
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== THE BUG: 'GSTIN must be alphanumeric with length of 15 characters' ===")

# This is the wording from the user's screenshot. Before the fix it
# returned ^.{15}$ (trivially permissive). Now it returns the canonical
# GSTIN structural regex.
pat = infer_regex_pattern_from_rule(
    "Validation",
    "GSTIN must be alphanumeric with a length of 15 characters.",
)
check("not just ^.{15}$ any-15-chars trap",
      pat != "^.{15}$", f"got {pat!r}")
check("looks like canonical GSTIN format",
      "[A-Z]{5}" in (pat or "") and "Z" in (pat or ""),
      f"got {pat!r}")

# Canonical structural validation: well-formed GSTINs accepted,
# garbage 15-char strings rejected
check_identifier(
    "GSTIN length+alphanumeric",
    "GSTIN must be alphanumeric with a length of 15 characters.",
    samples_should_reject=[
        "ABCDEFGHIJKLMNO",        # 15 letters — wrong shape
        "123456789012345",        # 15 digits — wrong shape
        "AAAAA1234AAAAAA",        # missing Z anchor
    ],
    samples_should_pass=[
        "27ABCDE1234F1Z5",        # canonical GSTIN
        "33EMEPS9578B1ZO",        # user's reported "invalid" data
        "29AAICK4821A1ZR",        # user's reported "invalid" data
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
# Other well-known identifiers — all length/format combinations
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Other well-known identifiers — broad triggers ===")

check_identifier(
    "PAN length-only",
    "PAN Number must be a string with length of 10 characters",
    samples_should_reject=["AAAAA12345", "ABCDEFGHIJ", "1234567890"],
    samples_should_pass=["ABCDE1234F"],
)

check_identifier(
    "IFSC length-only",
    "IFSC code must be 11 characters",
    samples_should_reject=["HDFCXXXX123", "12345678901"],
    samples_should_pass=["HDFC0000123", "ICIC0001234"],
)

check_identifier(
    "CIN length-only",
    "CIN must be a 21 character code",
    samples_should_reject=["A12345AB1234ABC123456", "123456789012345678901"],
    samples_should_pass=["L01234AB1234ABC123456", "U67890MH2000XYZ123456"],
)

check_identifier(
    "DUNS length-only",
    "DUNS number must be a 9 digit code",
    samples_should_reject=["12345678", "1234567890", "ABC123456"],
    samples_should_pass=["123456789"],
)

check_identifier(
    "EIN with digits",
    "EIN must be a 9-digit identifier in NN-NNNNNNN format",
    samples_should_reject=["123456789", "12-12345"],
    samples_should_pass=["12-3456789"],
)

check_identifier(
    "Aadhaar",
    "Aadhaar must be a 12 digit number",
    samples_should_reject=["123456789", "ABC123456789"],
    samples_should_pass=["123456789012"],
)

# IBAN / SWIFT — international banking
check_identifier(
    "IBAN",
    "IBAN must be in the standard IBAN format",
    samples_should_reject=["IBAN123", "ABCD1234"],
    samples_should_pass=["DE89370400440532013000", "GB82WEST12345698765432"],
)

check_identifier(
    "SWIFT/BIC",
    "SWIFT code must be a valid BIC",
    samples_should_reject=["INVALID", "X"],
    samples_should_pass=["DEUTDEFF", "DEUTDEFF500", "CHASUS33"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Variants the AI commonly emits — make sure all phrasings hit the
# right canonical regex (not the generic length fallback)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Phrasing variants — all hit canonical regex ===")

for variant in [
    "GSTIN must be 15 characters",
    "gstin must satisfy the structural rules",
    "GSTIN format validation",
    "GST Identification Number must be alphanumeric",
    "GSTIN must follow the prescribed format",
]:
    pat = infer_regex_pattern_from_rule("Validation", variant)
    check(f"variant gives canonical GSTIN: {variant[:55]}",
          pat and "[A-Z]{5}" in pat and "Z" in pat,
          f"got {pat!r}")

for variant in [
    "PAN must be alphanumeric with 10 characters",
    "PAN must satisfy the structural rules",
    "PAN Number must follow the prescribed format",
]:
    pat = infer_regex_pattern_from_rule("Validation", variant)
    check(f"variant gives canonical PAN: {variant[:55]}",
          pat == r"^[A-Z]{5}\d{4}[A-Z]$", f"got {pat!r}")

# ─────────────────────────────────────────────────────────────────────────────
# Negative cases — ensure max-length and exact-length still work for
# rules that DON'T mention well-known identifiers
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Regression: generic length rules still work ===")

got = infer_regex_pattern_from_rule(
    "Validation", "Description must have a maximum length of 100 characters"
)
check("max-length 100 still infers ^.{0,100}$",
      got == "^.{0,100}$", f"got {got!r}")

got = infer_regex_pattern_from_rule(
    "Validation", "Code must be exactly 6 characters long"
)
check("exact-length 6 still infers ^.{6}$",
      got == "^.{6}$", f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"CLEANSING-VS-PROFILE SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nWell-known identifier rules now produce canonical regex, "
      "matching what Profile drill-down checks against.")
