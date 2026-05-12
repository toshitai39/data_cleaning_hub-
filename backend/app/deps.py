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


def require_dataframe(x_session_id: Optional[str] = Header(default=None)) -> SessionData:
    sess = get_session(x_session_id)
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
