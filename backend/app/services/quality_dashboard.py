"""Data Quality Dashboard — consolidates everything the dashboard page needs
into one response payload so the React side renders without a fan-out of
small requests.

Mirrors the layout convention of the reference Power-BI dashboards
(Syngene Data Quality Dashboard) but driven by the live DAMA assessment
the profiling pipeline already produces. Every number here flows from
one of the dimension scorers + the cached AI classification — no
hardcoded thresholds, no per-master-type assumptions, no ad-hoc rules.
"""

from __future__ import annotations

import re
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from .dama_assessment import (
    _FORMAT_CHECKS,
    _IDENTIFIER_SEMANTIC_TYPES,
    _semantic_type_of,
    _validator_for_column,
)


# Threshold categorisation used everywhere downstream. Matches the
# reference workbook's High / Medium / Low buckets so the dashboard reads
# the same way to anyone who's seen a DAMA-style assessment before.
def _threshold_category(score: float) -> str:
    if score is None:
        return "Unscored"
    if score >= 0.95:
        return "High"
    if score >= 0.70:
        return "Medium"
    return "Low"


_THRESHOLD_TONE = {
    "High":     "#16a34a",
    "Medium":   "#ca8a04",
    "Low":      "#dc2626",
    "Unscored": "#94a3b8",
}


# Free-text-shaped semantic types where case consistency is what
# "Standardisation" actually checks per column.
_STANDARDISATION_TARGETS = {
    "free_text_name", "free_text_address", "free_text_description",
    "enum_code", "iso_country", "iso_currency",
}


def _per_field_scores(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    """Compute every CDE's per-dimension score plus an overall mean.

    Each field gets between 1 and 4 dimension scores depending on its
    AI-assigned semantic type:
      • Completeness  — always (fill rate)
      • Validation    — only when the type maps to a canonical regex
      • Uniqueness    — only for identifier-shaped types
      • Standardisation — only for free-text / enum / country / currency

    The overall is the mean of whatever applied. Missing dimensions
    don't drag the score down (so a name-only column isn't penalised
    for not having a regex check).
    """
    rows = int(len(df)) if df is not None else 0
    if rows == 0 or df is None:
        return []
    glossary = glossary or {}
    out: List[Dict[str, Any]] = []
    for col in df.columns:
        name = str(col)
        entry = glossary.get(name) or {}
        stype = (entry.get("semantic_type") or "").lower() or None

        # Completeness — fill rate (always applies)
        non_null = int(df[col].notna().sum())
        completeness = non_null / rows if rows else 0.0

        # Validation — regex compliance, only on typed columns
        validation: Optional[float] = None
        validator = _validator_for_column(name, glossary)
        if validator is not None and non_null:
            try:
                series = df[col].dropna().astype(str)
                valid = int(series.str.match(validator).sum())
                validation = valid / non_null if non_null else 0.0
            except Exception:
                validation = None

        # Uniqueness — only on identifier-type columns; ignore all-null
        uniqueness: Optional[float] = None
        if stype in _IDENTIFIER_SEMANTIC_TYPES:
            series = df[col].dropna()
            if not series.empty:
                uniqueness = float(series.nunique()) / len(series)

        # Standardisation — case-pattern consistency on text-shaped types
        standardisation: Optional[float] = None
        if stype in _STANDARDISATION_TARGETS:
            try:
                series = df[col].dropna().astype(str)
                if not series.empty:
                    upper = int((series.str.upper() == series).sum())
                    lower = int((series.str.lower() == series).sum())
                    mixed = int(len(series)) - upper - lower
                    dominant = max(upper, lower, mixed)
                    standardisation = dominant / len(series)
            except Exception:
                standardisation = None

        dim_scores = {
            "Completeness":    completeness,
            "Validation":      validation,
            "Uniqueness":      uniqueness,
            "Standardisation": standardisation,
        }
        applicable = [v for v in dim_scores.values() if v is not None]
        overall = sum(applicable) / len(applicable) if applicable else 0.0
        # "Non-compliant cases" = rows that fail any applicable check.
        # Closest single number: max(blank count, invalid count, etc.)
        blanks = rows - non_null
        invalid_count = (
            int((1.0 - validation) * non_null) if validation is not None else 0
        )
        non_compliant = max(blanks, invalid_count)

        out.append({
            "field":            name,
            "semantic_type":    stype,
            "is_cde":           bool(entry.get("recommended")),
            "completeness":     round(completeness, 4),
            "validation":       round(validation, 4) if validation is not None else None,
            "uniqueness":       round(uniqueness, 4) if uniqueness is not None else None,
            "standardisation":  round(standardisation, 4) if standardisation is not None else None,
            "overall_score":    round(overall, 4),
            "non_compliant_count": non_compliant,
            "threshold":        _threshold_category(overall),
        })
    # Worst-first so the table opens on the actionable rows.
    out.sort(key=lambda r: (r["overall_score"], r["field"]))
    return out


def _threshold_distribution(per_field: List[Dict[str, Any]]) -> Dict[str, int]:
    counts = {"High": 0, "Medium": 0, "Low": 0, "Unscored": 0}
    for f in per_field:
        counts[f["threshold"]] = counts.get(f["threshold"], 0) + 1
    return counts


def _semantic_type_distribution(per_field: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    counts: Dict[str, int] = {}
    for f in per_field:
        key = f["semantic_type"] or "other"
        counts[key] = counts.get(key, 0) + 1
    return sorted(
        [{"semantic_type": k, "count": v} for k, v in counts.items()],
        key=lambda r: (-r["count"], r["semantic_type"]),
    )


def _dimension_threshold_buckets(
    per_field: List[Dict[str, Any]],
    executive_summary: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """For each of the SIX dimensions, return a bucket count.

    Completeness / Validation / Uniqueness / Standardisation roll up
    from per-field scores (the natural model — they're column-level).
    Accuracy + Timeliness are dataset-level dimensions (cross-field
    rule pass-rate, date-freshness rate) so we bucket the dimension's
    overall score itself — keeps the chart inclusive of all six.
    """
    out: List[Dict[str, Any]] = []
    field_dims = ("Completeness", "Validation", "Uniqueness", "Standardisation")
    for dim in field_dims:
        key = dim.lower()
        scores = [f[key] for f in per_field if f[key] is not None]
        buckets = {"High": 0, "Medium": 0, "Low": 0}
        for s in scores:
            buckets[_threshold_category(s)] = buckets.get(_threshold_category(s), 0) + 1
        out.append({
            "dimension": dim,
            "applicable_fields": len(scores),
            "buckets": buckets,
        })
    # Dataset-level dimensions — emit a single-bucket entry based on the
    # dimension's headline score from the Executive Summary.
    dim_lookup = {
        (d.get("dimension") or ""): d
        for d in ((executive_summary or {}).get("dimensions") or [])
    }
    for dim in ("Accuracy", "Timeliness"):
        d = dim_lookup.get(dim) or {}
        if not d.get("enabled"):
            out.append({
                "dimension": dim,
                "applicable_fields": 0,
                "buckets": {"High": 0, "Medium": 0, "Low": 0},
            })
            continue
        bucket = _threshold_category(d.get("score") or 0)
        buckets = {"High": 0, "Medium": 0, "Low": 0}
        buckets[bucket] = 1
        out.append({
            "dimension": dim,
            "applicable_fields": 1,
            "buckets": buckets,
        })
    return out


def compute_quality_dashboard(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]] = None,
    executive_summary: Optional[Dict[str, Any]] = None,
    cross_field_rules: Optional[List[Dict[str, Any]]] = None,
    project_context: Optional[Dict[str, Any]] = None,
    ai_rules_df: Optional[pd.DataFrame] = None,
) -> Dict[str, Any]:
    """Build the consolidated dashboard payload."""
    ctx = project_context or {}
    if df is None or df.empty:
        return {
            "summary": {
                "total_cdes": 0,
                "total_records": 0,
                "total_rules": 0,
                "overall_score": 0.0,
                "stream_label": ctx.get("stream_label"),
                "system_label": ctx.get("system_label"),
            },
            "dimension_scores": [],
            "threshold_distribution": {"High": 0, "Medium": 0, "Low": 0, "Unscored": 0},
            "semantic_type_distribution": [],
            "dimension_threshold_buckets": [],
            "rules_by_dimension": [],
            "per_field": [],
            "project_context": ctx,
        }

    per_field = _per_field_scores(df, glossary)
    threshold_dist = _threshold_distribution(per_field)
    semantic_dist = _semantic_type_distribution(per_field)
    dim_threshold_buckets = _dimension_threshold_buckets(per_field, executive_summary)

    # Rule counts come from the actual generated rules DataFrame
    # (sess.ai_validation_rules) — same source the Rule Generator page
    # reads from, so the dashboard's "Data Quality Rules" total always
    # agrees with what the steward sees on Rule Generator (e.g. 108).
    # Legacy dimension labels (Consistency / Validity from before the
    # 2026-05 rename) get folded into the canonical names so the chart
    # doesn't show both old and new spellings side by side.
    rules_by_dim: List[Dict[str, Any]] = []
    total_rules = 0
    LEGACY_RENAME = {"Consistency": "Standardisation", "Validity": "Validation"}
    if isinstance(ai_rules_df, pd.DataFrame) and not ai_rules_df.empty and "Dimension" in ai_rules_df.columns:
        raw_counts = ai_rules_df["Dimension"].astype(str).value_counts().to_dict()
        # Normalise legacy names before bucketing.
        counts: Dict[str, int] = {}
        for name, n in raw_counts.items():
            canon = LEGACY_RENAME.get(name, name)
            counts[canon] = counts.get(canon, 0) + int(n)
        # Render in canonical order so the chart legend reads consistently.
        canonical = [
            "Completeness", "Validation", "Uniqueness",
            "Standardisation", "Accuracy", "Timeliness",
            "Cross-field Validation",
        ]
        for name in canonical:
            n = int(counts.pop(name, 0))
            if n:
                rules_by_dim.append({"dimension": name, "rule_count": n})
        # Any non-canonical dimension labels left over after rename
        for name, n in counts.items():
            rules_by_dim.append({"dimension": str(name), "rule_count": int(n)})
        total_rules = int(len(ai_rules_df))

    # Dimension scores echoed from the Executive Summary so the gauges
    # match the scorecard the steward saw on the profiling page.
    dimension_scores = (executive_summary or {}).get("dimensions") or []
    overall = (executive_summary or {}).get("overall_score") or 0.0

    return {
        "summary": {
            "total_cdes": int(len(df.columns)),
            "total_records": int(len(df)),
            "total_rules": total_rules,
            "overall_score": round(overall, 4),
            "stream_label": ctx.get("stream_label"),
            "system_label": ctx.get("system_label"),
            "recommended_cdes": sum(1 for f in per_field if f["is_cde"]),
        },
        "dimension_scores": dimension_scores,
        "threshold_distribution": threshold_dist,
        "semantic_type_distribution": semantic_dist,
        "dimension_threshold_buckets": dim_threshold_buckets,
        "rules_by_dimension": rules_by_dim,
        "per_field": per_field,
        "project_context": ctx,
    }
