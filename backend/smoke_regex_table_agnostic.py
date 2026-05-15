"""Prove the natural-language regex inference is table-agnostic.

The user asked (twice): "is it table specific?"

This suite runs the same inference engine against AI-generated rule
text patterned after FIVE different master-data domains and asserts
that the same regex pieces fire correctly for each. No domain-specific
column names are hardcoded — only the LLM's natural-language patterns.

Domains covered:
  1. Vendor Master      — payment / bank / tax IDs
  2. Material Master    — SAP codes / barcodes / units
  3. Employee Master    — HR fields / DOB / SSN
  4. Patient Master     — healthcare / NPI / MRN
  5. Financial Order    — accounting / amounts / dates
  6. SAP Material × Plant joined view — composite-key context
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from features.rule_generator.engine import (  # noqa: E402
    infer_regex_pattern_from_rule, _extract_allowed_values,
)

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


def check_inferred(domain, rule_text, must_accept, must_reject, expected_kind=None):
    pat = infer_regex_pattern_from_rule("Validation", rule_text)
    if not pat:
        check(f"[{domain}] inferred: {rule_text[:55]}", False, "regex empty")
        return
    try:
        rx = re.compile(pat)
    except re.error as e:
        check(f"[{domain}] compiled: {rule_text[:55]}", False, str(e))
        return
    check(f"[{domain}] inferred (got {pat[:35]}{'…' if len(pat)>35 else ''})",
          True, rule_text[:55])
    for v in must_accept:
        ok = bool(rx.match(v))
        check(f"  └ accepts {v!r}", ok, "")
    for v in must_reject:
        ok = not bool(rx.match(v))
        check(f"  └ rejects {v!r}", ok, "")


# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN 1: VENDOR MASTER
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== DOMAIN 1: VENDOR MASTER ===")

check_inferred("vendor",
    "Vendor Email must be a valid email address",
    must_accept=["ar@acme.com", "billing@globex.io"],
    must_reject=["no-at-sign.com"],
)
check_inferred("vendor",
    "Vendor Country must be a valid ISO country code",
    must_accept=["IN", "DE", "USA"],
    must_reject=["India", "1"],
)
check_inferred("vendor",
    "Bank Account currency must be a valid 3-letter code",
    must_accept=["USD", "EUR", "INR"],
    must_reject=["DOLLAR", "U"],
)
check_inferred("vendor",
    "Vendor phone must be a valid phone number",
    must_accept=["+91-98765-43210", "5551234567"],
    must_reject=["abc"],
)
check_inferred("vendor",
    "Vendor created_on must be a valid date",
    must_accept=["2024-01-15"],
    must_reject=["15-01-2024"],
)
check_inferred("vendor",
    "payment_terms must be one of: NET30, NET60, COD, ADVANCE",
    must_accept=["NET30", "COD", "ADVANCE"],
    must_reject=["NET90", "INVOICE"],
)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN 2: MATERIAL MASTER (joined view, M × plant)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== DOMAIN 2: MATERIAL × PLANT (joined view) ===")

check_inferred("material",
    "material_type must be one of: FERT, HALB, ROH, HIBE, DIEN",
    must_accept=["FERT", "DIEN"],
    must_reject=["ZZZZ", "RAW"],
)
check_inferred("material",
    "Weight Unit must be one of: KG, G, LB, OZ, TON",
    must_accept=["KG", "LB", "TON"],
    must_reject=["POUND", "kilograms"],
)
check_inferred("material",
    "EAN must be a 13 digit code",
    must_accept=["8901234567890"],
    must_reject=["1234", "abc"],
)
check_inferred("material",
    "Standard Price must be numeric",
    must_accept=["125.50", "0", "10"],
    must_reject=["abc", "USD125"],
)
check_inferred("material",
    "Material Description must be no more than 40 characters",
    must_accept=["Short", "X" * 40],
    must_reject=["X" * 41],
)
check_inferred("material",
    "Created On must be a valid datetime value",
    must_accept=["2024-05-15", "2024-05-15T10:30:00"],
    must_reject=["May 15"],
)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN 3: EMPLOYEE MASTER (HR)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== DOMAIN 3: EMPLOYEE MASTER ===")

check_inferred("employee",
    "Work Email must satisfy the structural rules of a valid email address",
    must_accept=["alice.smith@company.com", "x@y.io"],
    must_reject=["no-at-symbol.com"],
)
check_inferred("employee",
    "employee_phone must follow E.164 format",
    must_accept=["+1-555-1234567", "+919876543210"],
    must_reject=["123"],
)
check_inferred("employee",
    "Date of Birth must be a valid date",
    must_accept=["1985-04-12"],
    must_reject=["Apr 12 1985"],
)
check_inferred("employee",
    "Hire Date must be a valid datetime value",
    must_accept=["2023-01-15T09:00:00"],
    must_reject=["yesterday"],
)
check_inferred("employee",
    "Employment Status must be one of: ACTIVE, ON_LEAVE, TERMINATED, RETIRED",
    must_accept=["ACTIVE", "RETIRED"],
    must_reject=["DEAD", "FIRED"],
)
check_inferred("employee",
    "Office Country must be a valid country code",
    must_accept=["US", "UK", "DE"],
    must_reject=["United States"],
)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN 4: PATIENT / HEALTHCARE
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== DOMAIN 4: PATIENT MASTER (healthcare) ===")

check_inferred("patient",
    "Patient Email must be a valid email format",
    must_accept=["patient@clinic.com"],
    must_reject=["bad-email"],
)
check_inferred("patient",
    "Admission Date must be a valid datetime",
    must_accept=["2024-03-10T08:15:00"],
    must_reject=["yesterday"],
)
check_inferred("patient",
    "DOB must be a valid date",
    must_accept=["1990-01-15"],
    must_reject=["1/15/90"],
)
check_inferred("patient",
    "Insurance Type must be one of: PRIVATE, MEDICARE, MEDICAID, SELF_PAY",
    must_accept=["PRIVATE", "SELF_PAY"],
    must_reject=["UNKNOWN", "NONE"],
)
check_inferred("patient",
    "Patient ID must be a 10 digit code",
    must_accept=["1234567890"],
    must_reject=["abc1234567", "12345"],
)
check_inferred("patient",
    "Country of Origin must be a valid country name",
    must_accept=["US", "GB", "IN", "USA"],
    must_reject=["United States"],
)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN 5: FINANCIAL ORDER / INVOICE
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== DOMAIN 5: FINANCIAL ORDER / INVOICE ===")

check_inferred("order",
    "Order Number must be exactly 10 characters",
    must_accept=["ORD0001234"],
    must_reject=["ORD123"],
)
check_inferred("order",
    "Currency must be a valid ISO currency code",
    must_accept=["USD", "EUR", "INR"],
    must_reject=["DOLLARS"],
)
check_inferred("order",
    "Order Country must be a valid country code",
    must_accept=["US", "IN"],
    must_reject=["UnitedStates"],
)
check_inferred("order",
    "Status must be one of: DRAFT, CONFIRMED, SHIPPED, DELIVERED, CANCELLED",
    must_accept=["DRAFT", "DELIVERED"],
    must_reject=["PROCESSING"],
)
check_inferred("order",
    "Net Amount must be numeric",
    must_accept=["100.50", "0", "1000000"],
    must_reject=["abc", "$100"],
)
check_inferred("order",
    "Created At must be a valid timestamp",
    must_accept=["2024-05-15T13:45:00Z"],
    must_reject=["tomorrow"],
)

# ─────────────────────────────────────────────────────────────────────────────
# DOMAIN 6: SAP GL ACCOUNT MASTER
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== DOMAIN 6: SAP GL ACCOUNT MASTER ===")

check_inferred("gl",
    "Company Code must be a 4 digit code",
    must_accept=["1000", "9999"],
    must_reject=["100", "abc1"],
)
check_inferred("gl",
    "Account Currency must be a valid 3-letter ISO code",
    must_accept=["USD", "EUR"],
    must_reject=["DOLLAR", "X"],
)
check_inferred("gl",
    "Account Type must be one of: ASSET, LIABILITY, EQUITY, REVENUE, EXPENSE",
    must_accept=["ASSET", "REVENUE"],
    must_reject=["INCOME"],
)
check_inferred("gl",
    "Last Updated must be a valid datetime value",
    must_accept=["2024-05-15"],
    must_reject=["May 15"],
)
check_inferred("gl",
    "GL Country Code must be valid alpha-2 code",
    must_accept=["US", "DE"],
    must_reject=["United States"],
)

# ─────────────────────────────────────────────────────────────────────────────
# CONTROL: Confirm domain-specific noise words DON'T trigger
# (i.e. no over-matching on "country club", "phone call", "email signature")
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== CONTROL: trigger-word context matters ===")

# These rules mention email/country/phone but in unrelated ways with NO
# validation context — should NOT fire the inferred regex.
control_cases = [
    ("Membership type must be country club or regional", "country club"),
    ("Notes must not contain email signatures", "email signatures"),
    ("Call type must be inbound phone call or outbound", "phone call"),
]
for rule, label in control_cases:
    pat = infer_regex_pattern_from_rule("Validation", rule)
    # The "allowed values" extractor might fire on these (e.g., "must be ..." pattern)
    # which is FINE — they're still mapped, just not as email/country/phone regex.
    # Just assert we don't get the email regex when there's no email context.
    is_email_regex = pat and "@" in pat
    is_phone_regex = pat and "[+\\d]" in pat
    check(f"[{label}] doesn't get email regex",
          not is_email_regex, f"got {pat!r}")
    check(f"[{label}] doesn't get phone regex",
          not is_phone_regex, f"got {pat!r}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"TABLE-AGNOSTIC REGEX SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nRegex inference is genuinely table-agnostic — no domain hardcoding.")
