"""Data loading, preview, compare, and reset endpoints."""
from __future__ import annotations

import io
import math
import os
import tempfile
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, UploadFile
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.audit_log import log_action

from ..catalog import STREAM_SCHEMAS
from ..db import get_db
from ..deps import get_session, require_dataframe
from ..models import Project
from ..schemas import CompareResponse, LoadResponse, PreviewResponse
from ..services.cde_recommender import (
    CDERecommenderError,
    column_set_fingerprint as _cde_fingerprint,
    dtype_fallback_meta as _cde_dtype_fallback,
    generate_cde_meta as _generate_cde_meta,
)
from ..services.llm_rules import llm_available as _llm_available
from ..services.compare_engine import (
    cell_diff as _cell_diff,
    per_column_changes as _per_column_changes,
    stats as _compare_stats,
)
from ..services.db_connector_service import (
    build_url as _build_url,
    connect_and_list,
    list_supported_engines,
    load_from_database,
)
from ..services.loader import load_dataframe, safe_records
from ..services.project_storage import (
    clear_working,
    load_cde_meta,
    save_cde_meta,
    save_glossary,
    save_rules,
    save_scope,
    save_working,
)
from ..session_store import SessionData
from sqlalchemy.orm import Session


def _persist_to_active_project(sess: SessionData, db) -> None:
    """Snapshot the session's working DataFrame to the active project's
    parquet file and refresh the cached metadata in the project row.

    No-op when there's no active project — we still allow the legacy
    "session without a project" flow so existing tests keep working.
    """
    if not sess.active_project_id or sess.df is None:
        return
    save_working(sess.active_project_id, sess.df, sess.original_df)
    project = db.query(Project).filter(Project.id == sess.active_project_id).one_or_none()
    if project is None:
        return
    project.dataset_filename = sess.filename
    project.dataset_rows = int(len(sess.df))
    project.dataset_columns = int(len(sess.df.columns))
    if sess.file_path:
        try:
            project.dataset_size_bytes = int(os.path.getsize(sess.file_path))
        except OSError:
            pass
    if project.status in ("empty", None):
        project.status = "data_loaded"
    db.commit()

router = APIRouter(prefix="/data", tags=["data"])


@router.post("/upload", response_model=LoadResponse)
async def upload(
    file: UploadFile = File(...),
    sheet_name: Optional[str] = Form(default=None),
    header_row: int = Form(default=0),
    sess: SessionData = Depends(get_session),
    db: Session = Depends(get_db),
) -> LoadResponse:
    suffix = Path(file.filename or "data.csv").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    try:
        df, sheets, selected_sheet = load_dataframe(
            tmp_path, suffix, sheet_name=sheet_name, header_row=header_row,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")

    sess.df = df
    sess.original_df = df.copy()
    sess.filename = file.filename or "dataset"
    sess.file_path = tmp_path
    sess.sheet_name = selected_sheet
    sess.column_profiles = {}
    sess.quality_report = None
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    sess.fixes_applied = []

    try:
        log_action("file_loaded", detail=sess.filename, category="load",
                   row_count=len(df), col_count=len(df.columns), filename=sess.filename)
    except Exception:
        pass

    _persist_to_active_project(sess, db)

    return LoadResponse(
        filename=sess.filename,
        rows=len(df),
        columns=len(df.columns),
        column_names=list(df.columns.astype(str)),
        dtypes={c: str(df[c].dtype) for c in df.columns},
        preview=safe_records(df, limit=50),
        sheets=sheets,
    )


@router.get("/state")
def state(sess: SessionData = Depends(get_session)) -> dict:
    """Quick state snapshot for the sidebar + drill-down freshness.

    ``operations`` counts EVERY mutation that should invalidate cached
    profile views — both duplicate fixes (``sess.fixes_applied``) and
    cleansing rule applications (``sess.validation_history``). The
    Data Profiling drill-downs depend on this number so their useEffect
    re-fires whenever the working df is mutated, keeping the top
    scorecard and detail tabs in sync.
    """
    df = sess.df
    quality = None
    if sess.quality_report is not None:
        quality = float(getattr(sess.quality_report, "overall_score", 0))
    return {
        "loaded": df is not None,
        "filename": sess.filename if df is not None else None,
        "rows": int(len(df)) if df is not None else 0,
        "columns": int(len(df.columns)) if df is not None else 0,
        "quality_score": quality,
        "operations": len(sess.fixes_applied) + len(sess.validation_history),
    }


@router.get("/preview", response_model=PreviewResponse)
def preview(
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=10000),
    sess: SessionData = Depends(require_dataframe),
) -> PreviewResponse:
    df = sess.df
    total_rows = len(df)
    total_pages = max(1, math.ceil(total_rows / page_size))
    start = (page - 1) * page_size
    end = start + page_size
    chunk = df.iloc[start:end].copy()
    chunk = chunk.where(pd.notnull(chunk), None)
    return PreviewResponse(
        page=page,
        page_size=page_size,
        total_rows=total_rows,
        total_pages=total_pages,
        columns=list(df.columns.astype(str)),
        rows=chunk.astype(object).where(pd.notnull(chunk), None).to_dict(orient="records"),
    )


# Streamlit-parity Preview tab — matches features/preview/ui.py:
#   - 4 metrics (rows / columns / memory / dtype count)
#   - page sizes 100/500/1000/5000/10000
#   - column subset
#   - case-insensitive substring search across selected columns
#   - download current view as CSV

@router.get("/preview-full")
def preview_full(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=10000),
    columns: Optional[str] = Query(default=None, description="Comma-separated column subset"),
    search: Optional[str] = Query(default=None),
    sess: SessionData = Depends(require_dataframe),
) -> Dict[str, Any]:
    df = sess.df
    all_cols = list(df.columns.astype(str))
    selected_cols = (
        [c.strip() for c in columns.split(",") if c.strip() and c.strip() in df.columns]
        if columns else all_cols
    )

    total_rows = len(df)
    total_pages = max(1, math.ceil(total_rows / page_size))
    start_idx = (page - 1) * page_size
    end_idx = min(start_idx + page_size, total_rows)

    chunk = df.iloc[start_idx:end_idx]
    chunk = chunk[selected_cols] if selected_cols else chunk
    matched_count = len(chunk)
    if search:
        # case-insensitive substring match across any selected col
        mask = chunk.astype(str).apply(lambda c: c.str.contains(search, case=False, na=False, regex=False))
        chunk = chunk[mask.any(axis=1)]
        matched_count = len(chunk)

    chunk = chunk.where(pd.notnull(chunk), None)
    rows = chunk.astype(object).where(pd.notnull(chunk), None).to_dict(orient="records")
    dtypes = {str(c): str(df[c].dtype) for c in selected_cols}
    dtype_count = int(df.dtypes.value_counts().shape[0])
    memory_mb = round(df.memory_usage(deep=True).sum() / 1024 / 1024, 1)

    return {
        "page": page,
        "page_size": page_size,
        "total_rows": total_rows,
        "total_pages": total_pages,
        "start_idx": start_idx,
        "end_idx": end_idx,
        "columns": all_cols,
        "selected_columns": selected_cols,
        "rows": rows,
        "matched_count": matched_count,
        "dtypes": dtypes,
        "dtype_count": dtype_count,
        "total_columns": len(all_cols),
        "memory_mb": memory_mb,
    }


class PreviewDownloadBody(BaseModel):
    page: int = 1
    page_size: int = 100
    columns: Optional[List[str]] = None
    search: Optional[str] = None


@router.post("/preview/download")
def preview_download(body: PreviewDownloadBody,
                     sess: SessionData = Depends(require_dataframe)):
    df = sess.df
    selected = body.columns or list(df.columns.astype(str))
    selected = [c for c in selected if c in df.columns]
    if not selected:
        selected = list(df.columns.astype(str))

    start_idx = (body.page - 1) * body.page_size
    end_idx = start_idx + body.page_size
    chunk = df.iloc[start_idx:end_idx][selected]
    if body.search:
        mask = chunk.astype(str).apply(
            lambda c: c.str.contains(body.search, case=False, na=False, regex=False))
        chunk = chunk[mask.any(axis=1)]

    csv = chunk.to_csv(index=False)
    fname = f"preview_rows_{start_idx}_to_{min(end_idx, len(df))}.csv"
    return StreamingResponse(
        io.BytesIO(csv.encode("utf-8")),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/compare", response_model=CompareResponse)
def compare(sess: SessionData = Depends(require_dataframe)) -> CompareResponse:
    if sess.original_df is None:
        raise HTTPException(status_code=400, detail="No original snapshot available.")
    orig = sess.original_df
    mod = sess.df
    cols_added = [c for c in mod.columns if c not in orig.columns]
    cols_removed = [c for c in orig.columns if c not in mod.columns]
    return CompareResponse(
        original_rows=len(orig),
        modified_rows=len(mod),
        original_columns=len(orig.columns),
        modified_columns=len(mod.columns),
        rows_changed=abs(len(orig) - len(mod)),
        columns_added=cols_added,
        columns_removed=cols_removed,
        operations=sess.fixes_applied,
    )


@router.get("/compare/stats")
def compare_stats(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Full stat row for the Compare tab header (1:1 with Streamlit)."""
    if sess.original_df is None:
        raise HTTPException(status_code=400, detail="No original snapshot available.")
    return _compare_stats(sess.original_df, sess.df)


@router.get("/compare/by-column")
def compare_by_column(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Per-CDE change ledger across the WHOLE diff.

    Returns one row per critical data element that has any changed cells,
    classified by dominant change type (Modified / Standardised /
    Cleared / Backfilled) with up to 3 before/after samples per column.
    Drives the new Compare page narrative summary so stewards don't have
    to scan every row to see what happened.
    """
    if sess.original_df is None:
        raise HTTPException(status_code=400, detail="No original snapshot available.")
    return _per_column_changes(sess.original_df, sess.df)


@router.get("/compare/cells")
def compare_cells(
    columns: str = Query(..., description="Comma-separated column names"),
    start_row: int = Query(0, ge=0),
    num_rows: int = Query(50, ge=1, le=500),
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Windowed cell-level diff with per-cell flags (modified/added/removed)."""
    if sess.original_df is None:
        raise HTTPException(status_code=400, detail="No original snapshot available.")
    cols = [c.strip() for c in columns.split(",") if c.strip()]
    if not cols:
        raise HTTPException(status_code=400, detail="At least one column required")
    return _cell_diff(sess.original_df, sess.df, cols, start_row, num_rows)


@router.post("/reset")
def reset(sess: SessionData = Depends(require_dataframe)) -> dict:
    if sess.original_df is None:
        raise HTTPException(status_code=400, detail="Nothing to reset.")
    sess.df = sess.original_df.copy()
    sess.fixes_applied = []
    sess.column_profiles = {}
    sess.quality_report = None
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    return {"ok": True, "rows": len(sess.df), "columns": len(sess.df.columns)}


@router.post("/export")
def export(
    format: str = Query("csv"),
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
):
    df = sess.df
    fmt = format.lower()
    buf = io.BytesIO()
    media = "application/octet-stream"
    ext = fmt
    if fmt == "csv":
        df.to_csv(buf, index=False)
        media = "text/csv"
    elif fmt in ("xlsx", "excel"):
        with pd.ExcelWriter(buf, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Data")
        media = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        ext = "xlsx"
    elif fmt == "parquet":
        df.to_parquet(buf, index=False)
    elif fmt == "json":
        text = df.to_json(orient="records")
        buf.write(text.encode("utf-8"))
        media = "application/json"
    elif fmt == "feather":
        df.reset_index(drop=True).to_feather(buf)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

    buf.seek(0)
    fname = f"{Path(sess.filename).stem}.{ext}"

    # Mark the project as exported so the Home tile reflects completion.
    # The user can still continue editing — opening a project again does
    # not flip it back; the status just records the latest milestone.
    if sess.active_project_id:
        project = (
            db.query(Project).filter(Project.id == sess.active_project_id).one_or_none()
        )
        if project is not None and project.status != "exported":
            project.status = "exported"
            db.commit()

    return StreamingResponse(
        buf,
        media_type=media,
        headers={"Content-Disposition": f"attachment; filename={fname}"},
    )


# ──────────────────────────────────────────────────────────────────────
# Streamlit-parity additions: raw upload preview, Excel sheet listing,
# clear-all, file-info, column summary, database connector
# ──────────────────────────────────────────────────────────────────────

@router.post("/upload-raw")
async def upload_raw(
    file: UploadFile = File(...),
    sess: SessionData = Depends(get_session),
) -> dict:
    """Save the uploaded file to a temp path WITHOUT parsing — returns the
    file path, file type, and Excel sheet list (if applicable).

    Mirrors the Streamlit ChunkedFileUploader.upload_with_progress step where
    the file is staged before the user picks the header row / sheet.
    """
    suffix = Path(file.filename or "data.csv").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name

    sheets: Optional[List[str]] = None
    file_type = "csv"
    if suffix in (".xlsx", ".xls", ".xlsm"):
        try:
            xls = pd.ExcelFile(tmp_path)
            sheets = list(xls.sheet_names)
            file_type = "excel"
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Failed to read Excel: {exc}")
    elif suffix in (".csv", ".tsv", ".txt"):
        file_type = "csv"
    elif suffix in (".json", ".jsonl"):
        file_type = "json"
    elif suffix in (".parquet", ".pq"):
        file_type = "parquet"
    elif suffix in (".feather", ".ftr"):
        file_type = "feather"

    sess.file_path = tmp_path
    sess.filename = file.filename or "dataset"
    return {
        "file_path": tmp_path,
        "filename": sess.filename,
        "size_bytes": int(os.path.getsize(tmp_path)),
        "file_type": file_type,
        "sheets": sheets,
    }


@router.get("/raw-preview")
def raw_preview(
    n_rows: int = Query(20, ge=1, le=200),
    sheet_name: Optional[str] = Query(default=None),
    sess: SessionData = Depends(get_session),
) -> dict:
    """Return the first n_rows of the staged file with NO header row applied.

    Used by the React "configure header" step that mirrors the Streamlit
    `loader.load_fast_preview(n_rows=20, header=None)` call.
    """
    if not sess.file_path or not os.path.exists(sess.file_path):
        raise HTTPException(status_code=400, detail="No file uploaded yet")

    suffix = Path(sess.file_path).suffix.lower()
    try:
        if suffix in (".xlsx", ".xls", ".xlsm"):
            target_sheet = sheet_name
            if not target_sheet:
                xls = pd.ExcelFile(sess.file_path)
                target_sheet = xls.sheet_names[0]
            df = pd.read_excel(sess.file_path, sheet_name=target_sheet, header=None, nrows=n_rows)
        elif suffix == ".csv":
            df = pd.read_csv(sess.file_path, header=None, nrows=n_rows, low_memory=False)
        elif suffix == ".tsv":
            df = pd.read_csv(sess.file_path, sep="\t", header=None, nrows=n_rows, low_memory=False)
        elif suffix == ".txt":
            df = pd.read_csv(sess.file_path, header=None, nrows=n_rows, low_memory=False)
        elif suffix == ".json":
            df = pd.read_json(sess.file_path).head(n_rows)
            df.columns = list(range(len(df.columns)))
        elif suffix == ".jsonl":
            df = pd.read_json(sess.file_path, lines=True).head(n_rows)
            df.columns = list(range(len(df.columns)))
        elif suffix in (".parquet", ".pq"):
            df = pd.read_parquet(sess.file_path).head(n_rows)
            df.columns = list(range(len(df.columns)))
        elif suffix in (".feather", ".ftr"):
            df = pd.read_feather(sess.file_path).head(n_rows)
            df.columns = list(range(len(df.columns)))
        else:
            raise HTTPException(status_code=400, detail=f"Unsupported file type: {suffix}")
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Preview failed: {exc}")

    df = df.where(pd.notnull(df), None)
    return {
        "rows": df.astype(object).where(pd.notnull(df), None).to_dict(orient="records"),
        "n_columns": int(len(df.columns)),
        "n_rows_returned": int(len(df)),
    }


@router.post("/load-from-staged")
def load_from_staged(
    sheet_name: Optional[str] = Form(default=None),
    header_row: int = Form(default=0),
    sess: SessionData = Depends(get_session),
    db: Session = Depends(get_db),
) -> LoadResponse:
    """Parse the already-staged file with the chosen sheet + header row."""
    if not sess.file_path or not os.path.exists(sess.file_path):
        raise HTTPException(status_code=400, detail="No file staged. Upload first.")

    suffix = Path(sess.file_path).suffix.lower()
    try:
        df, sheets, selected_sheet = load_dataframe(
            sess.file_path, suffix, sheet_name=sheet_name, header_row=header_row,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to read file: {exc}")

    sess.df = df
    sess.original_df = df.copy()
    sess.sheet_name = selected_sheet
    sess.column_profiles = {}
    sess.quality_report = None
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    sess.fixes_applied = []

    try:
        log_action("file_loaded", detail=sess.filename, category="load",
                   row_count=len(df), col_count=len(df.columns), filename=sess.filename)
    except Exception:
        pass

    _persist_to_active_project(sess, db)

    return LoadResponse(
        filename=sess.filename,
        rows=len(df),
        columns=len(df.columns),
        column_names=list(df.columns.astype(str)),
        dtypes={c: str(df[c].dtype) for c in df.columns},
        preview=safe_records(df, limit=50),
        sheets=sheets,
    )


@router.get("/file-info")
def file_info(sess: SessionData = Depends(get_session)) -> dict:
    """Current dataset metadata. Source of truth is ``sess.df`` — the
    upload tempfile may have been cleaned up or the working DataFrame
    may have been restored from a project's parquet snapshot (no
    ``file_path`` in that case).
    """
    if sess.df is None:
        return {"loaded": False}
    size = 0
    if sess.file_path and os.path.exists(sess.file_path):
        try:
            size = int(os.path.getsize(sess.file_path))
        except OSError:
            size = 0
    if size == 0:
        # Estimate from the in-memory DataFrame so the UI doesn't show 0.0 MB.
        try:
            size = int(sess.df.memory_usage(deep=True).sum())
        except Exception:
            size = 0
    return {
        "loaded": True,
        "file_path": sess.file_path,
        "filename": sess.filename,
        "size_bytes": size,
        "size_mb": round(size / 1024 / 1024, 2),
        "rows": int(len(sess.df)),
        "columns": int(len(sess.df.columns)),
    }


@router.get("/column-summary")
def column_summary(sess: SessionData = Depends(require_dataframe)) -> List[Dict[str, Any]]:
    """Verbatim port of the Streamlit Column Summary table."""
    df = sess.df
    out: List[Dict[str, Any]] = []
    n = len(df)
    for col in df.columns:
        null_count = int(df[col].isnull().sum())
        null_pct = (null_count / n * 100) if n else 0.0
        out.append({
            "Column": str(col),
            "Type": str(df[col].dtype),
            "Non-Null": f"{n - null_count:,}",
            "Null %": f"{null_pct:.1f}%",
            "Unique": int(df[col].nunique()),
        })
    return out


@router.post("/clear")
def clear_data(sess: SessionData = Depends(get_session), db: Session = Depends(get_db)) -> dict:
    """Streamlit 'Clear All Data' / 'Load Different File' — reset the session."""
    sess.df = None
    sess.original_df = None
    sess.file_path = None
    sess.filename = "dataset"
    sess.sheet_name = None
    sess.column_profiles = {}
    sess.quality_report = None
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    sess.ai_validation_rules = None
    sess.fixes_applied = []
    sess.dq_config = {}
    sess.reject_df = None
    sess.validation_history = []
    sess.columns_of_interest = []
    sess.semantic_glossary = None
    # Wipe the project's on-disk working DataFrame too — Clear All means
    # the user wants a clean slate, not a hidden parquet to be re-loaded
    # on the next /projects/{id} open.
    if sess.active_project_id:
        clear_working(sess.active_project_id)
        project = (
            db.query(Project)
            .filter(Project.id == sess.active_project_id)
            .one_or_none()
        )
        if project is not None:
            project.dataset_filename = None
            project.dataset_rows = None
            project.dataset_columns = None
            project.dataset_size_bytes = None
            project.status = "empty"
            db.commit()
    return {"ok": True}


# ─── Columns of interest ──────────────────────────────────────────────


class ColumnsOfInterestBody(BaseModel):
    selected: List[str]


def _canonical_columns_for_project(project: Optional[Project]) -> List[str]:
    """Union of ``expected_columns`` across every table in the project's stream.

    Returns an empty list for ``file_upload`` projects or any (system, stream)
    pair not present in the catalog — in which case the picker falls back to
    the dataset's actual columns (the legacy behaviour).
    """
    if project is None:
        return []
    if project.system_id == "file_upload":
        return []
    tables = STREAM_SCHEMAS.get((project.system_id, project.stream_id))
    if not tables:
        return []
    seen: Dict[str, None] = {}
    for table in tables:
        for col in table.get("expected_columns", []):
            if col not in seen:
                seen[col] = None
    return list(seen.keys())


@router.get("/columns-of-interest")
def get_columns_of_interest(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """Return the picker column list plus the user's current selection.

    For ERP-style projects (system has a catalog entry for the chosen stream)
    the picker shows the **canonical** column set so the user sees every
    standard field they could mark as a CDE — including ones missing from
    their current extract (which are returned with ``in_data=False`` and
    cannot be selected). For file-upload projects this collapses to the
    legacy "show whatever's in the dataframe" behaviour.
    """
    data_cols = [str(c) for c in sess.df.columns]
    data_set = set(data_cols)

    project: Optional[Project] = None
    if sess.active_project_id and sess.user and sess.user.get("username"):
        project = (
            db.query(Project)
            .filter(
                Project.id == sess.active_project_id,
                Project.user_username == sess.user["username"],
            )
            .one_or_none()
        )

    canonical = _canonical_columns_for_project(project)
    if canonical:
        # Canonical columns first (in catalog order), then any extras the
        # user happens to have in their extract that aren't in the catalog.
        canonical_set = set(canonical)
        extras = [c for c in data_cols if c not in canonical_set]
        all_cols = canonical + extras
        in_data_flags = {c: (c in data_set) for c in all_cols}
        schema = {
            "system_id": project.system_id,
            "system_label": project.system_label,
            "stream_id": project.stream_id,
            "stream_label": project.stream_label,
            "is_canonical": True,
        }
    else:
        all_cols = data_cols
        in_data_flags = {c: True for c in all_cols}
        schema = {
            "system_id": project.system_id if project else None,
            "system_label": project.system_label if project else None,
            "stream_id": project.stream_id if project else None,
            "stream_label": project.stream_label if project else None,
            "is_canonical": False,
        }

    # Look up cached AI-generated meta. Cache is invalidated automatically when
    # the column set changes (different fingerprint). A cache that contains
    # *only* fallback entries (no successful AI rows) is treated as missing
    # so a previously-poisoned cache can self-heal on the next reload.
    fingerprint = _cde_fingerprint(all_cols)
    cached_meta: Optional[Dict[str, Dict[str, Any]]] = None
    if project is not None:
        cached_meta = load_cde_meta(project.id, fingerprint)
        if cached_meta is not None and not any(
            (v or {}).get("source") == "ai" for v in cached_meta.values()
        ):
            cached_meta = None

    if cached_meta is not None:
        meta: Dict[str, Dict[str, Any]] = {col: dict(cached_meta.get(col, {})) for col in all_cols}
        glossary_status = "ready"
    else:
        # No AI meta yet — return a minimal placeholder so the picker renders
        # immediately. The frontend will call POST .../generate-glossary which
        # invokes the LLM and persists the result for subsequent loads.
        meta = {col: {"description": "", "recommended": False, "source": "pending"} for col in all_cols}
        glossary_status = "missing"

    # Pre-select strategy:
    #   1. user has an explicit saved selection → restore it.
    #   2. AI meta is cached → start with the AI-recommended columns.
    #   3. otherwise → start with every in-data column (preserves old behaviour
    #      until the AI run finishes; the frontend will refetch and update).
    stored = [c for c in sess.columns_of_interest if c in data_set]
    if stored:
        default_selected = stored
    elif glossary_status == "ready":
        recommended_in_data = [
            c for c in all_cols
            if in_data_flags.get(c) and meta.get(c, {}).get("recommended")
        ]
        default_selected = recommended_in_data if recommended_in_data else [
            c for c in all_cols if in_data_flags.get(c)
        ]
    else:
        default_selected = [c for c in all_cols if in_data_flags.get(c)]

    # Stamp the in_data flag into each meta record so the frontend can
    # disable canonical-but-missing fields with a single lookup.
    for col in all_cols:
        meta.setdefault(col, {})["in_data"] = bool(in_data_flags.get(col))

    return {
        "all": all_cols,
        "selected": default_selected,
        "explicit": bool(sess.columns_of_interest),
        "meta": meta,
        "schema": schema,
        "glossary_status": glossary_status,
        "glossary_fingerprint": fingerprint,
    }


@router.post("/columns-of-interest/generate-glossary")
def generate_columns_glossary(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """Run the AI recommender for the current dataset and cache the result.

    Called by the picker UI the first time a project is opened (or when the
    user clicks "Regenerate"). One batched LLM call per ~50 columns; the
    output is keyed on a column-set fingerprint so re-opening the project
    later short-circuits straight to the cache.
    """
    data_cols = [str(c) for c in sess.df.columns]
    data_set = set(data_cols)

    project: Optional[Project] = None
    if sess.active_project_id and sess.user and sess.user.get("username"):
        project = (
            db.query(Project)
            .filter(
                Project.id == sess.active_project_id,
                Project.user_username == sess.user["username"],
            )
            .one_or_none()
        )

    canonical = _canonical_columns_for_project(project)
    if canonical:
        canonical_set = set(canonical)
        extras = [c for c in data_cols if c not in canonical_set]
        all_cols = canonical + extras
        in_data_flags = {c: (c in data_set) for c in all_cols}
        schema_hint = {
            "system_id": project.system_id,
            "system_label": project.system_label,
            "stream_id": project.stream_id,
            "stream_label": project.stream_label,
        }
    else:
        all_cols = data_cols
        in_data_flags = {c: True for c in all_cols}
        schema_hint = (
            {
                "system_id": project.system_id,
                "system_label": project.system_label,
                "stream_id": project.stream_id,
                "stream_label": project.stream_label,
            }
            if project
            else None
        )

    # Build a temporary frame whose columns match all_cols so the recommender
    # can sample even columns that exist only in the canonical schema (it will
    # get empty samples for canonical-but-missing fields, which is fine —
    # the LLM still has the name + schema context to reason from).
    import pandas as _pd
    frame_cols = {}
    for col in all_cols:
        if col in sess.df.columns:
            frame_cols[col] = sess.df[col]
        else:
            frame_cols[col] = _pd.Series([], dtype="object")
    df_for_llm = _pd.DataFrame(frame_cols)

    fingerprint = _cde_fingerprint(all_cols)

    if not _llm_available():
        # Credentials missing: hand back the dtype fallback but DO NOT cache —
        # the moment the user sets up Azure OpenAI, a Regenerate click should
        # produce real descriptions without hitting a stale cache.
        meta = _cde_dtype_fallback(df_for_llm)
        for col in all_cols:
            meta.setdefault(col, {})["in_data"] = bool(in_data_flags.get(col))
        return {
            "ok": True,
            "meta": meta,
            "glossary_fingerprint": fingerprint,
            "glossary_status": "fallback",
            "warning": (
                "Azure OpenAI is not configured (AZURE_OPENAI_ENDPOINT / KEY / DEPLOYMENT). "
                "Showing dtype + sample preview only."
            ),
        }

    try:
        meta = _generate_cde_meta(df_for_llm, schema_hint=schema_hint)
    except CDERecommenderError as exc:
        # Real LLM failure — bubble up so the picker shows its Retry alert
        # with the actual reason. Don't poison the on-disk cache.
        raise HTTPException(status_code=502, detail=str(exc))

    if project is not None:
        save_cde_meta(project.id, fingerprint, meta)

    for col in all_cols:
        meta.setdefault(col, {})["in_data"] = bool(in_data_flags.get(col))

    return {
        "ok": True,
        "meta": meta,
        "glossary_fingerprint": fingerprint,
        "glossary_status": "ready",
    }


@router.post("/columns-of-interest")
def set_columns_of_interest(
    body: ColumnsOfInterestBody,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Persist the user's selection of columns-of-interest for this session."""
    all_cols = {str(c) for c in sess.df.columns}
    unknown = [c for c in body.selected if c not in all_cols]
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown columns: {', '.join(unknown[:5])}",
        )
    selected_set = set(body.selected)
    previous = list(sess.columns_of_interest)
    sess.columns_of_interest = [str(c) for c in sess.df.columns if str(c) in selected_set]
    # Selection drives every downstream analytical step (profiling, AI rules,
    # quality apply). When scope changes, those caches become stale — drop
    # them so the user re-runs against the new scope explicitly.
    if previous != sess.columns_of_interest:
        sess.column_profiles = {}
        sess.quality_report = None
        sess.ai_validation_rules = None
        sess.semantic_glossary = None
        if sess.active_project_id:
            save_rules(sess.active_project_id, None)
            save_glossary(sess.active_project_id, None)
    # Persist the scope selection itself.
    if sess.active_project_id:
        save_scope(sess.active_project_id, sess.columns_of_interest)
    return {
        "ok": True,
        "selected": sess.columns_of_interest,
        "count": len(sess.columns_of_interest),
    }


# ─── Database connector ───────────────────────────────────────────────

class BuildUrlBody(BaseModel):
    engine_label: str
    host: str = ""
    port: int = 0
    database: str = ""
    username: str = ""
    password: str = ""


class ConnectBody(BaseModel):
    url: str


class DbLoadBody(BaseModel):
    url: str
    table: Optional[str] = None
    custom_query: Optional[str] = None


@router.get("/db/engines")
def db_engines() -> List[Dict[str, Any]]:
    return list_supported_engines()


@router.post("/db/build-url")
def db_build_url(body: BuildUrlBody) -> dict:
    try:
        url = _build_url(
            body.engine_label,
            host=body.host,
            port=body.port,
            database=body.database,
            username=body.username,
            password=body.password,
        )
    except Exception as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    return {"url": url}


@router.post("/db/connect")
def db_connect(body: ConnectBody) -> dict:
    try:
        ok, tables = connect_and_list(body.url)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Connection failed: {exc}")
    if not ok:
        raise HTTPException(status_code=400, detail="Connection test failed — check your credentials and host.")
    return {"ok": True, "tables": tables}


@router.post("/db/load")
def db_load(body: DbLoadBody, sess: SessionData = Depends(get_session)) -> dict:
    try:
        df = load_from_database(body.url, body.table, body.custom_query)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Load failed: {exc}")

    sess.df = df.copy()
    sess.original_df = df.copy()
    sess.filename = body.table or "query_result"
    sess.column_profiles = {}
    sess.quality_report = None
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    sess.fixes_applied = []

    try:
        log_action(
            "Database Load",
            detail=f"Table={body.table}, rows={len(df)}",
            username=(sess.user or {}).get("username", "system") or "system",
            category="load",
            row_count=len(df), col_count=len(df.columns),
        )
    except Exception:
        pass

    return {
        "ok": True,
        "filename": sess.filename,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "column_names": list(df.columns.astype(str)),
    }
