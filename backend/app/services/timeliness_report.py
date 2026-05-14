"""DAMA Timeliness deep-dive — per-date-column analysis.

For every datetime / date column in scope:

  - total rows
  - populated count
  - blank count
  - oldest / newest values
  - future-dated count + samples (created/updated dates in the future are
    almost always a data-entry or timezone bug)
  - very old values (configurable lower bound — defaults to "before 1990"
    which catches Epoch zero and obvious sentinel dates)
  - per-column timeliness score (1 − bad/total)

Empty when the dataset has no datetime columns — Timeliness is the one
dimension that can legitimately be N/A.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


_VERY_OLD_THRESHOLD = pd.Timestamp("1990-01-01")


def _to_naive_utc(series: pd.Series) -> pd.Series:
    """Ensure the series is timezone-naive so comparisons against ``now`` work."""
    if not pd.api.types.is_datetime64_any_dtype(series):
        return series
    try:
        if getattr(series.dt, "tz", None) is not None:
            return series.dt.tz_convert("UTC").dt.tz_localize(None)
    except Exception:
        pass
    return series


def compute_timeliness_report(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]] = None,
    project_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the Timeliness deep-dive."""
    ctx = project_context or {}
    if df is None or df.empty:
        return {
            "summary": {
                "rows": 0, "date_columns": 0,
                "total_future_rows": 0, "total_very_old_rows": 0,
                "overall_timeliness": 1.0,
            },
            "columns": [],
            "project_context": ctx,
        }

    rows = int(len(df))
    now = pd.Timestamp.utcnow().tz_localize(None)
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]

    per_col: List[Dict[str, Any]] = []
    total_future = 0
    total_very_old = 0
    total_checked = 0

    for col in date_cols:
        series = _to_naive_utc(df[col])
        non_null = series.dropna()
        n_non_null = int(len(non_null))
        n_blank = rows - n_non_null
        if n_non_null == 0:
            per_col.append({
                "column": str(col),
                "total": rows, "populated": 0, "blank": rows,
                "future_dated": 0, "very_old": 0,
                "oldest": None, "newest": None,
                "timeliness_rate": 0.0,
                "samples_future": [],
                "samples_very_old": [],
            })
            continue

        future_mask = non_null > now
        old_mask = non_null < _VERY_OLD_THRESHOLD
        future = int(future_mask.sum())
        very_old = int(old_mask.sum())
        total_future += future
        total_very_old += very_old
        total_checked += n_non_null

        # Up to 5 sample row numbers + values per offending bucket
        sample_future: List[Dict[str, Any]] = []
        for idx in non_null[future_mask].head(5).index:
            sample_future.append({"row": int(idx) + 1, "value": str(series.iloc[idx])})
        sample_old: List[Dict[str, Any]] = []
        for idx in non_null[old_mask].head(5).index:
            sample_old.append({"row": int(idx) + 1, "value": str(series.iloc[idx])})

        bad = future + very_old
        rate = 1.0 - (bad / n_non_null) if n_non_null else 0.0

        per_col.append({
            "column": str(col),
            "semantic_type": (glossary or {}).get(str(col), {}).get("semantic_type"),
            "total": rows,
            "populated": n_non_null,
            "blank": n_blank,
            "future_dated": future,
            "very_old": very_old,
            "oldest": str(non_null.min()),
            "newest": str(non_null.max()),
            "timeliness_rate": round(rate, 4),
            "samples_future": sample_future,
            "samples_very_old": sample_old,
        })

    # Worst-first so action items surface at the top
    per_col.sort(key=lambda r: r["timeliness_rate"])

    overall = (total_checked - total_future - total_very_old) / total_checked if total_checked else 1.0
    return {
        "summary": {
            "rows": rows,
            "date_columns": len(date_cols),
            "total_future_rows": total_future,
            "total_very_old_rows": total_very_old,
            "overall_timeliness": round(overall, 4),
        },
        "columns": per_col,
        "project_context": ctx,
    }
