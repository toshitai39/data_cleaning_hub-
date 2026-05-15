"""Regression suite for natural-language rule → regex inference.

The user reported four "Unmapped" rules in the Cleansing tab that
SHOULD have been mapped to standard validators:

  • Billing Country must be a valid country name.
  • Created Time must be a valid datetime value.
  • Email ID must satisfy the structural rules of a valid email address
  • Last Modified Time must be a valid datetime value.

All four of these are basic, common semantics that any data-quality
engine should auto-translate. This suite asserts they (and a wide
spread of related phrasings) now produce sensible regex patterns.
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


def check_regex(rule_text, must_accept, must_reject, dim="Validation"):
    pat = infer_regex_pattern_from_rule(dim, rule_text)
    if not pat:
        check(f"NOT INFERRED: {rule_text[:60]}", False, "regex was empty")
        return
    try:
        rx = re.compile(pat)
    except re.error as e:
        check(f"REGEX COMPILE: {rule_text[:60]}", False, f"{e}")
        return
    for val in must_accept:
        ok = bool(rx.match(val))
        check(f"accepts {val!r}: {rule_text[:50]}", ok, f"got pattern {pat!r}")
    for val in must_reject:
        ok = not bool(rx.match(val))
        check(f"rejects {val!r}: {rule_text[:50]}", ok, f"pattern {pat!r} wrongly accepted")


# ─────────────────────────────────────────────────────────────────────────────
# T1: THE FOUR BUGS FROM THE USER'S SCREENSHOT
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T1: the four rules from the user's Unmapped screenshot ===")

check_regex(
    "Email ID must satisfy the structural rules of a valid email address",
    must_accept=["a@b.com", "alice.smith@uniqus.io", "x+test@example.co.in"],
    must_reject=["plainstring", "no-at-sign.com", "@missingname.com", "missing@tld"],
)

check_regex(
    "Created Time must be a valid datetime value.",
    must_accept=[
        "2024-05-15",
        "2024-05-15T13:45:00",
        "2024-05-15 13:45:00",
        "2024-05-15T13:45:00.123Z",
        "2024-05-15T13:45:00+05:30",
    ],
    must_reject=["15-05-2024", "May 15 2024", "tomorrow", "abc"],
)

check_regex(
    "Last Modified Time must be a valid datetime value.",
    must_accept=["2024-01-01", "2024-01-01T00:00:00", "2024-12-31T23:59:59Z"],
    must_reject=["01/01/2024", "yesterday", ""],
)

check_regex(
    "Billing Country must be a valid country name.",
    must_accept=["IN", "US", "DE", "IND", "USA"],
    must_reject=["INDIA", "United States", "1", ""],
)

# ─────────────────────────────────────────────────────────────────────────────
# T2: more phrasing variants the LLM commonly emits
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T2: alternative phrasings the LLM emits ===")

# Email variants
for text in (
    "Email must be in a valid format.",
    "EmailID must be a well-formed email address.",
    "Email must conform to RFC 5322 standard.",
):
    check_regex(text, must_accept=["a@b.com"], must_reject=["not-an-email"])

# Country variants
for text in (
    "Country must be a valid ISO country code",
    "Shipping Country must be in alpha-2 format",
    "country_code must be a valid 2-letter code",
):
    check_regex(text, must_accept=["IN", "US"], must_reject=["INDIA", "1"])

# Currency
for text in (
    "Currency must be a valid ISO currency code",
    "currency_code must be a 3-letter code",
):
    check_regex(text, must_accept=["USD", "EUR", "INR"], must_reject=["DOLLAR", "U"])

# Phone variants
for text in (
    "Phone must be a valid phone number",
    "mobile_phone must follow E.164 format",
):
    check_regex(
        text,
        must_accept=["+91 9876543210", "+1-555-1234567", "9876543210"],
        must_reject=["abc", "12"],
    )

# Datetime variants
for text in (
    "created_at must be a valid timestamp.",
    "updated_at must have a valid datetime format.",
    "loaded_at must be a valid date/time.",
):
    check_regex(text, must_accept=["2024-01-01T12:00:00"], must_reject=["nope"])

# Plain date
for text in (
    "Birthday must be a valid date.",
    "must be a date.",
):
    check_regex(text, must_accept=["2024-05-15"], must_reject=["May 15"])

# ─────────────────────────────────────────────────────────────────────────────
# T3: existing patterns still work (regression guard)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T3: existing regex patterns unaffected ===")

# Max-length (the earlier ^.{255}$ bug)
got = infer_regex_pattern_from_rule(
    "Validation", "Company Name must be a string with a maximum length of 255 characters"
)
check("max-length 255 still works", got == "^.{0,255}$", f"got {got!r}")

# Allowed-values (the earlier GST Treatment bug)
got = infer_regex_pattern_from_rule(
    "Validation", "Status must be one of: ACTIVE, INACTIVE, PENDING"
)
check("allowed-values still works",
      got == "(?i)^(ACTIVE|INACTIVE|PENDING)$", f"got {got!r}")

# Numeric
got = infer_regex_pattern_from_rule("Validation", "Standard Price must be numeric")
check("numeric still works", got == r"^-?\d+(\.\d+)?$", f"got {got!r}")

# PAN well-known
got = infer_regex_pattern_from_rule(
    "Validation", "PAN must be a valid PAN format"
)
check("PAN still works", got == r"^[A-Z]{5}\d{4}[A-Z]$", f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"NATURAL-LANGUAGE REGEX SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nAll natural-language regex inference tests passed.")
