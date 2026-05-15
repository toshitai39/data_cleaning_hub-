"""Regression suite for Profile's source-of-truth regexes (_FORMAT_CHECKS).

The user found a HARD bug: Profile's GSTIN regex was 16 characters
long (extra ``\\d`` group between PAN's last letter and the
``[A-Z\\d]Z[A-Z\\d]`` tail). Every valid 15-char GSTIN was being
flagged invalid by the Validation drill-down, while Cleansing rules
(which use the canonical 15-char pattern) said the same rows passed.
Same data, opposite verdicts.

These tests assert every regex in _FORMAT_CHECKS:
  1. Accepts canonical well-formed examples
  2. Rejects clearly malformed ones
  3. Matches the spec character count where length is fixed
"""
from __future__ import annotations

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.services.dama_assessment import _FORMAT_CHECKS  # noqa: E402

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


def assert_format(semantic_type, well_formed, malformed):
    rx = _FORMAT_CHECKS.get(semantic_type)
    if rx is None:
        check(f"{semantic_type} regex exists", False, "missing from _FORMAT_CHECKS")
        return
    for v in well_formed:
        check(f"{semantic_type} accepts {v!r}",
              bool(rx.match(v)), f"regex={rx.pattern}")
    for v in malformed:
        check(f"{semantic_type} rejects {v!r}",
              not bool(rx.match(v)), f"regex={rx.pattern}")


# ─────────────────────────────────────────────────────────────────────────────
# THE BUG: GSTIN regex was 16 chars instead of 15
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== THE BUG: GSTIN must be exactly 15 chars (was 16) ===")

# These are the EXACT values from the user's screenshot that Profile was
# wrongly flagging as invalid:
assert_format("gstin",
    well_formed=[
        "33EMEPS9578B1ZO",       # user's data — was 'invalid' in Profile
        "29AAICK4821A1ZR",       # user's data — was 'invalid' in Profile
        "27ABCDE1234F1Z5",       # canonical textbook GSTIN
        "07AAAAA0000A1Z1",       # all-As variant
        "33AAAAA0000A1Z5",       # state 33, all-As PAN
    ],
    malformed=[
        "ABCDE1234F",            # PAN, not GSTIN
        "33EMEPS9578B1ZOO",      # 16 chars — too long
        "33EMEPS9578B1Z",        # 14 chars — too short
        "33emeps9578b1zo",       # lowercase
        "33EMEPS9578B1XO",       # missing literal Z at position 14
        "AAEMEPS9578B1ZO",       # state not digits
    ],
)

# ─────────────────────────────────────────────────────────────────────────────
# Other identifiers — sanity check they're still correct
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== PAN — 10 chars ===")
assert_format("pan",
    well_formed=["ABCDE1234F", "AAAPL1234C", "ZZZZZ9999Z"],
    malformed=["ABCDE12345", "12345ABCDF", "abcde1234f", "ABCDE1234FX"],
)

print("\n=== TAN — 10 chars (4 letters + 5 digits + 1 letter) ===")
assert_format("tan",
    well_formed=["DELS12345E", "MUMA00000Z"],
    malformed=["DELS1234E", "12345DELSE", "dels12345e"],
)

print("\n=== CIN — 21 chars ===")
assert_format("cin",
    well_formed=["L01234AB1234ABC123456", "U67890MH2000XYZ123456"],
    malformed=["X01234AB1234ABC123456",          # bad first letter
               "L01234AB1234ABC12345",           # too short
               "L01234AB1234ABC1234567"],        # too long
)

print("\n=== IFSC — 11 chars ===")
assert_format("ifsc",
    well_formed=["HDFC0000123", "ICIC0001234", "SBIN0002345"],
    malformed=["HDFC1234567",   # 5th char not 0
               "HDFC000012",    # too short
               "hdfc0000123",   # lowercase
               "12HD0000123"],  # first 4 not letters
)

print("\n=== Aadhaar — 12 digits ===")
assert_format("aadhaar",
    well_formed=["123456789012", "1234 5678 9012"],
    malformed=["12345678901",    # too short
               "1234567890123",  # too long
               "abc456789012"],  # non-digits
)

print("\n=== IBAN ===")
assert_format("iban",
    well_formed=[
        "DE89370400440532013000",
        "GB82WEST12345698765432",
        "FR1420041010050500013M02606",
    ],
    malformed=["IBAN", "12345", "de89370400440532013000"],
)

print("\n=== SWIFT/BIC — 8 or 11 chars ===")
assert_format("swift",
    well_formed=["DEUTDEFF", "DEUTDEFF500", "CHASUS33", "BOFAUS3NXXX"],
    malformed=["INVALID", "X", "DEUTDEFF50"],  # 10 chars not allowed
)

print("\n=== ISO country / currency / year ===")
assert_format("iso_country",
    well_formed=["IN", "US", "DE", "GB", "FR"],
    malformed=["India", "us", "USA", "1"],
)
assert_format("iso_currency",
    well_formed=["USD", "EUR", "INR", "GBP"],
    malformed=["DOLLAR", "eur", "U"],
)
assert_format("year",
    well_formed=["1900", "2024", "2099"],
    malformed=["1899", "2100", "24", "YYYY"],
)

print("\n=== Email + phone + URL ===")
assert_format("email",
    well_formed=["a@b.co", "alice.smith@uniqus.io", "x+tag@example.com"],
    malformed=["no-at.com", "@bad.com", "missing@tld"],
)
assert_format("phone",
    well_formed=["+91 9876543210", "(555) 123-4567", "+1-555-1234567"],
    malformed=["abc", "12", "phone"],
)
assert_format("url",
    well_formed=["https://x.com", "http://uniqus.io/path"],
    malformed=["no-protocol.com", "javascript:alert(1)"],
)

# ─────────────────────────────────────────────────────────────────────────────
# Cross-check: Profile's GSTIN regex agrees with Cleansing's inferred regex
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Cleansing-vs-Profile agreement (the critical consistency) ===")
import re
profile_rx = _FORMAT_CHECKS["gstin"]

# Cleansing's inferred regex (from infer_regex_pattern_from_rule's
# canonical well-known GSTIN path)
cleansing_rx = re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$")

# Both should give IDENTICAL verdicts on the user's data
for v in ["33EMEPS9578B1ZO", "29AAICK4821A1ZR", "27ABCDE1234F1Z5"]:
    p_match = bool(profile_rx.match(v))
    c_match = bool(cleansing_rx.match(v))
    check(f"{v!r}: Profile and Cleansing agree (both={p_match})",
          p_match == c_match,
          f"profile={p_match}, cleansing={c_match}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"PROFILE-REGEX-CORRECTNESS SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nProfile canonical regexes are now correct. "
      "Cleansing and Profile produce the same verdicts.")
