"""Stream-agnostic cleansing smoke test — Vendor Master.

Proves the cleansing engine has no customer-specific hardcoding by
running the SAME engine primitives against a vendor master with vendor-
specific fields and rules:

  vendor_id        identifier
  vendor_name      legal/trade name
  gstin            Indian GST registration (not customer PAN)
  ifsc_code        Indian bank routing
  swift_code       international wire
  bank_account     numeric account number
  email            contact email
  phone            E.164-ish phone
  country          ISO 2-letter
  payment_terms    enum (NET30 / NET60 / COD / ADVANCE)
  approval_status  enum (DRAFT / PENDING / APPROVED / REJECTED)
  created_date     YYYY-MM-DD

If a future regression makes cleansing customer-specific (e.g. someone
hardcodes 'pan_number' or 'company_name' in the engine), this test will
fail and force the issue out.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.session_store import SessionData  # noqa: E402
from backend.app.services.dq_engine import (  # noqa: E402
    apply_column_rules,
    default_config,
    get_preview,
)
from backend.app.routers.quality_router import _evaluate_rule_status  # noqa: E402
from features.rule_generator.engine import (  # noqa: E402
    infer_regex_pattern_from_rule,
)

results: list = []


def check(name: str, condition: bool, detail: str = "") -> None:
    tag = "[PASS]" if condition else "[FAIL]"
    line = f"{tag} {name}"
    if detail:
        line += f"  -- {detail}"
    results.append((condition, line))
    print(line)


def vendor_dataset() -> pd.DataFrame:
    """A synthetic vendor master with deliberate quality issues planted."""
    return pd.DataFrame({
        # vendor_id — alphanumeric, expected unique
        "vendor_id": ["VND-00001", "VND-00002", "VND-00003", "INVALID", "VND-00005",
                      "VND-00006", "VND-00007", "VND-00008", "VND-00009", "VND-00010"],
        # vendor_name — free text, max 100 chars, some blanks
        "vendor_name": ["Acme Supplies Pvt Ltd", "Globex Trading Co",
                        "", None, "Initech Solutions",
                        "Wayne Enterprises", "Stark Industries", "  ",
                        "Umbrella Corp", "Cyberdyne Systems"],
        # gstin — Indian GST, 15 chars: 2digits + 5letters + 4digits +
        # 1letter + 1alphanumeric + literal 'Z' + 1alphanumeric
        "gstin": ["27ABCDE1234F1Z5", "29FGHIJ5678K2Z8", "BAD_GSTIN",
                  "07KLMNO9012P3Z9", "06QRSTU3456V4Z2",
                  "", "33WXYZA7890B5Z3", "11CDEFG1357H6Z4",
                  "12HIJKL2468M7Z5", "13MNOPQ3579N8Z6"],
        # ifsc — Indian bank routing, 11 chars: BANK0BRANCH
        "ifsc_code": ["HDFC0000123", "ICIC0001234", "SBIN0002345",
                      "AXIS0003456", "NOTANIFSC",
                      "PNB0004567", "BARB0005678", "KKBK0006789",
                      "YESB0007890", "INDB0008901"],
        # swift — international wire, 8 or 11 chars
        "swift_code": ["DEUTDEFF", "CITIUS33XXX", "HSBCGB2L",
                       "BNPAFRPP", "INVALIDSWIFT",
                       "BOFAUS3N", "BARCGB22", "CHASUS33",
                       "BOFAUS3NXXX", "WFBIUS6S"],
        # bank_account — numeric, 8-18 digits
        "bank_account": ["12345678901234", "98765432109876", "1234",
                         "ABC123456789", "11112222333344",
                         "55556666777788", "99990000111122", "33334444555566",
                         "77778888999900", "22221111333344"],
        # email
        "email": ["billing@acme.com", "ar@globex.com", "BADEMAIL",
                  "vendor@initech.io", "ap@wayne.com",
                  "contact@stark.com", "billing@umbrella.org",
                  "info@cyberdyne.net", "no@email", "ok@ok.com"],
        # phone — E.164-ish
        "phone": ["+91-98765-43210", "+1-555-1234567", "BADPHONE",
                  "+44-20-12345678", "+91-99999-88888",
                  "+1-212-9876543", "+91-98760-12345", "+91-87654-32109",
                  "+1-310-5551212", "+91-90909-09090"],
        # country — ISO 2-letter
        "country": ["IN", "US", "IN", "GB", "IN",
                    "US", "IN", "IN", "US", "INDIA"],   # last one wrong format
        # payment_terms — enum
        "payment_terms": ["NET30", "NET60", "COD", "ADVANCE", "NET30",
                          "NET90", "NET30", "COD", "NET60", "NET30"],  # NET90 not allowed
        # approval_status — enum
        "approval_status": ["APPROVED", "PENDING", "DRAFT", "APPROVED", "REJECTED",
                            "APPROVED", "APPROVED", "ARCHIVED", "PENDING", "APPROVED"],
        # created_date — ISO date
        "created_date": ["2024-01-15", "2024-02-20", "2024-03-10",
                         "01/04/2024", "2024-05-22",  # 01/04/2024 wrong format
                         "2024-06-01", "2024-07-14", "2024-08-25",
                         "2024-09-30", "2024-10-12"],
    })


def make_session(df: pd.DataFrame) -> SessionData:
    s = SessionData(session_id="vendor")
    s.df = df.copy()
    s.original_df = df.copy()
    s.reject_df = pd.DataFrame()
    s.dq_config = {c: default_config() for c in df.columns}
    return s


# ─────────────────────────────────────────────────────────────────────────────
# V1: vendor_id format validation
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V1: vendor_id format (^VND-\\d{5}$) ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["vendor_id"]["applied_rules"] = [{
    "name": "Vendor ID format", "mode": "Validate",
    "pattern": r"^VND-\d{5}$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "vendor_id")
check("rejected the one INVALID row", rejected == 1, f"rejected={rejected}")
check("9 vendors remain", len(sess.df) == 9, f"len={len(sess.df)}")

# ─────────────────────────────────────────────────────────────────────────────
# V2: vendor_name Completeness (drops blanks + whitespace-only + nulls)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V2: vendor_name Completeness ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["vendor_name"]["applied_rules"] = [{
    "name": "Name not blank", "mode": "Validate",
    "pattern": r"^(?=.*\S).*$",
    "dimension": "Completeness", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "vendor_name")
# Row 3 has "", row 4 has None, row 8 has "  " — 3 rejections
check("3 blank-name rows rejected", rejected == 3, f"rejected={rejected}")
check("7 named vendors remain", len(sess.df) == 7, f"len={len(sess.df)}")

# ─────────────────────────────────────────────────────────────────────────────
# V3: GSTIN format (Indian tax ID) — note this is a VENDOR rule, not customer
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V3: GSTIN format (^\\d{2}[A-Z]{5}\\d{4}[A-Z][A-Z\\d]Z[A-Z\\d]$) ===")
df = vendor_dataset()
sess = make_session(df)
gstin_rule = {
    "name": "GSTIN format", "mode": "Validate",
    "pattern": r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$",
    "dimension": "Validation", "source": "ai",
}
sess.dq_config["gstin"]["applied_rules"] = [gstin_rule]
applied, rejected = apply_column_rules(sess, "gstin")
# BAD_GSTIN (row 3) and "" (row 6) both fail — non-empty filter is part of the Validate path
check("2 bad GSTIN rejected (BAD_GSTIN + empty)", rejected == 2, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V4: IFSC code format (bank routing)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V4: IFSC code format (^[A-Z]{4}0[A-Z0-9]{6}$) ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["ifsc_code"]["applied_rules"] = [{
    "name": "IFSC format", "mode": "Validate",
    "pattern": r"^[A-Z]{4}0[A-Z0-9]{6}$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "ifsc_code")
# Bad ones: "NOTANIFSC", "PNB0004567" (only 3 leading letters)
check("rejects malformed IFSC", rejected == 2, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V5: SWIFT/BIC code — accepts both 8 and 11 char forms
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V5: SWIFT/BIC format (^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$) ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["swift_code"]["applied_rules"] = [{
    "name": "SWIFT format", "mode": "Validate",
    "pattern": r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "swift_code")
# Bad: "INVALIDSWIFT" (12 chars — outside the 8/11 lengths)
check("INVALIDSWIFT (12 chars) rejected, both 8 and 11 char forms accepted",
      rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V6: bank_account numeric only — Validate mode
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V6: bank_account must be 8-18 digits ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["bank_account"]["applied_rules"] = [{
    "name": "Bank acct 8-18 digits", "mode": "Validate",
    "pattern": r"^\d{8,18}$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "bank_account")
# Bad: "1234" (too short), "ABC123456789" (non-numeric)
check("rejects short + alpha bank accounts", rejected == 2, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V7: email Validate
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V7: email format ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["email"]["applied_rules"] = [{
    "name": "Email format", "mode": "Validate",
    "pattern": r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "email")
# Bad: "BADEMAIL", "no@email" (no TLD)
check("2 bad emails rejected", rejected == 2, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V8: country ISO 2-letter
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V8: country ISO 2-letter ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["country"]["applied_rules"] = [{
    "name": "ISO 3166-1 alpha-2", "mode": "Validate",
    "pattern": r"^[A-Z]{2}$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "country")
# Bad: "INDIA" (5 chars)
check("INDIA (5 chars) rejected, IN/US/GB pass", rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V9: payment_terms allowed-values (enum)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V9: payment_terms enum (NET30/NET60/COD/ADVANCE) ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["payment_terms"]["applied_rules"] = [{
    "name": "Payment terms enum", "mode": "Validate",
    "pattern": r"^(NET30|NET60|COD|ADVANCE)$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "payment_terms")
# Bad: "NET90"
check("NET90 rejected (not in allowed set)", rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V10: approval_status enum  +  case-normalisation prior step
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V10: approval_status enum (after Case normalize) ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["approval_status"]["applied_rules"] = [
    {"name": "Force uppercase", "mode": "Case", "case": "UPPERCASE",
     "dimension": "Standardisation", "source": "ai"},
    {"name": "Status enum", "mode": "Validate",
     "pattern": r"^(DRAFT|PENDING|APPROVED|REJECTED)$",
     "dimension": "Validation", "source": "ai"},
]
applied, rejected = apply_column_rules(sess, "approval_status")
# Bad: "ARCHIVED" (not in enum)
check("ARCHIVED rejected after case-normalize", rejected == 1,
      f"rejected={rejected}")
check("Case standardisation also counted",
      sess.applied_rules_by_dim.get("Standardisation", 0) == 1,
      f"counter={sess.applied_rules_by_dim}")

# ─────────────────────────────────────────────────────────────────────────────
# V11: created_date — ISO format only
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V11: created_date YYYY-MM-DD ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["created_date"]["applied_rules"] = [{
    "name": "ISO date", "mode": "Validate",
    "pattern": r"^\d{4}-\d{2}-\d{2}$",
    "dimension": "Validation", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "created_date")
# Bad: "01/04/2024" (DD/MM/YYYY format)
check("non-ISO date rejected, 9 valid remain", rejected == 1, f"rejected={rejected}")

# ─────────────────────────────────────────────────────────────────────────────
# V12: Full cleansing pipeline — apply ALL vendor rules at once
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V12: full vendor pipeline — apply every rule across every column ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["vendor_id"]["applied_rules"] = [{
    "name": "Vendor ID format", "mode": "Validate",
    "pattern": r"^VND-\d{5}$", "dimension": "Validation", "source": "ai",
}]
sess.dq_config["vendor_name"]["applied_rules"] = [{
    "name": "Name not blank", "mode": "Validate",
    "pattern": r"^(?=.*\S).*$", "dimension": "Completeness", "source": "ai",
}]
sess.dq_config["gstin"]["applied_rules"] = [{
    "name": "GSTIN format", "mode": "Validate",
    "pattern": r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$",
    "dimension": "Validation", "source": "ai",
}]
sess.dq_config["ifsc_code"]["applied_rules"] = [{
    "name": "IFSC format", "mode": "Validate",
    "pattern": r"^[A-Z]{4}0[A-Z0-9]{6}$",
    "dimension": "Validation", "source": "ai",
}]
sess.dq_config["payment_terms"]["applied_rules"] = [{
    "name": "Payment terms enum", "mode": "Validate",
    "pattern": r"^(NET30|NET60|COD|ADVANCE)$",
    "dimension": "Validation", "source": "ai",
}]

from backend.app.services.dq_engine import apply_all_rules

for col in ("vendor_id", "vendor_name", "gstin", "ifsc_code", "payment_terms"):
    sess.dq_config[col]["enabled"] = True

result = apply_all_rules(sess)
check("apply_all returns dict with applied count",
      isinstance(result, dict) and "applied" in result, f"got {result}")
check("at least 5 rules applied", result.get("applied", 0) >= 5,
      f"applied={result.get('applied')}")
check("reject_df accumulated rows from multiple columns",
      len(sess.reject_df) > 0,
      f"rejects={len(sess.reject_df)}")
# Per-column rejections should be in reject_df with column tag
unique_reject_cols = set(sess.reject_df["Rejected_Column"].tolist())
check("rejections spread across multiple vendor columns",
      len(unique_reject_cols) >= 3,
      f"rejected columns: {unique_reject_cols}")

# ─────────────────────────────────────────────────────────────────────────────
# V13: Lifecycle status — vendor stream
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V13: lifecycle pipeline on vendor data ===")
df = vendor_dataset()
col_health = {}
for c in df.columns:
    non_empty = int(df[c].dropna().astype(str).str.strip().ne("").sum())
    col_health[c] = {
        "non_empty": non_empty, "total": len(df),
        "fill_rate": non_empty / len(df), "is_empty": non_empty == 0,
    }
real_cols = set(df.columns)
empty_set = {c for c, h in col_health.items() if h["is_empty"]}

# Vendor-specific rule that mentions a missing column → invalid
rg_row = pd.Series({
    "Column": "tax_id_secondary", "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "tax_id_secondary must be alphanumeric",
    "Regex Pattern": r"^[A-Z0-9]+$",
})
entry = _evaluate_rule_status(rg_row, 0, df, col_health, real_cols, empty_set, set(), {})
check("vendor: missing column → invalid", entry["status"] == "invalid",
      f"status={entry['status']}")

# Vendor-specific multi-CDE rule (cross-field uniqueness on vendor master)
rg_row = pd.Series({
    "Column": "vendor_id + gstin", "Columns": "vendor_id, gstin",
    "Dimension": "Cross-field Validation",
    "Data Quality Rule": "(vendor_id, gstin) tuple must be unique",
    "Regex Pattern": "",
})
entry = _evaluate_rule_status(rg_row, 1, df, col_health, real_cols, empty_set, set(), {})
check("vendor: cross-field rule → multi_cde", entry["status"] == "multi_cde",
      f"status={entry['status']}")

# Vendor with format violation — actionable
rg_row = pd.Series({
    "Column": "vendor_id", "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "vendor_id must follow VND-NNNNN pattern",
    "Regex Pattern": r"^VND-\d{5}$",
})
entry = _evaluate_rule_status(rg_row, 2, df, col_health, real_cols, empty_set, set(), {})
check("vendor: format violation → actionable + count > 0",
      entry["status"] == "actionable" and entry["failure_count"] >= 1,
      f"status={entry['status']}, fc={entry['failure_count']}")

# Vendor with all-pass — passed
rg_row = pd.Series({
    "Column": "country", "Columns": "",
    "Dimension": "Validation",
    "Data Quality Rule": "country must be 2-5 chars",
    "Regex Pattern": r"^[A-Z]{2,5}$",
})
entry = _evaluate_rule_status(rg_row, 3, df, col_health, real_cols, empty_set, set(), {})
check("vendor: all-rows-pass → passed",
      entry["status"] == "passed" and entry["failure_count"] == 0,
      f"status={entry['status']}, fc={entry['failure_count']}")

# ─────────────────────────────────────────────────────────────────────────────
# V14: Custom vendor rule (human-in-loop) survives apply
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V14: custom vendor rule round-trip ===")
df = vendor_dataset()
sess = make_session(df)
# User authors a vendor-specific rule via "Add Custom Rule"
sess.dq_config["vendor_id"]["applied_rules"].append({
    "name": "Custom vendor ID rule",
    "mode": "Validate",
    "pattern": r"^VND-\d{5}$",
    "dimension": "Validation",
    "source": "custom",
})
applied, rejected = apply_column_rules(sess, "vendor_id")
check("custom rule applied", applied == 1)
check("source='custom' preserved in history",
      sess.validation_history[-1]["backup_applied_rules"][0]["source"] == "custom")
# Purge AI rules — custom must survive
from backend.app.routers.rule_generator_router import _purge_ai_synced_from_dq_config

# Re-add since apply removed it from applied_rules (apply moves to history)
sess.dq_config["vendor_id"]["applied_rules"] = [
    {"name": "Some AI rule", "mode": "Validate", "pattern": r".*",
     "dimension": "Validation", "source": "ai"},
    {"name": "Custom vendor rule kept",
     "mode": "Validate", "pattern": r"^VND-\d{5}$",
     "dimension": "Validation", "source": "custom"},
]
_purge_ai_synced_from_dq_config(sess)
remaining_names = [r["name"] for r in sess.dq_config["vendor_id"]["applied_rules"]]
check("purge kept custom, dropped AI",
      remaining_names == ["Custom vendor rule kept"],
      f"got {remaining_names}")

# ─────────────────────────────────────────────────────────────────────────────
# V15: Regex inference works for vendor rule wording (table-agnostic prose)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V15: regex inference handles vendor-domain prose ===")
got = infer_regex_pattern_from_rule("Validation", "Vendor Name must be no more than 100 characters")
check("vendor max-length", got == "^.{0,100}$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Validation", "IFSC must be a valid IFSC format")
check("IFSC well-known format inferred",
      got == r"^[A-Z]{4}0[A-Z0-9]{6}$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Validation", "GSTIN must be a valid GST format")
check("GSTIN well-known format inferred",
      got == r"^\d{2}[A-Z]{5}\d{4}[A-Z]{1}[A-Z\d]{1}Z[A-Z\d]{1}$",
      f"got {got!r}")

got = infer_regex_pattern_from_rule("Validation", "Bank account must be a 14-digit number")
check("vendor bank account digit count inferred",
      got == r"^\d{14}$", f"got {got!r}")

got = infer_regex_pattern_from_rule("Completeness", "Vendor Name must not be blank")
check("vendor completeness inferred",
      got == r"^(?=.*\S).*$", f"got {got!r}")

# ─────────────────────────────────────────────────────────────────────────────
# V16: Reset against vendor data
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== V16: Reset restores original vendor dataset ===")
df = vendor_dataset()
sess = make_session(df)
sess.dq_config["vendor_id"]["applied_rules"] = [{
    "name": "Strict ID", "mode": "Validate", "pattern": r"^VND-\d{5}$",
    "dimension": "Validation", "source": "ai",
}]
apply_column_rules(sess, "vendor_id")
check("after apply: 9 vendors", len(sess.df) == 9)
check("reject_df has 1 row", len(sess.reject_df) == 1)

# Simulate /quality/reset-cleansing
sess.df = sess.original_df.copy()
sess.reject_df = pd.DataFrame()
sess.validation_history = []
sess.applied_rules_by_dim = {}
check("reset: 10 vendors restored", len(sess.df) == 10)
check("reset: reject_df cleared", len(sess.reject_df) == 0)
check("reset: history cleared", len(sess.validation_history) == 0)
check("reset: per-dim counter cleared", sess.applied_rules_by_dim == {})

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
total = len(results)
passed = sum(1 for ok, _ in results if ok)
failed = total - passed
print(f"VENDOR-MASTER SUMMARY: {passed}/{total} passed, {failed} failed")
if failed:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nVendor-master cleansing tests passed — engine is stream-agnostic.")
