"""Find Duplicates endpoints — 1:1 parity with features/duplicates/ui.py.

3 sub-tabs (Exact / Fuzzy / Combined). Each: scan → summary → per-group detail.
5 removal strategies: keep_first, keep_last, keep_selected, keep_multiple, merge.
Bulk action: Remove All Duplicates (exact only with `keep=first|last|none`).
Excel export of groups (full or selected subset).
"""
from __future__ import annotations

import io
import logging
import math
from datetime import date, datetime
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


def _json_safe(value: Any) -> Any:
    """Coerce numpy / pandas scalars to plain Python types that FastAPI's
    default JSON encoder can serialise. Without this the dialog's GET
    request 500s with no detail when a column contains a Timestamp /
    numpy int / numpy bool — exactly the case for customer-master data.
    """
    if value is None:
        return None
    # NaN / NaT first — bare pd.isna on arrays is ambiguous so guard with try.
    try:
        if isinstance(value, float) and math.isnan(value):
            return None
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(value, (str, int, bool)):
        return value
    if isinstance(value, float):
        return value
    if isinstance(value, np.integer):
        return int(value)
    if isinstance(value, np.floating):
        f = float(value)
        return None if math.isnan(f) else f
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp, datetime, date)):
        try:
            return value.isoformat()
        except Exception:
            return str(value)
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    # Fallback — stringify anything else so the response never blocks.
    try:
        return str(value)
    except Exception:
        return None


from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import require_dataframe, scoped_columns
from ..services.duplicates_engine import (
    export_groups_to_excel,
    find_group,
    get_groups,
    group_to_detail,
    group_to_summary,
    remove_exact,
    remove_fuzzy_group,
    scan_combined,
    scan_custom,
    scan_exact,
    scan_fuzzy,
)
from ..services.project_storage import save_working as _save_working
from ..services.rule_library import get_dedup_rule, list_dedup_rules
from ..services.survivorship_engine import apply_survivor, compute_golden_record
from ..session_store import SessionData

router = APIRouter(prefix="/duplicates", tags=["duplicates"])


# ---------- schemas ------------------------------------------------------

class ScanExactBody(BaseModel):
    subset: Optional[List[str]] = None


class ScanFuzzyBody(BaseModel):
    columns: List[str]
    threshold: float = 85.0
    algorithm: str = "rapidfuzz"


class ScanCombinedBody(BaseModel):
    exact_columns: List[str]
    fuzzy_columns: List[str]
    threshold: float = 85.0
    algorithm: str = "rapidfuzz"


class ScanCustomBody(BaseModel):
    """User-authored dedup rule: multi-CDE selection + AND / OR + survivorship.

    AND  → records are duplicates iff they match on EVERY selected CDE.
    OR   → records are duplicates iff they match on AT LEAST ONE selected CDE.
    Survivorship is passed straight through to the golden-record engine
    (most_complete / most_recent / field_level_merge).
    """
    columns: List[str]
    operator: str = "AND"  # AND | OR
    # Survivorship config shaped exactly like the legacy library rule's
    # ``survivorship`` field. Optional — backend falls back to
    # ``most_complete`` when omitted.
    survivorship: Optional[Dict[str, Any]] = None


class RemoveExactBody(BaseModel):
    subset: Optional[List[str]] = None
    keep: str = "first"  # "first" | "last" | "none"


class RemoveGroupBody(BaseModel):
    strategy: str  # keep_first | keep_last | keep_selected | keep_multiple | merge
    selected_index: Optional[int] = None
    selected_indices: Optional[List[int]] = None


class BulkActionBody(BaseModel):
    group_ids: List[int]
    strategy: str  # keep_first | keep_last | merge


class ExportSelectedBody(BaseModel):
    group_ids: List[int]


# ---------- columns availability ----------------------------------------

@router.get("/columns")
def list_columns(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Return columns + object-only columns (for fuzzy/combined dropdowns).

    Restricted to the user's Columns of interest selection so the duplicate
    detection UI only offers in-scope columns.
    """
    in_scope = set(scoped_columns(sess))
    df = sess.df[[c for c in sess.df.columns if str(c) in in_scope]]
    return {
        "all": list(df.columns.astype(str)),
        "object_only": list(df.select_dtypes(include=["object"]).columns.astype(str)),
    }


# ---------- exact --------------------------------------------------------

@router.post("/exact/scan")
def exact_scan(body: ScanExactBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    groups = scan_exact(sess, body.subset)
    return {
        "type": "exact",
        "total_groups": len(groups),
        "total_rows": sum(len(g.indices) for g in groups),
        "summaries": [group_to_summary(g) for g in groups],
    }


@router.post("/exact/remove-all")
def exact_remove_all(body: RemoveExactBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    keep_val: Any = False if body.keep == "none" else body.keep
    removed = remove_exact(sess, subset=body.subset, keep=keep_val)
    sess.exact_duplicates = []
    return {"ok": True, "removed": removed, "rows_remaining": len(sess.df)}


# ---------- fuzzy --------------------------------------------------------

@router.post("/fuzzy/scan")
def fuzzy_scan(body: ScanFuzzyBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    if not body.columns:
        raise HTTPException(status_code=400, detail="At least one column required for fuzzy matching.")
    try:
        groups = scan_fuzzy(sess, body.columns, body.threshold, body.algorithm)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Fuzzy scan failed: {exc}")
    return {
        "type": "fuzzy",
        "total_groups": len(groups),
        "total_rows": sum(len(g.indices) for g in groups),
        "summaries": [group_to_summary(g) for g in groups],
    }


# ---------- combined -----------------------------------------------------

@router.post("/combined/scan")
def combined_scan(body: ScanCombinedBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    try:
        groups = scan_combined(sess, body.exact_columns, body.fuzzy_columns,
                                body.threshold, body.algorithm)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Combined scan failed: {exc}")
    return {
        "type": "combined",
        "total_groups": len(groups),
        "total_rows": sum(len(g.indices) for g in groups),
        "summaries": [group_to_summary(g) for g in groups],
    }


# ---------- custom (user-authored: multi-CDE + AND/OR + survivorship) ---

@router.post("/custom/scan")
def custom_scan(
    body: ScanCustomBody,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Run a user-authored deduplication rule and return groups.

    The rule's survivorship config is echoed back in the response so the
    Golden Record review dialog can apply it without a second round-trip.
    Survivorship is also stashed on the session so the apply-golden
    endpoint can pick it up when ``dup_type == "custom"``.
    """
    if not body.columns:
        raise HTTPException(
            status_code=400,
            detail="At least one critical data element is required.",
        )
    dataset_cols = {str(c) for c in sess.df.columns}
    unknown = [c for c in body.columns if c not in dataset_cols]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown critical data element(s): {', '.join(unknown)}",
        )

    try:
        groups = scan_custom(sess, body.columns, body.operator)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Custom scan failed: {exc}")

    survivorship = body.survivorship or {"strategy": "most_complete"}
    # Persist on session so /apply-golden can find it without a re-send.
    meta = sess.duplicates_meta.get("custom") or {}
    meta["survivorship"] = survivorship
    sess.duplicates_meta["custom"] = meta

    return {
        "type": "custom",
        "operator": body.operator.upper(),
        "columns": body.columns,
        "survivorship": survivorship,
        "total_groups": len(groups),
        "total_rows": sum(len(g.indices) for g in groups),
        "summaries": [group_to_summary(g) for g in groups],
    }


# ---------- group detail ------------------------------------------------

_VALID_DUP_TYPES = ("exact", "fuzzy", "combined", "custom")


@router.get("/{dup_type}/group/{group_id}")
def group_detail(dup_type: str, group_id: int,
                 sess: SessionData = Depends(require_dataframe)) -> dict:
    if dup_type not in _VALID_DUP_TYPES:
        raise HTTPException(status_code=400, detail="Invalid duplicate type")
    g = find_group(sess, dup_type, group_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Group not found")
    return group_to_detail(g)


# ---------- per-group removal -------------------------------------------

@router.post("/{dup_type}/remove-group/{group_id}")
def remove_group(dup_type: str, group_id: int, body: RemoveGroupBody,
                 sess: SessionData = Depends(require_dataframe)) -> dict:
    g = find_group(sess, dup_type, group_id)
    if g is None:
        raise HTTPException(status_code=404, detail="Group not found")
    removed, msg = remove_fuzzy_group(
        sess, g.indices, body.strategy,
        selected_index=body.selected_index,
        selected_indices=body.selected_indices,
    )
    # Drop the group from cached results since rows have changed.
    if dup_type == "exact":
        sess.exact_duplicates = [x for x in sess.exact_duplicates if x.group_id != group_id]
    elif dup_type == "fuzzy":
        sess.fuzzy_duplicates = [x for x in sess.fuzzy_duplicates if x.group_id != group_id]
    elif dup_type == "combined":
        sess.combined_duplicates = [x for x in sess.combined_duplicates if x.group_id != group_id]
    elif dup_type == "custom":
        sess.custom_duplicates = [x for x in sess.custom_duplicates if x.group_id != group_id]
    return {"ok": True, "removed": removed, "message": msg, "rows_remaining": len(sess.df)}


# ---------- bulk on selected groups -------------------------------------

@router.post("/{dup_type}/bulk")
def bulk_action(dup_type: str, body: BulkActionBody,
                sess: SessionData = Depends(require_dataframe)) -> dict:
    if body.strategy not in ("keep_first", "keep_last", "merge"):
        raise HTTPException(status_code=400, detail="Bulk strategy must be keep_first/keep_last/merge")
    groups = [g for g in get_groups(sess, dup_type) if g.group_id in body.group_ids]
    if not groups:
        raise HTTPException(status_code=400, detail="No matching groups")
    total_removed = 0
    for g in groups:
        removed, _ = remove_fuzzy_group(sess, g.indices, body.strategy)
        total_removed += removed
    # Strip processed groups
    remaining_ids = set(body.group_ids)
    if dup_type == "exact":
        sess.exact_duplicates = [x for x in sess.exact_duplicates if x.group_id not in remaining_ids]
    elif dup_type == "fuzzy":
        sess.fuzzy_duplicates = [x for x in sess.fuzzy_duplicates if x.group_id not in remaining_ids]
    elif dup_type == "combined":
        sess.combined_duplicates = [x for x in sess.combined_duplicates if x.group_id not in remaining_ids]
    elif dup_type == "custom":
        sess.custom_duplicates = [x for x in sess.custom_duplicates if x.group_id not in remaining_ids]
    return {
        "ok": True,
        "groups_processed": len(groups),
        "rows_removed": total_removed,
        "rows_remaining": len(sess.df),
    }


# ---------- excel export -------------------------------------------------

@router.post("/{dup_type}/export")
def export_all(dup_type: str, sess: SessionData = Depends(require_dataframe)):
    groups = get_groups(sess, dup_type)
    if not groups:
        raise HTTPException(status_code=400, detail="No groups to export")
    data, fname = export_groups_to_excel(groups, f"{dup_type}_duplicates")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/{dup_type}/export-selected")
def export_selected(dup_type: str, body: ExportSelectedBody,
                    sess: SessionData = Depends(require_dataframe)):
    groups = [g for g in get_groups(sess, dup_type) if g.group_id in body.group_ids]
    if not groups:
        raise HTTPException(status_code=400, detail="No matching groups")
    data, fname = export_groups_to_excel(groups, f"{dup_type}_selected")
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ─── Dedup rule library (B) ──────────────────────────────────────────


@router.get("/library")
def list_library_rules(stream: Optional[str] = None) -> dict:
    """Catalog of pre-built duplicate-detection rules shipped with the app.

    Filtered by stream when provided — so the Duplicates tab for a Vendor
    project sees only vendor rules. The full list comes back when no
    stream is passed.
    """
    rules = list_dedup_rules(stream)
    return {"rules": rules, "count": len(rules)}


@router.get("/library/{rule_id}")
def get_library_rule(rule_id: str) -> dict:
    rule = get_dedup_rule(rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")
    return rule


class LibraryScanBody(BaseModel):
    rule_id: str
    # Optional mapping from "rule column" -> "actual dataset column". Lets
    # the same library rule run against datasets that use local column
    # naming (e.g. PAN_NUMBER instead of tax_id). When omitted, the rule's
    # own column names are used as-is.
    column_mapping: Optional[Dict[str, str]] = None


def _suggest_column_mapping(
    rule_columns: List[str],
    dataset_columns: List[str],
    semantic_glossary: Optional[Dict[str, Dict[str, Any]]],
    rule: Optional[Dict[str, Any]] = None,
) -> Dict[str, str]:
    """Best-effort heuristic to pre-fill the column-mapping dialog.

    Tries four signals in order:
      1. Exact column name match (case-insensitive).
      2. **Explicit alias list** declared on the rule (the strongest signal
         — a rule that says ``aliases: ["tax_id", "pan_number", "vat_no",
         "gstin"]`` will auto-map ``tax_id`` to whichever of those exists
         in the dataset).
      3. Semantic-glossary match: a rule column named ``email`` maps to
         the first dataset column whose glossary entry has
         ``semantic_type == "email"``.
      4. Substring match (``pan_number`` ←→ ``tax_id``).
    """
    suggested: Dict[str, str] = {}
    lower_to_actual = {c.lower(): c for c in dataset_columns}
    glossary = semantic_glossary or {}
    type_to_col: Dict[str, str] = {}
    for col, entry in glossary.items():
        if isinstance(entry, dict):
            st = (entry.get("semantic_type") or "").lower()
            if st and st not in type_to_col:
                type_to_col[st] = col

    # Build a quick lookup of explicit aliases keyed by rule-column name.
    alias_lookup: Dict[str, List[str]] = {}
    if rule:
        for mc in rule.get("match_columns", []) or []:
            rule_col = mc.get("column")
            aliases = mc.get("aliases") or []
            if rule_col and aliases:
                alias_lookup[rule_col] = [str(a) for a in aliases]

    for rule_col in rule_columns:
        if rule_col in dataset_columns:
            suggested[rule_col] = rule_col
            continue
        match = lower_to_actual.get(rule_col.lower())
        if match:
            suggested[rule_col] = match
            continue
        # Try the rule's declared aliases — case-insensitive.
        aliases = alias_lookup.get(rule_col, [])
        alias_hit = next(
            (lower_to_actual[a.lower()] for a in aliases if a.lower() in lower_to_actual),
            None,
        )
        if alias_hit:
            suggested[rule_col] = alias_hit
            continue
        sem_match = type_to_col.get(rule_col.lower())
        if sem_match:
            suggested[rule_col] = sem_match
            continue
        # Loose substring scan as the last resort.
        for cand in dataset_columns:
            if rule_col.lower() in cand.lower() or cand.lower() in rule_col.lower():
                suggested[rule_col] = cand
                break
    return suggested


@router.post("/library/scan")
def scan_with_library_rule(
    body: LibraryScanBody,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Apply a library dedup rule to the current dataset.

    When a column referenced by the rule isn't present in the dataset and
    the caller didn't supply a ``column_mapping`` for it, returns a
    structured 400 so the UI can pop a "map these columns" dialog rather
    than dead-ending the user.
    """
    rule = get_dedup_rule(body.rule_id)
    if not rule:
        raise HTTPException(status_code=404, detail="Rule not found")

    rule_columns: List[str] = [
        m["column"] for m in rule.get("match_columns", []) if "column" in m
    ]
    mapping: Dict[str, str] = body.column_mapping or {}
    dataset_columns: List[str] = [str(c) for c in sess.df.columns]
    dataset_set = set(dataset_columns)

    # Resolve each rule column through the mapping, defaulting to itself.
    resolved: List[str] = [mapping.get(c, c) for c in rule_columns]
    missing = [
        rc for rc, ac in zip(rule_columns, resolved)
        if ac not in dataset_set
    ]
    if missing:
        suggested = _suggest_column_mapping(
            missing, dataset_columns, sess.semantic_glossary, rule=rule,
        )
        raise HTTPException(
            status_code=400,
            detail={
                "code": "missing_columns",
                "message": (
                    "This rule references columns that aren't in the current "
                    "dataset. Map them to your columns and rerun."
                ),
                "rule_id": rule["id"],
                "rule_label": rule.get("label"),
                "rule_columns": rule_columns,
                "missing_columns": missing,
                "available_columns": dataset_columns,
                "suggested_mapping": suggested,
            },
        )

    strategy = rule.get("match_strategy", "exact")
    if strategy == "exact":
        groups = scan_exact(sess, resolved)
        dup_type = "exact"
    else:
        # The engine wants threshold on a 0-100 scale and one of a fixed
        # set of algorithm tags. Library rules express thresholds as
        # fractions (0.85) and call out the underlying method (e.g.
        # token_sort_ratio) — translate both.
        thresh_raw = next(
            (m.get("threshold", 0.85) for m in rule.get("match_columns", []) if "threshold" in m),
            0.85,
        )
        thresh_pct = float(thresh_raw)
        if thresh_pct <= 1.0:
            thresh_pct *= 100.0
        groups = scan_fuzzy(sess, resolved, thresh_pct, algorithm="rapidfuzz")
        dup_type = "fuzzy"

    return {
        "rule_id": rule["id"],
        "label": rule.get("label"),
        "dup_type": dup_type,
        "total_groups": len(groups),
        "total_rows": sum(len(g.indices) for g in groups),
        "summaries": [group_to_summary(g) for g in groups],
        "survivorship": rule.get("survivorship", {"strategy": "most_complete"}),
        "resolved_columns": dict(zip(rule_columns, resolved)),
    }


# ─── Survivorship / golden record (C) ────────────────────────────────


@router.get("/{dup_type}/group/{group_id}/golden")
def preview_golden_record(
    dup_type: str,
    group_id: int,
    rule_id: Optional[str] = None,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Compute the proposed golden record for one duplicate group.

    If ``rule_id`` is supplied, the rule's survivorship config drives the
    merge; otherwise a sensible default (most_complete) is used. Returns
    the merged record + per-column provenance so the UI can render the
    "where did this value come from" panel.
    """
    group = find_group(sess, dup_type, group_id)
    if not group:
        available = [int(g.group_id) for g in get_groups(sess, dup_type)]
        logger.warning(
            "preview_golden_record: group not found. dup_type=%s requested_id=%s "
            "available_ids=%s session_id=%s",
            dup_type, group_id, available, getattr(sess, "session_id", "?"),
        )
        raise HTTPException(
            status_code=404,
            detail=(
                f"Group #{group_id} not found in {dup_type} scan results. "
                f"Available groups: {available[:10]}{'...' if len(available) > 10 else ''}. "
                "Re-run the scan and try again."
            ),
        )

    indices = list(group.indices)
    if not indices:
        raise HTTPException(status_code=400, detail="Group is empty")

    survivorship = {"strategy": "most_complete"}
    if rule_id:
        rule = get_dedup_rule(rule_id)
        if rule:
            survivorship = rule.get("survivorship", survivorship)
    # Custom rules stash their survivorship on the session at scan-time,
    # so the dialog doesn't need to re-send it on every preview call.
    if dup_type == "custom":
        meta = (sess.duplicates_meta or {}).get("custom") or {}
        survivorship = meta.get("survivorship", survivorship)

    try:
        group_df = sess.df.loc[indices]
    except Exception as exc:
        logger.exception("preview_golden_record: df.loc failed indices=%s", indices)
        raise HTTPException(
            status_code=500,
            detail=f"Could not slice group rows: {exc}",
        )
    try:
        golden = compute_golden_record(group_df, survivorship)
    except Exception as exc:
        logger.exception("preview_golden_record: golden computation failed")
        raise HTTPException(
            status_code=500,
            detail=f"Could not compute golden record: {exc}",
        )

    try:
        members: List[Dict[str, Any]] = []
        for idx in indices:
            row = sess.df.loc[idx]
            # In rare cases of non-unique row indices, .loc returns a
            # DataFrame instead of a Series — degrade gracefully by
            # taking the first matching row so the response still ships.
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            members.append({
                "index": int(idx),
                "is_survivor": int(idx) == int(golden.survivor_index),
                "values": {
                    str(c): _json_safe(row[c]) for c in sess.df.columns
                },
            })

        response = {
            "group_id": int(group.group_id),
            "dup_type": str(dup_type),
            "survivor_index": int(golden.survivor_index),
            "survivorship_strategy": survivorship.get("strategy"),
            "members": members,
            "golden_record": {
                str(c): _json_safe(v) for c, v in golden.record.items()
            },
            "provenance": _json_safe(golden.provenance),
        }
    except Exception as exc:
        logger.exception("preview_golden_record: response build failed")
        raise HTTPException(
            status_code=500,
            detail=f"Could not build golden-record response: {exc}",
        )

    return response


class ApplyGoldenBody(BaseModel):
    rule_id: Optional[str] = None
    overrides: Optional[Dict[str, Any]] = None  # column -> value (manual override)


@router.post("/{dup_type}/group/{group_id}/apply-golden")
def apply_golden_record(
    dup_type: str,
    group_id: int,
    body: ApplyGoldenBody,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Materialize the golden record: update the survivor row, drop the
    other group members, persist if a project is active. Overrides let
    the user replace any computed field value before applying.
    """
    group = find_group(sess, dup_type, group_id)
    if not group:
        raise HTTPException(status_code=404, detail="Group not found")
    indices = list(group.indices)
    if not indices:
        raise HTTPException(status_code=400, detail="Group is empty")

    survivorship = {"strategy": "most_complete"}
    if body.rule_id:
        rule = get_dedup_rule(body.rule_id)
        if rule:
            survivorship = rule.get("survivorship", survivorship)
    if dup_type == "custom":
        meta = (sess.duplicates_meta or {}).get("custom") or {}
        survivorship = meta.get("survivorship", survivorship)

    group_df = sess.df.loc[indices]
    golden = compute_golden_record(group_df, survivorship)
    # Manual overrides take precedence over the engine's choices.
    if body.overrides:
        for col, val in body.overrides.items():
            if col in golden.record:
                golden.record[col] = val
                golden.provenance[col] = {
                    "source_index": None,
                    "reason": "manual_override",
                }

    before = int(len(sess.df))
    sess.df = apply_survivor(sess.df, indices, golden)
    after = int(len(sess.df))

    # Persist if a project is active.
    if sess.active_project_id and sess.df is not None:
        _save_working(sess.active_project_id, sess.df, sess.original_df)

    return {
        "ok": True,
        "survivor_index": int(golden.survivor_index),
        "rows_dropped": int(before - after),
        "rows_remaining": int(after),
        "applied_record": {
            str(c): _json_safe(v) for c, v in golden.record.items()
        },
    }
