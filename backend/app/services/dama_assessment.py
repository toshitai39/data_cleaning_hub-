"""DAMA-aligned Data Quality Assessment — Executive Summary scoring.

Phase 1 of the Data Profiling rebuild. Produces the per-dimension scorecard
the steward sees first when they open Data Profiling: six numeric scores
(Completeness, Validation, Uniqueness, Standardisation, Accuracy,
Timeliness), each with a rating, key finding, records-impacted count,
and risk level. Plus a key-statistics block and a prioritized list of
remediation actions.

The scoring is intentionally lightweight — it operates on whatever the
session already has loaded (the working DataFrame plus, where available,
the semantic glossary from a prior Data Glossary run). Subsequent phases
(P2–P6) deepen each dimension into its own tab with per-field detail.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass
from typing import Any, Dict, Iterable, List, Optional, Tuple

import pandas as pd


# ─── Score → rating / risk translation ───────────────────────────────

def _rating(score: float) -> str:
    if score >= 0.95: return "Strong"
    if score >= 0.85: return "Moderate"
    if score >= 0.70: return "Needs Attention"
    return "Critical"


def _risk(score: float) -> str:
    if score >= 0.95: return "Low"
    if score >= 0.80: return "Medium"
    return "High"


# ─── Standard format checks ──────────────────────────────────────────
# This is a *standards catalog*, not a column lookup. Each entry is the
# canonical regex for a well-known semantic type — PAN's format is fixed
# by Indian tax law, GSTIN's by GST regulation, ISO country codes by
# ISO 3166, etc. The mapping FROM a column TO a semantic_type is the
# job of the AI recommender (`cde_recommender.generate_cde_meta`); this
# table only knows how to *check* a value once the type is known.

# GSTIN regex below was previously 16 chars long (had an extra ``\d``
# group between the PAN's last letter and ``[A-Z\d]Z``). That meant
# every valid 15-character GSTIN — including correctly-formed values
# like ``27ABCDE1234F1Z5`` — was being flagged invalid by the
# Validation drill-down, while Cleansing said the same rows passed.
# Same data, opposite verdicts.
#
# Correct GSTIN structure (15 chars total):
#   2 state digits + 10-char PAN ([A-Z]{5}\d{4}[A-Z]) +
#   1 entity char ([A-Z\d]) + literal 'Z' + 1 check char ([A-Z\d])
_FORMAT_CHECKS: Dict[str, re.Pattern] = {
    "pan":          re.compile(r"^[A-Z]{5}\d{4}[A-Z]$"),
    "gstin":        re.compile(r"^\d{2}[A-Z]{5}\d{4}[A-Z][A-Z\d]Z[A-Z\d]$"),
    "tan":          re.compile(r"^[A-Z]{4}\d{5}[A-Z]$"),
    "cin":          re.compile(r"^[LUu]\d{5}[A-Z]{2}\d{4}[A-Z]{3}\d{6}$"),
    "ein":          re.compile(r"^\d{2}-?\d{7}$"),
    "ssn":          re.compile(r"^\d{3}-?\d{2}-?\d{4}$"),
    "aadhaar":      re.compile(r"^\d{4}\s?\d{4}\s?\d{4}$"),
    "email":        re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]{2,}$"),
    "indian_pin":   re.compile(r"^[1-9]\d{5}$"),
    "postal_code":  re.compile(r"^[A-Z0-9 \-]{3,12}$", re.IGNORECASE),
    "ifsc":         re.compile(r"^[A-Z]{4}0[A-Z0-9]{6}$"),
    "iban":         re.compile(r"^[A-Z]{2}\d{2}[A-Z0-9]{1,30}$"),
    "swift":        re.compile(r"^[A-Z]{6}[A-Z0-9]{2}([A-Z0-9]{3})?$"),
    "iso_country":  re.compile(r"^[A-Z]{2}$"),
    "iso_currency": re.compile(r"^[A-Z]{3}$"),
    "phone":        re.compile(r"^[\d\s\-\+\(\)]{7,}$"),
    "url":          re.compile(r"^https?://\S+$", re.IGNORECASE),
    "year":         re.compile(r"^(19|20)\d{2}$"),
}

# Semantic types that represent business identifiers (used by Uniqueness
# scoring to decide which columns to group on). Free-text and audit
# fields are deliberately excluded.
_IDENTIFIER_SEMANTIC_TYPES = {
    "pan", "gstin", "tan", "cin", "vat", "ein", "ssn", "aadhaar",
    "iban", "swift", "ifsc", "account_number",
    "numeric_id", "alphanumeric_id",
}


def _semantic_type_of(column: str, glossary: Optional[Dict[str, Any]]) -> Optional[str]:
    """Return the AI-assigned semantic_type for a column, or ``None``.

    Pure lookup against the per-project ``cde_meta`` produced by the AI
    recommender — no column-name regex, no keyword heuristics. If the
    column hasn't been classified yet, the caller should treat it as
    unclassifiable and skip rather than penalise.
    """
    if not glossary:
        return None
    entry = glossary.get(column)
    if not isinstance(entry, dict):
        return None
    stype = entry.get("semantic_type") or entry.get("type")
    if not stype:
        return None
    return str(stype).strip().lower().replace(" ", "_") or None


def _validator_for_column(column: str, glossary: Optional[Dict[str, Any]]) -> Optional[re.Pattern]:
    """Resolve the regex used to validate this column's values.

    Two sources, both AI-driven:
      1. An explicit ``regex`` / ``pattern`` field on the column's glossary
         entry (the LLM emitted a custom pattern for this dataset).
      2. The column's ``semantic_type`` matched against the standards
         catalog above.

    No column-name keyword matching. Columns whose semantic type isn't
    known are skipped from Validation scoring entirely.
    """
    if not glossary:
        return None
    entry = glossary.get(column)
    if isinstance(entry, dict):
        raw_regex = entry.get("regex") or entry.get("pattern")
        if raw_regex:
            try:
                return re.compile(raw_regex)
            except re.error:
                pass
    stype = _semantic_type_of(column, glossary)
    if stype and stype in _FORMAT_CHECKS:
        return _FORMAT_CHECKS[stype]
    return None


# ─── Per-dimension scoring ───────────────────────────────────────────

@dataclass
class DimensionScore:
    dimension: str
    score: float
    rating: str
    key_finding: str
    records_impacted: str
    risk_level: str
    enabled: bool = True  # False when there's no data to evaluate the dimension


def _score_completeness(df: pd.DataFrame) -> DimensionScore:
    if df.empty:
        return DimensionScore("Completeness", 0.0, "Critical",
                              "No data loaded.", "—", "High", enabled=False)
    fill_rates = df.notna().mean()
    overall = float(fill_rates.mean())
    low_fields = fill_rates[fill_rates < 0.90]
    critical_fields = fill_rates[fill_rates < 0.50]
    blank_rows = int((df.isna().any(axis=1)).sum())
    finding = (
        f"{len(low_fields)} of {len(fill_rates)} fields have <90% fill; "
        f"{len(critical_fields)} fields are below 50%."
    ) if len(low_fields) else "All fields are at least 90% complete."
    return DimensionScore(
        dimension="Completeness",
        score=round(overall, 3),
        rating=_rating(overall),
        key_finding=finding,
        records_impacted=f"~{blank_rows:,} rows with any blank",
        risk_level=_risk(overall),
    )


def _score_validation(df: pd.DataFrame, glossary: Optional[Dict[str, Any]]) -> DimensionScore:
    typed_cols: List[Tuple[str, re.Pattern]] = []
    for col in df.columns:
        pat = _validator_for_column(str(col), glossary)
        if pat is not None:
            typed_cols.append((str(col), pat))
    if not typed_cols:
        if glossary:
            # Glossary exists but no columns mapped to a known format —
            # either an old cache without semantic_types or every column
            # is free-text. Tell the user how to refresh.
            return DimensionScore(
                "Validation", 0.0, "—",
                "No columns matched a typed format. Click View detail and regenerate the AI classification to refresh.",
                "—", "—", enabled=False,
            )
        return DimensionScore(
            "Validation", 0.0, "—",
            "AI column classification missing. Open Critical Data Elements on Load Data to generate it.",
            "—", "—", enabled=False,
        )

    total_checked = 0
    total_valid = 0
    invalid_details: List[Tuple[str, int]] = []  # (column, # invalid)
    for col, pat in typed_cols:
        series = df[col].dropna().astype(str)
        if series.empty:
            continue
        valid_mask = series.str.match(pat)
        valid = int(valid_mask.sum())
        checked = int(len(series))
        invalid = checked - valid
        total_checked += checked
        total_valid += valid
        if invalid:
            invalid_details.append((col, invalid))

    if total_checked == 0:
        return DimensionScore(
            "Validation", 0.0, "—",
            "Typed columns are entirely blank — nothing to validate.",
            "—", "—", enabled=False,
        )
    score = total_valid / total_checked
    invalid_details.sort(key=lambda x: x[1], reverse=True)
    worst = ", ".join(f"{c} ({n})" for c, n in invalid_details[:3]) if invalid_details else "no failures"
    finding = (
        f"{len(typed_cols)} typed columns validated; "
        f"{total_checked - total_valid:,} invalid values. Worst offenders: {worst}."
    ) if invalid_details else (
        f"All {total_checked:,} values across {len(typed_cols)} typed columns conform to their format."
    )
    return DimensionScore(
        dimension="Validation",
        score=round(score, 3),
        rating=_rating(score),
        key_finding=finding,
        records_impacted=f"~{(total_checked - total_valid):,} invalid values",
        risk_level=_risk(score),
    )


def _detect_identifier_columns(df: pd.DataFrame, glossary: Optional[Dict[str, Any]]) -> List[str]:
    """Find columns that the AI tagged as business identifiers AND that
    actually behave like identifiers in the data.

    Used for Uniqueness scoring. A column qualifies when:
      1. Its AI-assigned ``semantic_type`` is an identifier (PAN, GSTIN,
         account_number, numeric_id, alphanumeric_id, …) OR the AI marked
         it as a CDE (``recommended=true``) with a key-shaped type.
      2. Among non-null values it is mostly unique (ratio ≥ 0.95).

    Step (2) excludes foreign-key lookup columns that the AI legitimately
    tags ``account_number`` / ``numeric_id`` but which by design repeat
    across rows in a master record — e.g. NetSuite customer.subsidiary,
    customer.salesrep, customer.receivablesaccount. Without this filter
    a single FK column with 8/9 duplicates drives Uniqueness to ~10%
    even though id / entityid are 100% unique.
    """
    if not glossary:
        return []
    candidates: List[str] = []
    for col in df.columns:
        name = str(col)
        entry = glossary.get(name)
        if not isinstance(entry, dict):
            continue
        stype = _semantic_type_of(name, glossary)
        if stype and stype in _IDENTIFIER_SEMANTIC_TYPES:
            candidates.append(name)
            continue
        # Fall back: if the AI flagged this as a CDE *and* the type is
        # something key-shaped (recommended primary identifier without an
        # exact semantic-type hit), still treat it as an identifier.
        if entry.get("recommended") and stype in {"enum_code", "year", None, ""}:
            # year / enum_code shouldn't be used for uniqueness — skip.
            continue
        if entry.get("recommended") and stype not in {
            "free_text_name", "free_text_address", "free_text_description",
            "email", "phone", "url", "date", "datetime", "amount", "quantity",
            "percentage", "boolean", "iso_country", "iso_currency",
        }:
            candidates.append(name)

    # Filter to candidates that actually behave like identifiers (mostly
    # unique among non-null values). FK columns that repeat by design fall
    # out here.
    out: List[str] = []
    for name in candidates:
        try:
            series = df[name].dropna()
            if series.empty:
                continue
            ratio = series.nunique() / len(series)
        except Exception:
            continue
        if ratio >= 0.95:
            out.append(name)
    return out


def _score_uniqueness(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]],
    project_context: Optional[Dict[str, Any]] = None,
) -> DimensionScore:
    if df.empty:
        return DimensionScore("Uniqueness", 0.0, "—", "No data loaded.", "—", "—", enabled=False)
    total = len(df)
    full_dup_mask = df.duplicated(keep=False)
    full_dup_rows = int(full_dup_mask.sum())

    id_cols = _detect_identifier_columns(df, glossary)[:4]
    id_dup_rows = 0
    composite_label = ""
    if id_cols:
        composite_label = " + ".join(id_cols)
        id_dup_mask = df[id_cols].duplicated(keep=False)
        id_dup_rows = int(id_dup_mask.sum())

    # Per-column identifier duplicates. Previously the score only looked
    # at full-row + composite-key duplicates — so a column like PAN with
    # 28 duplicate values (96.4% unique) didn't pull the score down at all
    # because the composite (id+pan+tan) stayed unique courtesy of id.
    # Now we surface the worst-affected single identifier so the score
    # tracks the drill-down's per-identifier table.
    #
    # CRITICAL: drop NaN before counting. Pandas' default duplicated()
    # treats NaN==NaN as equal, so a column that's entirely blank
    # (e.g. an unpopulated TAN field) would otherwise be reported as
    # "775 duplicate rows" and drag the score to 0. An empty column
    # contributes no signal — we skip it.
    per_id_worst_rows = 0
    per_id_worst_col = ""
    for col in id_cols:
        try:
            non_null = df[col].dropna()
            if non_null.empty:
                continue
            n = int(non_null.duplicated(keep=False).sum())
        except Exception:
            n = 0
        if n > per_id_worst_rows:
            per_id_worst_rows = n
            per_id_worst_col = col

    # Master-data semantics: for "joined" masters (material across plants,
    # GL across company codes), identifier repetition is expected by design
    # and shouldn't drag the score down. We only flag full-row duplicates
    # in that mode and surface the identifier repetition as informational.
    identifier_repeats_ok = bool((project_context or {}).get("identifier_repeats_expected"))
    if identifier_repeats_ok:
        worst = full_dup_rows
        score = 1.0 - (worst / total if total else 0)
        stream_label = (project_context or {}).get("stream_label") or "stream"
        if full_dup_rows:
            finding = (
                f"{full_dup_rows:,} full-row duplicates found. Identifier repetition "
                f"({id_dup_rows:,} rows sharing {composite_label or 'identifier'}) is "
                f"expected for a {stream_label} dataset and is not penalised."
            )
        elif id_dup_rows:
            finding = (
                f"No exact-row duplicates. Identifier repetition is expected for "
                f"a {stream_label} dataset ({id_dup_rows:,} rows share {composite_label})."
            )
        else:
            finding = f"No duplicates detected — {stream_label} rows are fully distinct."
    else:
        # Entity master OR no stream context: any of the three duplicate
        # signals pulls the score down. The worst one drives the rating.
        worst = max(full_dup_rows, id_dup_rows, per_id_worst_rows)
        score = 1.0 - (worst / total if total else 0)
        if per_id_worst_rows > max(full_dup_rows, id_dup_rows) and per_id_worst_col:
            finding = (
                f"{per_id_worst_rows:,} rows have a duplicated {per_id_worst_col} value "
                f"(the worst single-identifier finding). "
                f"{full_dup_rows:,} are full-row duplicates."
            )
        elif id_dup_rows and id_cols:
            finding = (
                f"{id_dup_rows:,} rows share the same {composite_label} combination — "
                f"{full_dup_rows:,} are full-row duplicates."
            )
        elif full_dup_rows:
            finding = f"{full_dup_rows:,} full-row duplicates found."
        else:
            finding = "No exact-row or identifier duplicates detected."
    return DimensionScore(
        dimension="Uniqueness",
        score=round(score, 3),
        rating=_rating(score),
        key_finding=finding,
        records_impacted=f"~{worst:,} rows in duplicate sets",
        risk_level=_risk(score),
    )


_STANDARDISATION_TARGET_TYPES = {
    "free_text_name", "free_text_address", "free_text_description",
    "enum_code", "iso_country", "iso_currency",
}


def _score_standardisation(df: pd.DataFrame, glossary: Optional[Dict[str, Any]] = None) -> DimensionScore:
    # ``is_string_dtype`` covers both legacy ``object`` columns and pandas 2.x
    # ``StringDtype`` columns, which a plain ``== "object"`` check misses.
    string_cols = [c for c in df.columns if pd.api.types.is_string_dtype(df[c])]
    # When we have AI classification, restrict to columns where a canonical
    # case is actually meaningful — names, addresses, enum codes, country /
    # currency codes. Identifiers (PAN / GSTIN), dates, amounts, etc. are
    # excluded; their format is policed by Validation, not Standardisation.
    if glossary:
        scoped: List[str] = []
        for c in string_cols:
            stype = _semantic_type_of(str(c), glossary)
            if stype is None or stype in _STANDARDISATION_TARGET_TYPES:
                scoped.append(c)
        string_cols = scoped
    if not string_cols:
        return DimensionScore("Standardisation", 1.0, "Strong",
                              "No text columns to evaluate.", "—", "Low")
    # Use the same 5-bucket case detection as the Standardisation drill-down
    # (upper / lower / title / mixed / other) — otherwise Title-Case columns
    # like vendor names get lumped into a single "mixed" bucket and report
    # 100% consistency on the top card while the drill-down shows 70%.
    from .standardisation_report import _detect_case
    per_col: List[Tuple[str, float]] = []
    total_values = 0
    total_off_pattern = 0
    for col in string_cols:
        s = df[col].dropna().astype(str)
        if s.empty:
            continue
        cases = s.map(_detect_case)
        counts = cases.value_counts()
        dominant_count = int(counts.iloc[0]) if len(counts) else 0
        off = int(len(s)) - dominant_count
        total_values += int(len(s))
        total_off_pattern += off
        per_col.append((col, dominant_count / len(s)))
    if total_values == 0:
        return DimensionScore("Standardisation", 1.0, "Strong",
                              "Text columns are blank — nothing to score.", "—", "Low", enabled=False)
    score = 1.0 - (total_off_pattern / total_values)
    per_col.sort(key=lambda x: x[1])
    worst_cols = ", ".join(f"{c} ({pct:.0%})" for c, pct in per_col[:3])
    finding = (
        f"{total_off_pattern:,} values deviate from their column's dominant case pattern. "
        f"Worst columns: {worst_cols}."
    ) if total_off_pattern else "All text columns are case-consistent."
    return DimensionScore(
        dimension="Standardisation",
        score=round(score, 3),
        rating=_rating(score),
        key_finding=finding,
        records_impacted=f"~{total_off_pattern:,} non-conforming values",
        risk_level=_risk(score),
    )


def _score_accuracy(df: pd.DataFrame, cross_field_rules: Optional[List[Dict[str, Any]]]) -> DimensionScore:
    """Accuracy = share of cross-field BUSINESS RULES that fully pass.

    Aligned with the drill-down's "Pass Rate" so the dimension card and
    the detail view never disagree. The previous row-weighted formula
    (rows passing / total row-evaluations) made any single-row violation
    look statistically tiny — 2 failing rows out of 3,875 row-evaluations
    came in at 99.95% and rounded to 100%, while the drill-down reading
    of the same data showed 80% (4 / 5 rules passing). Same problem,
    two contradictory numbers on screen.

    Now both views compute Accuracy = rules_passing / total_rules and
    rate it by rule-level integrity. The violation count is still
    surfaced in the records-impacted line so the steward sees magnitude.
    """
    if not cross_field_rules:
        return DimensionScore(
            "Accuracy", 0.0, "—",
            "No cross-field rules generated yet — run Rule Generator's cross-field pass to evaluate Accuracy.",
            "—", "—", enabled=False,
        )

    total_rules = len(cross_field_rules)
    rules_passing = 0
    total_violations = 0
    failing_rule_names: List[Tuple[str, int]] = []
    for rule in cross_field_rules:
        n = int(rule.get("issues_found", 0) or 0)
        total_violations += n
        if n == 0:
            rules_passing += 1
        else:
            failing_rule_names.append((
                str(rule.get("rule") or rule.get("data_quality_rule") or "rule"),
                n,
            ))
    rules_failing = total_rules - rules_passing
    score = rules_passing / total_rules if total_rules else 0.0
    failing_rule_names.sort(key=lambda x: x[1], reverse=True)
    worst = ", ".join(f"{n}× '{r[:50]}'" for r, n in failing_rule_names[:2])
    if rules_failing:
        finding = (
            f"{rules_failing} of {total_rules} cross-field rules failing "
            f"({total_violations:,} total violations). Top: {worst}."
        )
    else:
        finding = f"All {total_rules} cross-field rules pass on every row."
    return DimensionScore(
        dimension="Accuracy",
        score=round(score, 3),
        rating=_rating(score),
        key_finding=finding,
        records_impacted=(
            f"~{total_violations:,} rule violations across {rules_failing} failing rule(s)"
            if rules_failing else "0 violations"
        ),
        risk_level=_risk(score),
    )


def _score_timeliness(df: pd.DataFrame) -> DimensionScore:
    date_cols = [c for c in df.columns if pd.api.types.is_datetime64_any_dtype(df[c])]
    if not date_cols:
        return DimensionScore("Timeliness", 1.0, "Strong",
                              "No date / datetime columns in the dataset.",
                              "—", "Low", enabled=False)
    now = pd.Timestamp.utcnow().tz_localize(None)
    total = 0
    bad = 0
    future_cols: List[Tuple[str, int]] = []
    for col in date_cols:
        s = df[col].dropna()
        if s.empty:
            continue
        try:
            s = s.dt.tz_localize(None) if getattr(s.dt, "tz", None) is not None else s
        except Exception:
            pass
        future = int((s > now).sum())
        total += int(len(s))
        bad += future
        if future:
            future_cols.append((col, future))
    if total == 0:
        return DimensionScore("Timeliness", 1.0, "Strong",
                              "Date columns are blank.", "—", "Low", enabled=False)
    score = 1.0 - (bad / total)
    detail = ", ".join(f"{c} ({n})" for c, n in future_cols[:2]) if future_cols else "no future dates"
    finding = f"{bad:,} future-dated values across {len(future_cols)} columns: {detail}." if bad else \
              f"All {total:,} date values are in the past or present."
    return DimensionScore(
        dimension="Timeliness",
        score=round(score, 3),
        rating=_rating(score),
        key_finding=finding,
        records_impacted=f"~{bad:,} future-dated rows",
        risk_level=_risk(score),
    )


# ─── Key statistics + remediation actions ────────────────────────────

def _key_statistics(df: pd.DataFrame, glossary: Optional[Dict[str, Any]]) -> List[Dict[str, Any]]:
    stats: List[Dict[str, Any]] = []
    rows = len(df)
    cols = len(df.columns)
    stats.append({"label": "Total Records", "value": f"{rows:,}"})
    stats.append({"label": "Total Fields", "value": str(cols)})
    id_cols = _detect_identifier_columns(df, glossary)
    if id_cols:
        primary = id_cols[0]
        try:
            uniq = int(df[primary].nunique(dropna=True))
            stats.append({"label": f"Unique {primary} values", "value": f"{uniq:,}"})
        except Exception:
            pass
    fill_rate = float(df.notna().mean().mean()) if rows and cols else 0.0
    stats.append({"label": "Overall Fill Rate", "value": f"{fill_rate:.1%}"})
    # Useful one-liner distributions, when present
    for candidate in ("Country", "country", "LAND1", "Currency", "currency", "WAERS"):
        if candidate in df.columns:
            uniq = int(df[candidate].nunique(dropna=True))
            stats.append({"label": f"{candidate} distinct values", "value": str(uniq)})
            break
    return stats


def _remediation_actions(scores: List[DimensionScore]) -> List[Dict[str, str]]:
    """Translate every dimension finding into a prioritised action.

    Each enabled dimension with a score below perfect gets a row. The
    weakest dimensions take P1 / P2 / P3 labels; anything weaker than
    that becomes P4+ and ages out as the steward remediates upstream.
    Perfect (1.0) dimensions are excluded — they don't need an action.
    """
    enabled = [s for s in scores if s.enabled and s.score < 1.0]
    enabled.sort(key=lambda s: s.score)
    actions: List[Dict[str, str]] = []
    for i, s in enumerate(enabled):
        # P1, P2, P3 for the top three; P4+ for any additional findings
        # so the panel keeps surfacing real issues instead of truncating.
        prio = f"P{i + 1}"
        if s.dimension == "Completeness":
            action = "Backfill or source-correct the highest-blank fields; add Completeness rules to block future blanks."
        elif s.dimension == "Validation":
            action = "Cleanse invalid identifier values flagged in the Validation tab; tighten input regex at point-of-entry."
        elif s.dimension == "Uniqueness":
            action = "Run the dedup rule library on shared identifiers; merge duplicate customer records via Golden Record review."
        elif s.dimension == "Standardisation":
            action = "Normalise case patterns and spelling variants in text fields; introduce a value-master lookup."
        elif s.dimension == "Accuracy":
            action = "Resolve cross-field rule violations (e.g. GST Registered ↔ GSTIN); add validation gates."
        elif s.dimension == "Timeliness":
            action = "Audit future-dated records; correct or reject at ingestion."
        else:
            action = f"Investigate {s.dimension} findings."
        actions.append({
            "priority": prio,
            "dimension": s.dimension,
            "action": action,
            "impact": s.key_finding,
            "estimated_records": s.records_impacted,
        })
    return actions


# ─── Public entry point ──────────────────────────────────────────────

def compute_executive_summary(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]] = None,
    cross_field_rules: Optional[List[Dict[str, Any]]] = None,
    project_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the full DAMA scorecard for the given DataFrame.

    Returns a dict shaped for direct JSON serialisation by the API layer:

        {
          "dimensions": [ {dimension, score, rating, key_finding,
                           records_impacted, risk_level, enabled}, ... ],
          "overall_score": float,        # mean of enabled-dimension scores
          "overall_rating": "Strong" | "Moderate" | "Needs Attention" | "Critical",
          "key_statistics": [ {label, value}, ... ],
          "remediation_actions": [ {priority, dimension, action, impact,
                                    estimated_records}, ... ],
        }
    """
    if df is None or df.empty:
        return {
            "dimensions": [],
            "overall_score": 0.0,
            "overall_rating": "—",
            "key_statistics": [],
            "remediation_actions": [],
            "warning": "No data loaded.",
        }

    scores = [
        _score_completeness(df),
        _score_validation(df, glossary),
        _score_uniqueness(df, glossary, project_context),
        _score_standardisation(df, glossary),
        _score_accuracy(df, cross_field_rules),
        _score_timeliness(df),
    ]
    enabled_scores = [s for s in scores if s.enabled]
    overall = round(sum(s.score for s in enabled_scores) / len(enabled_scores), 3) if enabled_scores else 0.0

    return {
        "dimensions": [s.__dict__ for s in scores],
        "overall_score": overall,
        "overall_rating": _rating(overall) if enabled_scores else "—",
        "key_statistics": _key_statistics(df, glossary),
        "remediation_actions": _remediation_actions(scores),
        "project_context": project_context or {},
    }
