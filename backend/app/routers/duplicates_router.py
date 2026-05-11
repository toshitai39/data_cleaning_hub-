"""Find Duplicates endpoints — 1:1 parity with features/duplicates/ui.py.

3 sub-tabs (Exact / Fuzzy / Combined). Each: scan → summary → per-group detail.
5 removal strategies: keep_first, keep_last, keep_selected, keep_multiple, merge.
Bulk action: Remove All Duplicates (exact only with `keep=first|last|none`).
Excel export of groups (full or selected subset).
"""
from __future__ import annotations

import io
from typing import Any, Dict, List, Optional

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
    scan_exact,
    scan_fuzzy,
)
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


# ---------- group detail ------------------------------------------------

@router.get("/{dup_type}/group/{group_id}")
def group_detail(dup_type: str, group_id: int,
                 sess: SessionData = Depends(require_dataframe)) -> dict:
    if dup_type not in ("exact", "fuzzy", "combined"):
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
