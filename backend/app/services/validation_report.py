"""Per-attribute format Validation report — Phase 3 of the rebuild.

Mirrors Sheet 2 of the reference DAMA workbook: for every column the AI
recommender classified as a typed identifier (PAN / GSTIN / Email /
postal / IBAN / SWIFT / IFSC / ISO country / ISO currency / etc.), run
the standards-body regex against the actual values and report:

  - records with the field populated
  - count + share of valid values
  - count + share of invalid values
  - count + share of blank values
  - up to 10 sample invalid rows (row number + raw value)

The format catalog itself lives in ``dama_assessment._FORMAT_CHECKS`` —
re-used as the single source of truth so Validation scoring on the
Executive Summary and the detail view always agree.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional

import pandas as pd

from .dama_assessment import _FORMAT_CHECKS, _semantic_type_of


_SEMANTIC_TYPE_LABEL = {
    "pan":          "PAN",
    "gstin":        "GSTIN",
    "tan":          "TAN",
    "cin":          "CIN",
    "ein":          "EIN (US)",
    "ssn":          "SSN (US)",
    "aadhaar":      "Aadhaar",
    "email":        "Email Address",
    "indian_pin":   "Indian PIN code",
    "postal_code":  "Postal Code",
    "ifsc":         "IFSC (India)",
    "iban":         "IBAN",
    "swift":        "SWIFT / BIC",
    "iso_country":  "ISO Country Code",
    "iso_currency": "ISO Currency Code",
    "phone":        "Phone Number",
    "url":          "URL",
    "year":         "Year",
}


_SEMANTIC_TYPE_RULE = {
    "pan":          "5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)",
    "gstin":        "15 chars: 2 state digits + 10-char PAN + 1 entity digit + Z + 1 check char",
    "tan":          "4 letters + 5 digits + 1 letter",
    "cin":          "21 chars: L/U + 5 digits + 2-letter state + 4-digit year + 3-letter class + 6-digit number",
    "ein":          "9 digits, optionally formatted XX-XXXXXXX",
    "ssn":          "9 digits, optionally formatted XXX-XX-XXXX",
    "aadhaar":      "12 digits, optionally separated into groups of four",
    "email":        "Standard RFC-style local@domain.tld",
    "indian_pin":   "6 digits, first digit non-zero",
    "postal_code":  "Alphanumeric, 3–12 characters",
    "ifsc":         "4 letters + '0' + 6 alphanumerics",
    "iban":         "Country code + 2 check digits + up to 30 alphanumerics",
    "swift":        "6 letters + 2 alphanumerics, optional 3-char branch suffix",
    "iso_country":  "Exactly 2 uppercase letters",
    "iso_currency": "Exactly 3 uppercase letters",
    "phone":        "Digits with optional + / spaces / parens / dashes, 7+ chars",
    "url":          "Begins with http:// or https://",
    "year":         "Four-digit year between 1900 and 2099",
}


def _row_indexes_of(series: pd.Series, mask: pd.Series, limit: int = 10) -> List[Dict[str, Any]]:
    """Return up to `limit` (row_number, value) samples from a boolean mask."""
    if not mask.any():
        return []
    hits = series[mask]
    out: List[Dict[str, Any]] = []
    for idx, value in hits.head(limit).items():
        out.append({"row": int(idx) + 1, "value": "" if pd.isna(value) else str(value)})
    return out


def compute_validation_report(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]] = None,
    project_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the Validation report.

    Returns:

        {
          "summary": {
              "rows": N,
              "typed_columns": N,
              "valid_values": N, "invalid_values": N, "blank_values": N,
              "overall_validity_rate": 0.0–1.0,
          },
          "fields": [
              {
                "field": "STCD1",
                "semantic_type": "pan",
                "semantic_type_label": "PAN",
                "format_rule": "5 letters + 4 digits + 1 letter (...)",
                "records_with_value": N,
                "valid": N, "valid_pct": 0.0–1.0,
                "invalid": N, "invalid_pct": 0.0–1.0,
                "blank": N, "blank_pct": 0.0–1.0,
                "validity_rate": 0.0–1.0,
                "samples_invalid": [{"row": 241, "value": "17CHE00033"}, ...],
              },
              ...
          ],
          "skipped": [   # informational — columns the AI didn't classify
              {"field": "...", "reason": "no semantic type assigned"}
          ],
          "project_context": {...},
        }
    """
    if df is None or df.empty:
        return {
            "summary": {
                "rows": 0,
                "typed_columns": 0,
                "valid_values": 0, "invalid_values": 0, "blank_values": 0,
                "overall_validity_rate": 0.0,
            },
            "fields": [],
            "skipped": [],
            "project_context": project_context or {},
        }

    rows = int(len(df))
    glossary = glossary or {}

    fields: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    # Breakdown of "what semantic_type did the AI assign across the dataset?"
    # so the empty state on the frontend can show the steward exactly why
    # Validation has nothing to score (and whether that's expected).
    semantic_type_counts: Dict[str, int] = {}

    total_valid = 0
    total_invalid = 0
    total_blank = 0
    total_checked = 0

    for col in df.columns:
        name = str(col)
        stype = _semantic_type_of(name, glossary)
        if stype:
            semantic_type_counts[stype] = semantic_type_counts.get(stype, 0) + 1
        else:
            semantic_type_counts["(unclassified)"] = semantic_type_counts.get("(unclassified)", 0) + 1

        # Prefer an explicit regex on the glossary entry; fall back to the
        # standards catalog keyed on semantic_type.
        entry = glossary.get(name) if isinstance(glossary.get(name), dict) else {}
        raw_regex = entry.get("regex") or entry.get("pattern") if entry else None
        pattern: Optional[re.Pattern] = None
        if raw_regex:
            try:
                pattern = re.compile(raw_regex)
            except re.error:
                pattern = None
        if pattern is None and stype and stype in _FORMAT_CHECKS:
            pattern = _FORMAT_CHECKS[stype]

        if pattern is None:
            # Column either wasn't AI-classified or has a semantic type
            # we don't have a format check for (free text, numeric_id with
            # no canonical format, enum_code, …). Surface as "skipped"
            # informational rather than penalising it.
            if stype:
                skipped.append({
                    "field": name,
                    "semantic_type": stype,
                    "reason": "no canonical format check defined for this type",
                })
            else:
                skipped.append({
                    "field": name,
                    "semantic_type": None,
                    "reason": "no semantic type assigned by the AI",
                })
            continue

        series = df[col]
        blank_mask = series.isna() | (series.astype(str).str.strip() == "")
        blank = int(blank_mask.sum())
        nonblank = series[~blank_mask].astype(str)
        valid_mask = nonblank.str.match(pattern)
        valid = int(valid_mask.sum())
        records_with_value = int(len(nonblank))
        invalid = records_with_value - valid

        # Sample invalid rows from the original frame so the row numbers
        # match what the steward sees in Preview / Cleansing.
        invalid_indices = nonblank[~valid_mask].index
        samples = []
        for idx in list(invalid_indices)[:10]:
            v = series.iloc[idx] if idx < len(series) else nonblank.loc[idx]
            samples.append({"row": int(idx) + 1, "value": "" if pd.isna(v) else str(v)})

        total_checked += records_with_value
        total_valid += valid
        total_invalid += invalid
        total_blank += blank

        validity_rate = (valid / records_with_value) if records_with_value else 0.0
        fields.append({
            "field": name,
            "semantic_type": stype,
            "semantic_type_label": _SEMANTIC_TYPE_LABEL.get(stype, stype.replace("_", " ").title()),
            "format_rule": _SEMANTIC_TYPE_RULE.get(stype, "Standards-defined format"),
            "records_with_value": records_with_value,
            "valid": valid,
            "valid_pct": round(valid / rows, 4) if rows else 0,
            "invalid": invalid,
            "invalid_pct": round(invalid / rows, 4) if rows else 0,
            "blank": blank,
            "blank_pct": round(blank / rows, 4) if rows else 0,
            "validity_rate": round(validity_rate, 4),
            "samples_invalid": samples,
        })

    # Sort failing fields first so the steward sees worst-validity at top.
    fields.sort(key=lambda f: (f["validity_rate"], -f["invalid"]))

    overall = (total_valid / total_checked) if total_checked else 0.0
    # Sort the breakdown by count desc so the dominant categories surface first.
    semantic_type_breakdown = sorted(
        [{"semantic_type": k, "count": v} for k, v in semantic_type_counts.items()],
        key=lambda x: (-x["count"], x["semantic_type"]),
    )
    return {
        "summary": {
            "rows": rows,
            "typed_columns": len(fields),
            "valid_values": total_valid,
            "invalid_values": total_invalid,
            "blank_values": total_blank,
            "overall_validity_rate": round(overall, 4),
            "ai_classified_total": len([c for c in df.columns if _semantic_type_of(str(c), glossary)]),
            "semantic_type_breakdown": semantic_type_breakdown,
        },
        "fields": fields,
        "skipped": skipped,
        "project_context": project_context or {},
    }
