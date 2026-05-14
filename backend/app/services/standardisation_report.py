"""DAMA Standardisation deep-dive — Phase 5 of the Data Profiling rebuild.

Mirrors Sheet 4 ("Standardization Assessment") of the reference workbook:

  1. Name casing patterns      — per text column, count of UPPER / lower /
                                 Title / mixed values with status
  2. Value spelling variants    — fuzzy clusters within the SAME text column
                                 (e.g. "KUALA LUMPUR" / "KUALA  LUMPUR" /
                                 "KualaLumpur" collapse to one cluster)
  3. Whitespace / non-printable — leading / trailing / double-spaces and
                                 control characters in text columns
  4. Recommendations           — derived from the worst findings

Only inspects columns the AI tagged as text-shaped
(free_text_name / free_text_address / free_text_description / enum_code /
iso_country / iso_currency). PAN / GSTIN / Email / etc. are excluded —
those formats are policed by Validation, not Standardisation.
"""

from __future__ import annotations

import re
import unicodedata
from collections import Counter, defaultdict
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd

from .dama_assessment import _semantic_type_of


# Same target set the executive-summary scorer uses, kept in lock-step.
_STANDARDISATION_TARGET_TYPES = {
    "free_text_name", "free_text_address", "free_text_description",
    "enum_code", "iso_country", "iso_currency",
}

_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _detect_case(value: str) -> str:
    """Classify a single value's case pattern. Empty / numeric-only → 'other'."""
    if not value:
        return "other"
    has_letter = any(ch.isalpha() for ch in value)
    if not has_letter:
        return "other"
    upper = sum(1 for ch in value if ch.isalpha() and ch.isupper())
    lower = sum(1 for ch in value if ch.isalpha() and ch.islower())
    if upper > 0 and lower == 0:
        return "upper"
    if lower > 0 and upper == 0:
        return "lower"
    # Title case heuristic: first letter of each whitespace-separated token
    # is upper, rest are lower or non-letters.
    if value.title() == value:
        return "title"
    return "mixed"


def _normalise_for_clustering(s: str) -> str:
    """Aggressive normalisation used to detect spelling variants.

    Strips accents, collapses non-alphanumerics to nothing, lowercases.
    "KUALA LUMPUR", "Kuala Lumpur ", "KUALA  LUMPUR", "KualaLumpur" all
    map to the same key 'kualalumpur'.
    """
    if not s:
        return ""
    nfkd = unicodedata.normalize("NFKD", s)
    stripped = "".join(c for c in nfkd if not unicodedata.combining(c))
    return _NON_ALNUM.sub("", stripped.lower())


def _whitespace_issues(series: pd.Series) -> Dict[str, int]:
    """Counts of leading-space, trailing-space, double-space, and control chars."""
    s = series.dropna().astype(str)
    if s.empty:
        return {"leading": 0, "trailing": 0, "doublespace": 0, "control_chars": 0}
    return {
        "leading":      int((s.str.len() != s.str.lstrip().str.len()).sum()),
        "trailing":     int((s.str.len() != s.str.rstrip().str.len()).sum()),
        "doublespace":  int(s.str.contains(r"\s{2,}", na=False, regex=True).sum()),
        "control_chars":int(s.str.contains(r"[\x00-\x1f\x7f]", na=False, regex=True).sum()),
    }


def _case_breakdown(series: pd.Series) -> Tuple[Dict[str, int], List[Dict[str, Any]]]:
    """Per-case counts plus sample values for the off-dominant pattern."""
    s = series.dropna().astype(str)
    if s.empty:
        return {"upper": 0, "lower": 0, "title": 0, "mixed": 0, "other": 0}, []
    cases = s.map(_detect_case)
    counts = Counter(cases.tolist())
    dominant = counts.most_common(1)[0][0] if counts else "upper"
    off_pattern = cases[cases != dominant]
    samples: List[Dict[str, Any]] = []
    for idx in off_pattern.head(5).index:
        samples.append({"row": int(idx) + 1, "value": str(s.loc[idx])[:60]})
    return {
        "upper": int(counts.get("upper", 0)),
        "lower": int(counts.get("lower", 0)),
        "title": int(counts.get("title", 0)),
        "mixed": int(counts.get("mixed", 0)),
        "other": int(counts.get("other", 0)),
        "dominant": dominant,
    }, samples


def _spelling_variant_clusters(series: pd.Series, max_clusters: int = 20) -> List[Dict[str, Any]]:
    """Group values whose aggressive-normalised form matches.

    Only reports clusters with ≥2 distinct surface forms — the whole point
    is to surface inconsistent spellings. Singleton clusters (one normal
    form, one surface form) are not interesting.
    """
    s = series.dropna().astype(str)
    if s.empty:
        return []
    by_norm: Dict[str, Counter] = defaultdict(Counter)
    for value in s:
        norm = _normalise_for_clustering(value)
        if not norm:
            continue
        by_norm[norm][value] += 1
    clusters: List[Dict[str, Any]] = []
    for norm, surface in by_norm.items():
        if len(surface) < 2:
            continue
        variants = surface.most_common()
        clusters.append({
            "normalised": norm,
            "variants": [{"value": v, "count": int(c)} for v, c in variants],
            "total_rows": int(sum(c for _, c in variants)),
            "distinct_spellings": len(variants),
        })
    clusters.sort(key=lambda c: (-c["distinct_spellings"], -c["total_rows"]))
    return clusters[:max_clusters]


def compute_standardisation_report(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]] = None,
    project_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the Standardisation deep-dive.

    Returns:

        {
          "summary": {rows, text_columns, off_pattern_values, overall_consistency},
          "case_patterns":     [ {column, semantic_type, counts, dominant, samples} ],
          "spelling_variants": [ {column, clusters: [{normalised, variants, ...}]} ],
          "whitespace":        [ {column, leading, trailing, doublespace, control_chars} ],
          "project_context":   {...},
        }
    """
    rows = int(len(df)) if df is not None else 0
    ctx = project_context or {}
    if df is None or df.empty:
        return {
            "summary": {"rows": 0, "text_columns": 0, "off_pattern_values": 0, "overall_consistency": 0.0},
            "case_patterns": [], "spelling_variants": [], "whitespace": [],
            "project_context": ctx,
        }

    # Pick columns by AI semantic_type when available; fall back to "any
    # string column" so the section still shows useful data on un-classified
    # datasets. Identifier-typed columns are excluded — their format is
    # Validation's domain, not Standardisation's.
    text_cols: List[str] = []
    for col in df.columns:
        if not pd.api.types.is_string_dtype(df[col]):
            continue
        stype = _semantic_type_of(str(col), glossary)
        if stype is None or stype in _STANDARDISATION_TARGET_TYPES:
            text_cols.append(str(col))

    case_patterns: List[Dict[str, Any]] = []
    spelling_variants: List[Dict[str, Any]] = []
    whitespace_issues: List[Dict[str, Any]] = []

    total_values = 0
    total_off_pattern = 0

    for col in text_cols:
        series = df[col]
        breakdown, samples = _case_breakdown(series)
        n_non_null = sum(v for k, v in breakdown.items() if isinstance(v, int) and k in {"upper", "lower", "title", "mixed", "other"})
        dominant = breakdown.get("dominant", "upper")
        off = n_non_null - int(breakdown.get(dominant, 0))
        total_values += n_non_null
        total_off_pattern += off
        case_patterns.append({
            "column": col,
            "semantic_type": _semantic_type_of(col, glossary),
            "counts": {
                "upper": breakdown["upper"],
                "lower": breakdown["lower"],
                "title": breakdown["title"],
                "mixed": breakdown["mixed"],
                "other": breakdown["other"],
            },
            "dominant": dominant,
            "off_pattern": off,
            "consistency_rate": round((n_non_null - off) / n_non_null, 4) if n_non_null else 1.0,
            "samples_off_pattern": samples,
        })

        clusters = _spelling_variant_clusters(series)
        if clusters:
            spelling_variants.append({
                "column": col,
                "semantic_type": _semantic_type_of(col, glossary),
                "clusters": clusters,
            })

        ws = _whitespace_issues(series)
        if any(ws.values()):
            whitespace_issues.append({
                "column": col,
                **ws,
            })

    # Sort worst-first so the steward sees the biggest problems on top.
    case_patterns.sort(key=lambda r: r["consistency_rate"])
    overall = (total_values - total_off_pattern) / total_values if total_values else 1.0

    return {
        "summary": {
            "rows": rows,
            "text_columns": len(text_cols),
            "off_pattern_values": total_off_pattern,
            "overall_consistency": round(overall, 4),
            "spelling_variant_columns": len(spelling_variants),
            "whitespace_issue_columns": len(whitespace_issues),
        },
        "case_patterns": case_patterns,
        "spelling_variants": spelling_variants,
        "whitespace": whitespace_issues,
        "project_context": ctx,
    }
