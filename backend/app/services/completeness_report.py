"""Per-field Completeness analysis — Phase 2 of the Data Profiling rebuild.

Mirrors Sheet 1 ("Completeness Assessment") of the reference DAMA workbook:

  Summary block:
     Total Fields  |  100% Complete  |  95-99%  |  50-94%  |  <50%  |  Empty (0%)
     Overall Fill Rate

  Field-level table (one row per column):
     # · Field Name · Total Records · Filled · Blank · Fill Rate % · Status

Status uses the same thresholds as the reference (≥95 → Complete, ≥90 →
Acceptable, ≥50 → Low, >0 → Critical, 0 → Empty).

The report enriches each field with the AI signals already available on
the project — semantic_type and the recommended-CDE flag — so stewards
can sort / filter by "blanks on CDEs only" in the picker UI.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


# Thresholds chosen to match the reference workbook's bucketing.
_BUCKETS = [
    ("Complete (100%)",   lambda f: f >= 1.0),
    ("Acceptable (95-99%)", lambda f: 0.95 <= f < 1.0),
    ("Low (50-94%)",        lambda f: 0.50 <= f < 0.95),
    ("Critical (<50%)",     lambda f: 0.0  <  f < 0.50),
    ("Empty (0%)",          lambda f: f <= 0.0),
]


def _status_for(fill_rate: float, is_cde: bool) -> str:
    """One-word status label.

    A CDE with anything less than 100% fill is at least "Watch" — we treat
    blanks on identifiers as a stronger signal than blanks on descriptive
    fields. Otherwise thresholds match the reference workbook.
    """
    if fill_rate >= 0.999:
        return "Complete"
    if fill_rate <= 0:
        return "Empty"
    if fill_rate < 0.50:
        return "Critical"
    if fill_rate < 0.90:
        return "Low"
    if fill_rate < 0.95:
        return "Watch" if is_cde else "Acceptable"
    return "Acceptable"


def compute_completeness_report(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]] = None,
    project_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the Completeness report.

    Returns a structure the frontend can render directly:

        {
          "summary": {
              "total_fields": N,
              "buckets": [{label, count}, ...],
              "overall_fill_rate": 0.0–1.0,
              "rows": N,
              "cde_count": N,
              "cde_fill_rate": 0.0–1.0  (or None if no CDEs tagged),
          },
          "fields": [
              {
                "rank": 1,
                "field": "LIFNR",
                "total": 9722,
                "filled": 9722,
                "blank": 0,
                "fill_rate": 1.0,
                "status": "Complete",
                "semantic_type": "numeric_id",
                "is_cde": true,
              },
              ...
          ],
          "project_context": {...},
        }
    """
    if df is None or df.empty:
        return {
            "summary": {
                "total_fields": 0,
                "buckets": [{"label": label, "count": 0} for label, _ in _BUCKETS],
                "overall_fill_rate": 0.0,
                "rows": 0,
                "cde_count": 0,
                "cde_fill_rate": None,
            },
            "fields": [],
            "project_context": project_context or {},
        }

    rows = int(len(df))
    glossary = glossary or {}

    field_records: List[Dict[str, Any]] = []
    total_cells = 0
    total_filled = 0
    cde_cells = 0
    cde_filled = 0

    for col in df.columns:
        name = str(col)
        series = df[col]
        filled = int(series.notna().sum())
        blank = rows - filled
        fill_rate = (filled / rows) if rows else 0.0

        meta = glossary.get(name) if isinstance(glossary.get(name), dict) else {}
        is_cde = bool(meta.get("recommended"))
        semantic_type = (meta.get("semantic_type") or "").lower() or None

        total_cells += rows
        total_filled += filled
        if is_cde:
            cde_cells += rows
            cde_filled += filled

        field_records.append({
            "field": name,
            "total": rows,
            "filled": filled,
            "blank": blank,
            "fill_rate": round(fill_rate, 4),
            "status": _status_for(fill_rate, is_cde),
            "semantic_type": semantic_type,
            "is_cde": is_cde,
        })

    # Sort ascending by fill rate so the worst fields surface first; ties
    # broken by field name for stable rendering.
    field_records.sort(key=lambda r: (r["fill_rate"], r["field"]))
    for i, rec in enumerate(field_records, start=1):
        rec["rank"] = i

    # Bucket counts.
    bucket_counts = []
    for label, predicate in _BUCKETS:
        bucket_counts.append({
            "label": label,
            "count": sum(1 for r in field_records if predicate(r["fill_rate"])),
        })

    overall = (total_filled / total_cells) if total_cells else 0.0
    cde_fill = (cde_filled / cde_cells) if cde_cells else None

    return {
        "summary": {
            "total_fields": len(field_records),
            "buckets": bucket_counts,
            "overall_fill_rate": round(overall, 4),
            "rows": rows,
            "cde_count": sum(1 for r in field_records if r["is_cde"]),
            "cde_fill_rate": round(cde_fill, 4) if cde_fill is not None else None,
        },
        "fields": field_records,
        "project_context": project_context or {},
    }
