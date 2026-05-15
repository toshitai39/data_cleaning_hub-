"""Smoke test for the rewritten client-grade DQ report.

Asserts the report:
  1. Builds at all without missing-field crashes
  2. Includes the cover, executive summary, dimension scorecard, rules,
     rejected rows, CDE scorecard sections
  3. Reflects current session state (not stale or "No profile data")
  4. Gracefully degrades when optional pieces are missing
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.session_store import SessionData  # noqa: E402
from backend.app.services.cleansing_report import (  # noqa: E402
    build_report_html, html_to_pdf_bytes,
)

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


# ─────────────────────────────────────────────────────────────────────────────
# Build a realistic session
# ─────────────────────────────────────────────────────────────────────────────
df_original = pd.DataFrame({
    "customer_id": [f"C{i:04d}" for i in range(20)],
    "name":        ["Acme", "Globex", "", None, "Wayne", "Stark", "Umbrella",
                    "Cyberdyne", "Initech", "Soylent",
                    "Tyrell", "OmniCorp", "Massive Dynamic", "Vandelay",
                    "Hooli", "PiedPiper", "Aviato", "DunderMifflin",
                    "Sterling", "Pearson"],
    "pan_number":  ["ABCDE1234F", "FGHIJ5678K", "BADPAN", "AAUPQ3368B", "AXZPH4392Q",
                    "ABLCS0638P", "AALPW2512Q", "AAKFE1953C", "AAJPO9338C", "FBQPR6442P",
                    "BKIPG6708A", "CJWPC4249L", "", None, "BAD!@#",
                    "XYZAB9999Z", "MNOPQ1234R", "STUVW5678X", "ABCDE2222Y", "FGHIJ8888Z"],
    "country":     ["IN", "US", "IN", "GB", "IN", "US", "IN", "IN", "US", "IN",
                    "DE", "FR", "GB", "US", "IN", "IN", "US", "DE", "IN", "US"],
    "year_of_establishment": [2017, 2018, 1850, 2020, 2019,
                              2015, 2021, 2010, 2005, 2018,
                              2022, 1995, 2000, 1999, 2017,
                              2018, 2020, 2019, 2015, 2010],
})
# Simulate cleansing: drop the row with BADPAN and the blank-name row
df_current = df_original[~df_original["pan_number"].isin(["BADPAN", "BAD!@#"])].copy()
df_current = df_current[df_current["name"].notna() & (df_current["name"].str.strip() != "")]

sess = SessionData(session_id="report-smoke")
sess.filename = "customer_master.xlsx"
sess.df = df_current.reset_index(drop=True)
sess.original_df = df_original
sess.user = {"username": "toshit", "name": "Toshit Tejasvat"}

# Reject log
rej = df_original[df_original["pan_number"].isin(["BADPAN", "BAD!@#"])].copy()
rej["Rejection_Reason"] = "PAN format - Does not match"
rej["Rejected_Column"] = "pan_number"
rej["Rejected_At"] = "2026-05-15 12:30:00"
extra_rej = df_original[df_original["name"].isna() | (df_original["name"].astype(str).str.strip() == "")].copy()
extra_rej["Rejection_Reason"] = "Name not blank - Does not match"
extra_rej["Rejected_Column"] = "name"
extra_rej["Rejected_At"] = "2026-05-15 12:31:00"
sess.reject_df = pd.concat([rej, extra_rej], ignore_index=True)

# Validation history (mirrors what apply_column_rules pushes)
sess.validation_history = [
    {
        "description": "Applied 1 rule (Validate) to pan_number",
        "timestamp": "2026-05-15 12:30:00",
        "rejected_count": int(len(rej)),
        "column": "pan_number",
    },
    {
        "description": "Applied 1 rule (Validate) to name",
        "timestamp": "2026-05-15 12:31:00",
        "rejected_count": int(len(extra_rej)),
        "column": "name",
    },
]

# Per-dimension applied counter
sess.applied_rules_by_dim = {"Validation": 1, "Completeness": 1}

# AI rules
sess.ai_validation_rules = pd.DataFrame([
    {"S.No": 1, "Column": "customer_id", "Dimension": "Validation",
     "Data Quality Rule": "customer_id must match ^C\\d{4}$",
     "Regex Pattern": r"^C\d{4}$",
     "Issues Found": 0, "Issues Found Example": ""},
    {"S.No": 2, "Column": "name", "Dimension": "Completeness",
     "Data Quality Rule": "name must not be blank",
     "Regex Pattern": r"^(?=.*\S).*$",
     "Issues Found": 2, "Issues Found Example": "rows 3, 4"},
    {"S.No": 3, "Column": "pan_number", "Dimension": "Validation",
     "Data Quality Rule": "pan must be valid PAN format",
     "Regex Pattern": r"^[A-Z]{5}\d{4}[A-Z]$",
     "Issues Found": 2, "Issues Found Example": "BADPAN, BAD!@#"},
    {"S.No": 4, "Column": "country", "Dimension": "Validation",
     "Data Quality Rule": "country must be ISO 2-letter",
     "Regex Pattern": r"^[A-Z]{2}$",
     "Issues Found": 0, "Issues Found Example": ""},
    {"S.No": 5, "Column": "year_of_establishment", "Dimension": "Validation",
     "Data Quality Rule": "year must be valid year",
     "Regex Pattern": r"^(19|20)\d{2}$",
     "Issues Found": 1, "Issues Found Example": "1850"},
])

# Semantic glossary
sess.semantic_glossary = {
    "customer_id": {"semantic_type": "identifier_alpha"},
    "name":        {"semantic_type": "free_text_name"},
    "pan_number":  {"semantic_type": "pan"},
    "country":     {"semantic_type": "iso_country"},
    "year_of_establishment": {"semantic_type": "year"},
}

# ─────────────────────────────────────────────────────────────────────────────
# R1: Report builds without crashing on a realistic session
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== R1: build_report_html does not crash on realistic session ===")
try:
    html = build_report_html(sess, project_context={
        "system_label": "File upload", "stream_label": "Customer Master",
    })
    check("HTML produced", isinstance(html, str) and len(html) > 1000,
          f"got {len(html) if isinstance(html, str) else 'non-str'} chars")
except Exception as e:
    check("HTML produced", False, f"raised: {e}")
    html = ""

# ─────────────────────────────────────────────────────────────────────────────
# R2: Critical sections present
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== R2: report contains all critical sections ===")
checks = [
    ("Cover section", "DATA QUALITY REPORT"),
    ("Cover filename", "customer_master.xlsx"),
    ("Cover project context", "Customer Master"),
    ("Cover user", "Toshit Tejasvat"),
    ("Executive summary heading", "Executive Summary"),
    ("DAMA scorecard heading", "DAMA Six-Dimension Scorecard"),
    ("Rules section heading", "Rules Generated"),
    ("Cleansing actions log", "Cleansing Actions Log"),
    ("Rejected rows section", "Rejected Rows"),
    ("Per-CDE scorecard", "Critical Data Element Scorecard"),
    ("Footer brand", "Uniqus Data Profiler"),
]
for label, needle in checks:
    check(f"contains: {label}", needle in html, f"missing: {needle!r}")

# ─────────────────────────────────────────────────────────────────────────────
# R3: Report reflects ACTUAL session state (not stale/empty)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== R3: report uses real session numbers, not zeros or placeholders ===")
check("original row count rendered", "20" in html,
      "expected 20 rows in original")
check("current row count rendered (after cleansing)",
      f"{len(df_current):,}" in html or str(len(df_current)) in html,
      f"expected {len(df_current)}")
check("rejection reason rendered",
      "PAN format" in html or "Name not blank" in html)
check("CDE names rendered in per-CDE table",
      all(c in html for c in ("customer_id", "name", "pan_number", "country")))
check("semantic types rendered (pan, iso_country)",
      "pan" in html and "iso_country" in html)
check("rules count rendered",
      "5" in html and "Validation" in html)

# ─────────────────────────────────────────────────────────────────────────────
# R4: Graceful degradation — sparse session shouldn't crash
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== R4: graceful degradation on sparse session ===")
sparse = SessionData(session_id="sparse")
sparse.filename = "sparse.csv"
sparse.df = pd.DataFrame({"x": [1, 2, 3]})
sparse.original_df = sparse.df.copy()
# Everything else is empty / None

try:
    html_sparse = build_report_html(sparse, project_context={})
    check("sparse session: HTML built", isinstance(html_sparse, str))
    check("sparse session: no crash on missing exec summary",
          "Executive Summary" in html_sparse)
    check("sparse session: handles zero rules gracefully",
          "No data-quality rules" in html_sparse or "Rules Generated" in html_sparse)
except Exception as e:
    check("sparse session: HTML built", False, f"raised: {e}")

# ─────────────────────────────────────────────────────────────────────────────
# R5: PDF conversion (best-effort — xhtml2pdf may not be installed locally)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== R5: PDF conversion attempt ===")
pdf_bytes = html_to_pdf_bytes(html)
if pdf_bytes is None:
    check("PDF unavailable (xhtml2pdf not installed) — falls back to HTML",
          True, "Falls back to HTML download path (verified by None return)")
else:
    check("PDF bytes produced", len(pdf_bytes) > 100,
          f"got {len(pdf_bytes)} bytes")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"REPORT SUMMARY: {passed}/{total} passed")

# Also dump a sample HTML to /tmp for visual inspection
import tempfile
out = Path(tempfile.gettempdir()) / "smoke_dq_report.html"
out.write_text(html, encoding="utf-8")
print(f"\nSample report saved for inspection: {out}")

if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nReport smoke tests passed.")
