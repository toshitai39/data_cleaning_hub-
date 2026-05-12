"""Project workspace endpoints.

Every endpoint is gated by the logged-in user — users only ever see and
mutate their own projects. The session's ``active_project_id`` is set when
the user opens a project; subsequent data / rule / quality endpoints work
inside that scope.

Endpoints
---------
  GET    /projects                 list my projects
  POST   /projects                 create new
  GET    /projects/{id}            open a project (sets active session)
  PATCH  /projects/{id}            rename / archive
  DELETE /projects/{id}            delete (also wipes session if active)
  GET    /projects/catalog         systems + streams for the wizard
  GET    /projects/dashboard       roll-up metrics for the Home page
"""
from __future__ import annotations

import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, File, Header, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import desc
from sqlalchemy.orm import Session

from ..catalog import (
    STREAMS,
    SYSTEMS,
    get_org_setup_tables,
    get_stream,
    get_stream_tables,
    get_system,
)
from ..db import get_db
from ..deps import get_session
from ..models import Project
from ..services.loader import load_dataframe
from ..services.project_storage import (
    delete_project_storage,
    delete_table,
    list_uploaded_tables,
    load_dq_config,
    load_glossary,
    load_rejected,
    load_rules,
    load_scope,
    load_table,
    load_working,
    save_dq_config,
    save_glossary,
    save_rejected,
    save_rules,
    save_scope,
    save_table,
    save_working,
)
from ..session_store import SessionData, store

router = APIRouter(prefix="/projects", tags=["projects"])


# ─── dependencies ────────────────────────────────────────────────────


def require_logged_in(sess: SessionData = Depends(get_session)) -> SessionData:
    if not sess.user or not sess.user.get("username"):
        raise HTTPException(status_code=401, detail="Not signed in")
    return sess


def require_owned_project(
    project_id: str,
    sess: SessionData = Depends(require_logged_in),
    db: Session = Depends(get_db),
) -> Project:
    """Look up a project and confirm the current user owns it.

    Returns 404 — not 403 — on a cross-user access so the existence of
    another user's project doesn't leak.
    """
    p = (
        db.query(Project)
        .filter(
            Project.id == project_id,
            Project.user_username == sess.user["username"],
        )
        .one_or_none()
    )
    if not p:
        raise HTTPException(status_code=404, detail="Project not found")
    return p


# ─── schemas ─────────────────────────────────────────────────────────


class CreateProjectBody(BaseModel):
    system_id: str
    stream_id: str
    name: Optional[str] = Field(default=None, max_length=200)


class UpdateProjectBody(BaseModel):
    name: Optional[str] = Field(default=None, max_length=200)
    status: Optional[str] = Field(default=None)


# ─── catalog (for the wizard) ────────────────────────────────────────


@router.get("/catalog")
def get_catalog(_: SessionData = Depends(require_logged_in)) -> dict:
    return {"systems": SYSTEMS, "streams": STREAMS}


@router.get("/catalog/schema")
def get_catalog_schema(
    system_id: str,
    stream_id: str,
    _: SessionData = Depends(require_logged_in),
) -> dict:
    """Return the physical-table schema for a (system, stream) combo and the
    org-setup tables of that ERP. The New Analysis wizard calls this once
    the user has picked system + stream, to render the table-upload step.
    """
    return {
        "system_id": system_id,
        "stream_id": stream_id,
        "tables": get_stream_tables(system_id, stream_id),
        "org_setup_tables": get_org_setup_tables(system_id),
    }


# ─── dashboard rollup ───────────────────────────────────────────────


@router.get("/dashboard")
def get_dashboard(
    sess: SessionData = Depends(require_logged_in),
    db: Session = Depends(get_db),
) -> dict:
    """Aggregate metrics for the Home page — total projects, by status,
    average quality, most recently opened."""
    projects = (
        db.query(Project)
        .filter(Project.user_username == sess.user["username"])
        .all()
    )
    by_status: dict[str, int] = {}
    quality_scores: list[float] = []
    for p in projects:
        by_status[p.status] = by_status.get(p.status, 0) + 1
        if p.quality_score is not None:
            quality_scores.append(p.quality_score)
    avg_quality = (
        round(sum(quality_scores) / len(quality_scores), 1)
        if quality_scores else None
    )
    return {
        "total_projects": len(projects),
        "by_status": by_status,
        "avg_quality": avg_quality,
        "active_project_id": sess.active_project_id,
    }


# ─── CRUD ────────────────────────────────────────────────────────────


@router.get("")
def list_projects(
    sess: SessionData = Depends(require_logged_in),
    db: Session = Depends(get_db),
) -> List[dict]:
    rows = (
        db.query(Project)
        .filter(Project.user_username == sess.user["username"])
        .order_by(desc(Project.updated_at))
        .all()
    )
    return [r.to_dict() for r in rows]


@router.post("")
def create_project(
    body: CreateProjectBody,
    sess: SessionData = Depends(require_logged_in),
    db: Session = Depends(get_db),
) -> dict:
    system = get_system(body.system_id)
    stream = get_stream(body.stream_id)
    if not system:
        raise HTTPException(status_code=400, detail=f"Unknown system: {body.system_id}")
    if not stream:
        raise HTTPException(status_code=400, detail=f"Unknown stream: {body.stream_id}")
    if system.get("status") != "available":
        raise HTTPException(
            status_code=400,
            detail=f"System '{system['label']}' is not available yet — only File upload is enabled in this version.",
        )

    name = (body.name or "").strip() or f"{system['label']} · {stream['label']} · {datetime.now().strftime('%d %b %Y')}"
    project = Project(
        user_username=sess.user["username"],
        name=name,
        system_id=system["id"],
        system_label=system["label"],
        stream_id=stream["id"],
        stream_label=stream["label"],
        status="empty",
        last_opened_at=datetime.utcnow(),
    )
    db.add(project)
    db.commit()
    db.refresh(project)
    # Activate the newly created project for the calling session so the
    # next data-upload call binds to it.
    sess.active_project_id = project.id
    return project.to_dict()


def _bind_session_to_project(sess: SessionData, project: Project) -> None:
    """Replace the session's in-memory DataFrame with the project's on-disk
    working copy (if any), and reset transient analysis state so the
    incoming project doesn't inherit the outgoing project's profiles / rules.
    """
    # First, snapshot the OUTGOING project (if there was one) so its work
    # isn't lost. We only do this when leaving a different project — if
    # the user re-opens the same project, the in-memory copy is canonical.
    outgoing_id = sess.active_project_id
    if outgoing_id and outgoing_id != project.id:
        if sess.df is not None:
            save_working(outgoing_id, sess.df, sess.original_df)
        if isinstance(sess.ai_validation_rules, pd.DataFrame):
            save_rules(outgoing_id, sess.ai_validation_rules)
        if sess.semantic_glossary:
            save_glossary(outgoing_id, sess.semantic_glossary)
        if sess.columns_of_interest:
            save_scope(outgoing_id, sess.columns_of_interest)
        if sess.dq_config:
            save_dq_config(outgoing_id, sess.dq_config)
        if isinstance(sess.reject_df, pd.DataFrame) and not sess.reject_df.empty:
            save_rejected(outgoing_id, sess.reject_df)

    # Wipe transient analysis state — different project, different rules.
    sess.df = None
    sess.original_df = None
    sess.file_path = None
    sess.filename = "dataset"
    sess.sheet_name = None
    sess.column_profiles = {}
    sess.quality_report = None
    sess.ai_validation_rules = None
    sess.fixes_applied = []
    sess.dq_config = {}
    sess.reject_df = None
    sess.validation_history = []
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    sess.columns_of_interest = []
    sess.semantic_glossary = None

    # Load this project's working DataFrame + analysis artifacts from disk.
    working, original = load_working(project.id)
    if working is not None:
        sess.df = working
        sess.original_df = original if original is not None else working.copy()
        sess.filename = project.dataset_filename or "dataset"
    rules = load_rules(project.id)
    if rules is not None:
        sess.ai_validation_rules = rules
    glossary = load_glossary(project.id)
    if glossary:
        sess.semantic_glossary = glossary
    scope = load_scope(project.id)
    if scope:
        sess.columns_of_interest = scope
    dq_cfg = load_dq_config(project.id)
    if dq_cfg:
        sess.dq_config = dq_cfg
    rejected = load_rejected(project.id)
    if rejected is not None:
        sess.reject_df = rejected
    sess.active_project_id = project.id


@router.get("/{project_id}")
def open_project(
    project: Project = Depends(require_owned_project),
    sess: SessionData = Depends(require_logged_in),
    db: Session = Depends(get_db),
) -> dict:
    project.last_opened_at = datetime.utcnow()
    db.commit()
    _bind_session_to_project(sess, project)
    return project.to_dict()


@router.patch("/{project_id}")
def update_project(
    body: UpdateProjectBody,
    project: Project = Depends(require_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    changed = False
    if body.name is not None:
        new_name = body.name.strip()
        if new_name:
            project.name = new_name
            changed = True
    if body.status is not None:
        project.status = body.status
        changed = True
    if changed:
        db.commit()
        db.refresh(project)
    return project.to_dict()


@router.delete("/{project_id}")
def delete_project(
    project: Project = Depends(require_owned_project),
    sess: SessionData = Depends(require_logged_in),
    db: Session = Depends(get_db),
) -> dict:
    # If this was the active project, detach the session and wipe in-memory
    # state so the user doesn't keep seeing a dead project's data.
    if sess.active_project_id == project.id:
        sess.active_project_id = None
        sess.df = None
        sess.original_df = None
        sess.column_profiles = {}
        sess.ai_validation_rules = None
        sess.semantic_glossary = None
    delete_project_storage(project.id)
    db.delete(project)
    db.commit()
    return {"ok": True}


# ─── session ↔ project binding helpers ───────────────────────────────


@router.post("/{project_id}/close")
def close_project(
    project: Project = Depends(require_owned_project),
    sess: SessionData = Depends(require_logged_in),
) -> dict:
    """Detach the session from this project without deleting anything."""
    if sess.active_project_id == project.id:
        sess.active_project_id = None
    return {"ok": True}


# ─── Multi-table upload (Phase A2) ───────────────────────────────────


@router.get("/{project_id}/tables")
def list_project_tables(
    project: Project = Depends(require_owned_project),
) -> dict:
    """Return the expected table schema for this project's stream, the
    org-setup tables for its ERP, and the per-table upload status.

    The frontend's Load Data page renders one upload tile per ``expected``
    entry; entries also in ``uploaded`` get the green check.
    """
    expected = get_stream_tables(project.system_id, project.stream_id)
    org_setup = get_org_setup_tables(project.system_id)
    uploaded_meta = project.tables_meta or {}
    # Reconcile against the filesystem in case the JSON drifted.
    on_disk = set(list_uploaded_tables(project.id))
    return {
        "expected": expected,
        "org_setup_tables": org_setup,
        "uploaded": {
            tid: meta
            for tid, meta in uploaded_meta.items()
            if tid in on_disk
        },
        "missing_required": [
            t["id"] for t in expected
            if t.get("required") and t["id"] not in on_disk
        ],
    }


@router.post("/{project_id}/tables/{table_id}/upload")
async def upload_project_table(
    table_id: str,
    file: UploadFile = File(...),
    project: Project = Depends(require_owned_project),
    db: Session = Depends(get_db),
    sess: SessionData = Depends(require_logged_in),
) -> dict:
    """Upload ONE physical table for a multi-table stream.

    The file gets parsed (CSV / Excel / parquet / feather / JSON) just
    like the single-file upload path, but stored under
    ``tables/<table_id>.parquet`` instead of becoming the working copy
    immediately. Call ``POST /projects/{id}/materialize`` once all
    required tables are uploaded to stitch them into the working df.
    """
    expected = get_stream_tables(project.system_id, project.stream_id)
    if not any(t["id"] == table_id for t in expected):
        raise HTTPException(
            status_code=400,
            detail=f"Table '{table_id}' isn't part of the {project.stream_id} schema for {project.system_id}",
        )

    suffix = Path(file.filename or f"{table_id}.csv").suffix.lower()
    with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
        content = await file.read()
        tmp.write(content)
        tmp_path = tmp.name
    try:
        df, _, _ = load_dataframe(tmp_path, suffix)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Failed to parse file: {exc}")
    finally:
        # Don't leak the temp file once we have the DataFrame.
        try: os.unlink(tmp_path)
        except OSError: pass

    meta = save_table(project.id, table_id, df, original_filename=file.filename)
    meta["uploaded_at"] = datetime.utcnow().isoformat()

    # Persist meta on the project row (JSON column).
    tables_meta = dict(project.tables_meta or {})
    tables_meta[table_id] = meta
    project.tables_meta = tables_meta
    db.commit()

    return {"ok": True, "table_id": table_id, "meta": meta}


@router.delete("/{project_id}/tables/{table_id}")
def delete_project_table(
    table_id: str,
    project: Project = Depends(require_owned_project),
    db: Session = Depends(get_db),
) -> dict:
    delete_table(project.id, table_id)
    if project.tables_meta and table_id in project.tables_meta:
        tables_meta = dict(project.tables_meta)
        tables_meta.pop(table_id, None)
        project.tables_meta = tables_meta
        db.commit()
    return {"ok": True}


@router.post("/{project_id}/materialize")
def materialize_working_view(
    project: Project = Depends(require_owned_project),
    sess: SessionData = Depends(require_logged_in),
    db: Session = Depends(get_db),
) -> dict:
    """Join the project's per-table parquet files into a single working
    DataFrame and persist it as ``working.parquet``.

    Strategy: start from the ``primary`` table, then LEFT JOIN every
    ``extension`` table on its declared ``join_key``. ``lookup`` tables
    are left alone — they're typically joined on a different key (ADRC
    on ADRNR) and including them naively would blow up row counts.

    For ``file_upload`` projects this is a no-op (working.parquet is
    written directly by ``/data/upload``).
    """
    expected = get_stream_tables(project.system_id, project.stream_id)
    if not expected:
        raise HTTPException(status_code=400, detail="This project has no multi-table schema")

    primary = next((t for t in expected if t.get("role") == "primary"), None)
    if not primary:
        raise HTTPException(status_code=400, detail="Schema has no primary table")

    primary_df = load_table(project.id, primary["id"])
    if primary_df is None:
        raise HTTPException(
            status_code=400,
            detail=f"Primary table {primary['id']} hasn't been uploaded yet",
        )

    df = primary_df
    extensions_applied = []
    for t in expected:
        if t.get("role") != "extension":
            continue
        ext_df = load_table(project.id, t["id"])
        if ext_df is None:
            continue
        key = t.get("join_key")
        if not key or key not in df.columns or key not in ext_df.columns:
            continue
        df = df.merge(ext_df, on=key, how="left", suffixes=("", f"__{t['id']}"))
        extensions_applied.append(t["id"])

    # Persist the materialized view as working.parquet.
    save_working(project.id, df)
    # Mirror onto the live session if it's the active project.
    if sess.active_project_id == project.id:
        sess.df = df
        sess.original_df = df.copy()
        sess.filename = project.dataset_filename or f"{project.stream_id}_master"

    # Update Project row meta.
    project.dataset_filename = sess.filename if sess.active_project_id == project.id else (
        project.dataset_filename or f"{project.stream_id}_master"
    )
    project.dataset_rows = int(len(df))
    project.dataset_columns = int(len(df.columns))
    if project.status in ("empty", None):
        project.status = "data_loaded"
    db.commit()

    return {
        "ok": True,
        "primary": primary["id"],
        "extensions_applied": extensions_applied,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
    }
