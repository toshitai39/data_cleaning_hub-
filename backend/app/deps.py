"""Common FastAPI dependencies."""
from __future__ import annotations

from fastapi import Header, HTTPException
from typing import Optional

from .session_store import SessionData, resolve_session_id, store


def get_session(x_session_id: Optional[str] = Header(default=None)) -> SessionData:
    sid = resolve_session_id(x_session_id)
    return store.get(sid)


def require_dataframe(x_session_id: Optional[str] = Header(default=None)) -> SessionData:
    sess = get_session(x_session_id)
    if sess.df is None:
        raise HTTPException(status_code=400, detail="No dataset loaded. Upload a file first.")
    return sess
