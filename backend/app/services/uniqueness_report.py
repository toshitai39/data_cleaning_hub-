"""DAMA Uniqueness deep-dive — Phase 4 of the Data Profiling rebuild.

Mirrors Sheet 3 ("Uniqueness Assessment") of the reference workbook:

  1. Record overview          — totals, distinct rows, distinct identifier values
  2. Composite-key duplicates — rows sharing Name + Primary ID + Tax ID
  3. Shared-identifier risk   — same identifier value attached to multiple
                                entities (e.g. one PAN across many customer
                                numbers); flagged High Risk for entity masters
  4. Per-column uniqueness    — unique / duplicate counts per identifier

All identifier detection is AI-driven via `cde_meta.semantic_type` +
`cde_meta.recommended`. Master-data stream context tunes the severity —
identifier repetition is a violation for Customer / Vendor / Employee
masters and informational for Material / GL / Cost Centre joined views.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

from .dama_assessment import _detect_identifier_columns


_PRIMARY_IDENTIFIER_TYPES = {
    "pan", "gstin", "tan", "cin", "vat", "ein", "ssn", "aadhaar",
    "iban", "swift", "ifsc", "account_number",
    "numeric_id", "alphanumeric_id",
}


def _identifier_columns_ordered(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]],
) -> List[str]:
    """Identifier columns sorted "most-key-like first".

    Ordering (most-primary → least):
      Tier 0: generic-shaped IDs (numeric_id / alphanumeric_id) — these
              are the actual entity-key columns in a master (id,
              entity_code, customer_number, KUNNR, LIFNR, MATNR, …).
              They should be 100% unique in a clean master.
      Tier 1: account_number — strong key, but typically not the
              primary one (a customer can have multiple bank accounts).
      Tier 2: regulatory identifiers (PAN, GSTIN, TAN, CIN, EIN, SSN,
              Aadhaar). These are *attributes* of an entity, not the
              entity key. They legitimately duplicate when a customer
              has multiple rows (e.g. across sales orgs), or when two
              related companies share a parent's PAN.
      Tier 3: everything else.

    Within a tier we prefer columns with higher actual uniqueness rate —
    a 100%-unique column is more likely the true primary key than one
    with duplicates. Fixes the bug where PAN (~96% unique due to shared
    PANs across related entities) was ranked above `id` (100% unique).
    """
    cols = _detect_identifier_columns(df, glossary)
    if not cols:
        return []

    # Precompute uniqueness rate per column for the tie-breaker.
    uniqueness: Dict[str, float] = {}
    for col in cols:
        try:
            series = df[col].dropna()
            uniqueness[col] = float(series.nunique()) / len(series) if len(series) else 0.0
        except Exception:
            uniqueness[col] = 0.0

    # Column position in the source frame — used as the final tiebreaker
    # when type tier and uniqueness are identical. Source systems almost
    # always order the natural primary key first (KUNNR comes first in
    # LFA1, customer_id first in a CSV export, etc.) so position is the
    # most-defensible signal we have. Alphabetical was arbitrary.
    column_position = {str(c): i for i, c in enumerate(df.columns)}

    _REGULATORY_IDS = {"pan", "gstin", "tan", "cin", "ein", "ssn", "aadhaar", "vat"}

    def rank(col: str):
        entry = (glossary or {}).get(col) or {}
        stype = (entry.get("semantic_type") or "").lower()
        if stype in {"numeric_id", "alphanumeric_id"}:
            tier = 0
        elif stype == "account_number":
            tier = 1
        elif stype in _REGULATORY_IDS:
            tier = 2
        else:
            tier = 3
        # Negative uniqueness sorts higher value first within the tier;
        # column-position keeps lower-index columns first when uniqueness ties.
        return (tier, -uniqueness.get(col, 0.0), column_position.get(col, 999))

    return sorted(cols, key=rank)


_REGULATORY_ID_TYPES = {"pan", "gstin", "tan", "cin", "ein", "ssn", "aadhaar", "vat"}


def _attribute_composite_columns(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]],
    primary_identifier: Optional[str],
) -> List[str]:
    """Build the "Name + regulatory IDs" composite used for duplicate-entity
    detection — mirrors the reference workbook's Sheet 3 §2 ("Duplicate
    Name + PAN + GSTIN combinations").

    Critically EXCLUDES the primary entity key so the analysis can find
    rows that share the same real-world identity (same name, same tax
    IDs) but were recorded under different primary keys. Including the
    primary key would always produce zero duplicates by definition.
    """
    if df is None or df.empty or not glossary:
        return []
    out: List[str] = []
    # 1. Find a name column the AI flagged as recommended
    for col in df.columns:
        if str(col) == primary_identifier:
            continue
        entry = glossary.get(str(col)) or {}
        if not isinstance(entry, dict):
            continue
        stype = (entry.get("semantic_type") or "").lower()
        if stype == "free_text_name" and entry.get("recommended"):
            out.append(str(col))
            break
    # 2. Add up to two regulatory identifiers (PAN / GSTIN / TAN / CIN …)
    reg_added = 0
    for col in df.columns:
        if str(col) == primary_identifier or str(col) in out:
            continue
        entry = glossary.get(str(col)) or {}
        if not isinstance(entry, dict):
            continue
        stype = (entry.get("semantic_type") or "").lower()
        if stype in _REGULATORY_ID_TYPES:
            out.append(str(col))
            reg_added += 1
            if reg_added >= 2:
                break
    return out


def _primary_rationale(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]],
    primary: Optional[str],
    other_candidates: List[str],
) -> str:
    """Plain-English explanation of *why* this column was chosen as the
    primary entity identifier. Designed for a tooltip in the UI so the
    steward can see the math behind the choice."""
    if not primary:
        return "No identifier columns were detected by the AI classifier."
    entry = (glossary or {}).get(primary) or {}
    stype = (entry.get("semantic_type") or "").lower()
    try:
        series = df[primary].dropna()
        uniq_rate = float(series.nunique()) / len(series) if len(series) else 0.0
    except Exception:
        uniq_rate = 0.0
    pieces = [
        f"Type: {stype or 'unknown'}.",
        f"Uniqueness: {uniq_rate:.1%}.",
    ]
    if other_candidates:
        pieces.append(
            f"Chosen over {', '.join(other_candidates[:3])} "
            f"based on (1) being a generic-ID type rather than a regulatory ID, "
            f"(2) higher uniqueness rate, then (3) source-column order as the tiebreaker."
        )
    else:
        pieces.append("Only identifier candidate in the dataset.")
    return " ".join(pieces)


def _top_duplicate_values(
    df: pd.DataFrame,
    cols: List[str],
    limit: int = 10,
) -> List[Dict[str, Any]]:
    """Top duplicate value combinations across the supplied column list."""
    if not cols or df.empty:
        return []
    grouped = (
        df[cols]
        .dropna(how="all")
        .groupby(cols, dropna=False)
        .size()
        .reset_index(name="rows")
    )
    grouped = grouped[grouped["rows"] > 1].sort_values("rows", ascending=False).head(limit)
    out: List[Dict[str, Any]] = []
    for _, row in grouped.iterrows():
        values = {c: (None if pd.isna(row[c]) else str(row[c])) for c in cols}
        out.append({"values": values, "rows": int(row["rows"])})
    return out


def compute_uniqueness_report(
    df: pd.DataFrame,
    glossary: Optional[Dict[str, Any]] = None,
    project_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Compute the Uniqueness deep-dive.

    Returns a dict with sections for the four reference layouts above plus
    a project-context echo so the frontend can vary severity language.
    """
    ctx = project_context or {}
    identifier_repeats_ok = bool(ctx.get("identifier_repeats_expected"))

    if df is None or df.empty:
        return {
            "summary": {
                "rows": 0, "distinct_rows": 0, "full_row_duplicates": 0,
                "identifier_columns": [],
                "primary_identifier": None,
                "composite_key": [],
            },
            "composite_key_duplicates": {
                "key": [], "duplicate_combos": 0, "rows_in_duplicates": 0,
                "duplicate_rate": 0.0, "samples": [],
            },
            "shared_identifier_risk": [],
            "per_column": [],
            "project_context": ctx,
        }

    rows = int(len(df))
    full_dup_mask = df.duplicated(keep=False)
    full_dups = int(full_dup_mask.sum())
    distinct_rows = int(df.drop_duplicates().shape[0])

    id_cols = _identifier_columns_ordered(df, glossary)
    primary = id_cols[0] if id_cols else None
    primary_rationale = _primary_rationale(df, glossary, primary, id_cols[1:])

    # Composite key for *duplicate-entity* detection: NAME + regulatory IDs,
    # EXCLUDING the primary entity key. Matches the reference workbook's
    # "Duplicate Name + PAN + GSTIN combinations" approach. Falls back to
    # the top-three identifier columns only if no name / regulatory ID
    # signal is available (which is the prototype's old behaviour and
    # rarely useful — but we keep it so the section isn't empty).
    composite_key = _attribute_composite_columns(df, glossary, primary)
    composite_fallback_used = False
    if not composite_key:
        composite_key = id_cols[:3]
        composite_fallback_used = True

    # 2. Composite-key duplicate analysis (Sheet 3 §2)
    comp_dupes = {
        "key": composite_key,
        "duplicate_combos": 0,
        "rows_in_duplicates": 0,
        "duplicate_rate": 0.0,
        "samples": [],
        "fallback_used": composite_fallback_used,
    }
    if composite_key:
        grouped = (
            df[composite_key]
            .dropna(how="all")
            .groupby(composite_key, dropna=False)
            .size()
            .reset_index(name="rows")
        )
        dup_groups = grouped[grouped["rows"] > 1]
        rows_in_dupes = int(dup_groups["rows"].sum())
        comp_dupes = {
            "key": composite_key,
            "duplicate_combos": int(len(dup_groups)),
            "rows_in_duplicates": rows_in_dupes,
            "duplicate_rate": round(rows_in_dupes / rows, 4) if rows else 0.0,
            "samples": _top_duplicate_values(df, composite_key, limit=10),
            "fallback_used": composite_fallback_used,
        }

    # 3. Shared-identifier risk (Sheet 3 §3): for each primary-identifier
    # column, find values that appear across multiple distinct entity rows.
    # "Distinct entity" is defined by the union of all OTHER identifier
    # columns — different name+other-id combos sharing one PAN, etc.
    shared_risk: List[Dict[str, Any]] = []
    pure_id_cols = [
        c for c in id_cols
        if (glossary or {}).get(c, {}).get("semantic_type")
        in _PRIMARY_IDENTIFIER_TYPES - {"numeric_id", "alphanumeric_id"}
    ]
    for col in pure_id_cols[:3]:
        other_cols = [c for c in df.columns if c != col]
        # How many distinct OTHER-column combinations does each value cover?
        if not other_cols:
            continue
        try:
            grouped = (
                df.dropna(subset=[col])
                  .groupby(col)
                  .apply(lambda g: g[other_cols].drop_duplicates().shape[0])
            )
        except Exception:
            continue
        shared = grouped[grouped > 1]
        if shared.empty:
            continue
        affected_rows = int(df[df[col].isin(shared.index)].shape[0])
        samples = []
        for value, distinct in shared.sort_values(ascending=False).head(10).items():
            samples.append({
                "value": str(value),
                "distinct_entities": int(distinct),
            })
        shared_risk.append({
            "column": col,
            "semantic_type": (glossary or {}).get(col, {}).get("semantic_type"),
            "shared_values": int(len(shared)),
            "rows_affected": affected_rows,
            "severity": "informational" if identifier_repeats_ok else "high",
            "samples": samples,
        })

    # 4. Per-identifier-column uniqueness rollup. For a column with zero
    # non-null values, ``uniqueness_rate`` is not meaningful — surface
    # as None so the UI can render "—" / "N/A" instead of a misleading
    # 0% (which would imply "all values are duplicates of each other").
    per_column: List[Dict[str, Any]] = []
    for col in id_cols:
        series = df[col].dropna()
        unique = int(series.nunique())
        non_null = int(len(series))
        duplicates = non_null - unique
        rate: Optional[float] = round(unique / non_null, 4) if non_null else None
        per_column.append({
            "column": col,
            "semantic_type": (glossary or {}).get(col, {}).get("semantic_type"),
            "non_null": non_null,
            "unique": unique,
            "duplicates": duplicates,
            "uniqueness_rate": rate,
            "is_empty": non_null == 0,
        })

    return {
        "summary": {
            "rows": rows,
            "distinct_rows": distinct_rows,
            "full_row_duplicates": full_dups,
            "identifier_columns": id_cols,
            "primary_identifier": primary,
            "primary_rationale": primary_rationale,
            "composite_key": composite_key,
            "composite_fallback_used": composite_fallback_used,
        },
        "composite_key_duplicates": comp_dupes,
        "shared_identifier_risk": shared_risk,
        "per_column": per_column,
        "project_context": ctx,
    }
