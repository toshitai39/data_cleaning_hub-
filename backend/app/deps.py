"""Common FastAPI dependencies."""
from __future__ import annotations

from typing import List, Optional

import pandas as pd
from fastapi import Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .db import get_db
from .models import Project
from .session_store import SessionData, resolve_session_id, store


def get_session(x_session_id: Optional[str] = Header(default=None)) -> SessionData:
    sid = resolve_session_id(x_session_id)
    return store.get(sid)


def _restore_dataframe_from_disk(sess: SessionData) -> bool:
    """Lazy-load the project's working.parquet back into the session.

    The in-memory ``SessionData`` is wiped whenever uvicorn hot-reloads,
    the worker recycles, or the user picks the project up from a brand
    new browser tab. The on-disk parquet is the durable source of truth
    — this helper reads it back into ``sess.df`` so downstream endpoints
    don't have to deal with "session lost ⇒ no dataset" cascades.

    Returns True when a dataframe was restored, False otherwise.
    """
    if sess.df is not None or not sess.active_project_id:
        return False
    # Imported lazily to avoid a circular dependency between deps.py and
    # the storage layer at import time.
    from .services.project_storage import load_working
    try:
        working, original = load_working(sess.active_project_id)
    except Exception:
        return False
    if working is None or working.empty:
        return False
    sess.df = working
    if original is not None and getattr(sess, "df_original", None) is None:
        sess.df_original = original
    # Re-hydrate scope from disk so downstream endpoints see the saved
    # critical-data-element selection rather than an empty list.
    if not sess.columns_of_interest:
        try:
            from .services.project_storage import load_scope
            saved_scope = load_scope(sess.active_project_id)
            if saved_scope:
                sess.columns_of_interest = [
                    c for c in saved_scope if c in working.columns
                ]
        except Exception:
            pass
    return True


def require_dataframe(x_session_id: Optional[str] = Header(default=None)) -> SessionData:
    sess = get_session(x_session_id)
    if sess.df is None:
        # First try: rehydrate from the on-disk working parquet. Covers
        # backend hot-reloads, worker recycles, fresh tabs on existing
        # projects — anything that wiped the in-memory state but left
        # the project intact on disk.
        _restore_dataframe_from_disk(sess)
    if sess.df is None:
        raise HTTPException(status_code=400, detail="No dataset loaded. Upload a file first.")
    return sess


def scoped_columns(sess: SessionData) -> List[str]:
    """Columns the user has flagged as in-scope.

    Returns the user's saved selection (filtered to columns that still exist
    in the dataset), or every dataset column when no explicit selection has
    been saved yet. Order matches the dataset's own column order.
    """
    if sess.df is None:
        return []
    all_cols = [str(c) for c in sess.df.columns]
    if not sess.columns_of_interest:
        return all_cols
    selected = set(sess.columns_of_interest)
    return [c for c in all_cols if c in selected]


def require_active_project(
    sess: SessionData = Depends(get_session),
    db: Session = Depends(get_db),
) -> Project:
    """Resolve the user's active project, 400 if there isn't one.

    Use this on data-mutation endpoints so the user can't accidentally
    write into the wrong project. Cross-user access is impossible because
    the lookup is keyed on ``(project_id, user_username)``.
    """
    if not sess.user or not sess.user.get("username"):
        raise HTTPException(status_code=401, detail="Not signed in")
    if not sess.active_project_id:
        raise HTTPException(
            status_code=400,
            detail="No active project. Pick one from Home or create a new analysis.",
        )
    project = (
        db.query(Project)
        .filter(
            Project.id == sess.active_project_id,
            Project.user_username == sess.user["username"],
        )
        .one_or_none()
    )
    if not project:
        # Stale binding — session points at a project the user no longer owns.
        sess.active_project_id = None
        raise HTTPException(status_code=400, detail="Active project no longer exists.")
    return project


def scoped_dataframe(sess: SessionData) -> pd.DataFrame:
    """Return ``sess.df`` narrowed to :func:`scoped_columns`.

    Falls back to the full DataFrame when there is no explicit selection or
    the saved selection is now empty (e.g. all referenced columns were
    dropped). The returned frame is a view-like slice — callers should not
    mutate it in place if they need the full dataset intact.
    """
    if sess.df is None:
        return sess.df  # type: ignore[return-value]
    cols = scoped_columns(sess)
    if not cols or len(cols) == len(sess.df.columns):
        return sess.df
    return sess.df[cols]
