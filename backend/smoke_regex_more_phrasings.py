"""Regression suite for three "Unmapped" rules the user flagged that
were not actually vague:

  • entity_code: "must be a string with a length between 8 and 10 characters"
  • entity_type: "must satisfy the structural rules for string data"
  • id:          "must be a valid UUID string"

These are mechanical, well-specified rules. They were Unmapped because
my inference function didn't recognise:
  - length RANGE ("between X and Y")
  - UUID format
  - generic "structural rules for string"
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


def check_inferred(rule_text, accepts, rejects):
    pat = infer_regex_pattern_from_rule("Validation", rule_text)
    if not pat:
        check(f"inferred: {rule_text[:60]}", False, "regex empty")
        return
    try:
        rx = re.compile(pat)
    except re.error as e:
        check(f"compiled: {rule_text[:60]}", False, str(e))
        return
    check(f"inferred (got {pat[:35]}{'…' if len(pat)>35 else ''})",
          True, rule_text[:60])
    for v in accepts:
        check(f"  └ accepts {v!r}", bool(rx.match(v)),
              f"pattern={pat!r}")
    for v in rejects:
        check(f"  └ rejects {v!r}", not bool(rx.match(v)),
              f"pattern={pat!r}")


# ─────────────────────────────────────────────────────────────────────────────
# THE THREE BUGS FROM THE USER'S SCREENSHOT
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== USER'S BUG #1: length RANGE ===")

check_inferred(
    "Entity Code must be a string with a length between 8 and 10 characters.",
    accepts=["BY123456", "BY1234567", "BY12345678"],     # 8, 9, 10 chars
    rejects=["BY12345", "BY123456789", ""],              # 7, 11, 0 chars
)

# Other range phrasings
check_inferred(
    "Code must be between 4 and 6 characters",
    accepts=["1234", "12345", "123456"],
    rejects=["123", "1234567"],
)

check_inferred(
    "ID must be 5 to 15 characters long",
    accepts=["12345", "123456789012345"],
    rejects=["1234", "1234567890123456"],
)


print("\n=== USER'S BUG #2: UUID ===")

check_inferred(
    "Customer ID must be a valid UUID string.",
    accepts=[
        "550e8400-e29b-41d4-a716-446655440000",     # canonical UUID v4
        "00000000-0000-0000-0000-000000000000",     # nil UUID
        "AABBCCDD-EEFF-0011-2233-445566778899",     # uppercase hex
    ],
    rejects=[
        "550e8400-e29b-41d4-a716",                  # too short
        "not-a-uuid",
        "550e8400e29b41d4a716446655440000",         # no hyphens
    ],
)

# Other UUID phrasings the LLM emits
for variant in (
    "ID must be a valid UUID",
    "ID must be in UUID format",
    "Customer ID must be a UUID v4",
    "ID must follow the UUID standard",
):
    check_inferred(
        variant,
        accepts=["550e8400-e29b-41d4-a716-446655440000"],
        rejects=["not-a-uuid"],
    )


print("\n=== USER'S BUG #3: structural rules for string ===")

check_inferred(
    "Entity Type must satisfy the structural rules for string data.",
    accepts=["any-non-blank-value", "X", "with spaces and chars"],
    rejects=["", "   ", "\t"],
)

# Other generic-string phrasings
for variant in (
    "Field must be a string",
    "Type must be a non-empty string",
    "Value must be string data",
):
    check_inferred(
        variant,
        accepts=["something"],
        rejects=["", "   "],
    )

# ─────────────────────────────────────────────────────────────────────────────
# Regression: existing patterns still work
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Regression: max-length / exact-length still work ===")

got = infer_regex_pattern_from_rule(
    "Validation", "Description must have a maximum length of 255 characters"
)
check("max-length 255 still works", got == "^.{0,255}$", f"got {got!r}")

got = infer_regex_pattern_from_rule(
    "Validation", "Internal Code must be exactly 10 characters"
)
check("exact-length 10 still works", got == "^.{10}$", f"got {got!r}")

# Make sure UUID doesn't over-match on unrelated mentions
got = infer_regex_pattern_from_rule(
    "Validation", "Field uuid_old has been deprecated"
)
check("'uuid_old' alone (no valid/format/...) doesn't trigger UUID regex",
      got != r"(?i)^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$",
      f"got {got!r}")

# Range should NOT match when the rule says "max" or "up to"
got = infer_regex_pattern_from_rule(
    "Validation", "Name must be up to 50 characters with max length 50"
)
check("max-length phrasing wins over range",
      got == "^.{0,50}$", f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"MORE-PHRASINGS SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nLength-range / UUID / structural-string rules now auto-mapped.")
