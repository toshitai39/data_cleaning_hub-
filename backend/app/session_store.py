"""In-memory session store for per-session DataFrames and profiling state.

Each browser session gets a UUID. The React app stores it in localStorage and
sends it as the `X-Session-Id` header on every request. The store keeps the
loaded DataFrame, the original (pre-modification) DataFrame, profiling results,
duplicate groups, applied operations, and cached AI rules.

This is intentionally process-local. For a production deployment with multiple
workers, swap the dict for Redis (the API surface stays the same).
"""
from __future__ import annotations

import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class SessionData:
    session_id: str
    df: Optional[pd.DataFrame] = None
    original_df: Optional[pd.DataFrame] = None
    filename: str = "dataset"
    file_path: Optional[str] = None
    sheet_name: Optional[str] = None
    column_profiles: Dict[str, Any] = field(default_factory=dict)
    quality_report: Optional[Any] = None
    exact_duplicates: List[Any] = field(default_factory=list)
    fuzzy_duplicates: List[Any] = field(default_factory=list)
    combined_duplicates: List[Any] = field(default_factory=list)
    # cached scan params per duplicate type for re-rendering
    duplicates_meta: Dict[str, Any] = field(default_factory=dict)
    ai_validation_rules: Optional[pd.DataFrame] = None
    fixes_applied: List[Dict[str, Any]] = field(default_factory=list)
    # Data Quality tab state (mirrors st.session_state.dq_config / reject_df / history)
    dq_config: Dict[str, Any] = field(default_factory=dict)
    reject_df: Optional[pd.DataFrame] = None
    validation_history: List[Dict[str, Any]] = field(default_factory=list)
    last_access: float = field(default_factory=time.time)
    user: Optional[Dict[str, str]] = None


class SessionStore:
    """Thread-safe session registry with simple TTL eviction."""

    def __init__(self, ttl_seconds: int = 60 * 60 * 4):
        self._sessions: Dict[str, SessionData] = {}
        self._lock = threading.Lock()
        self._ttl = ttl_seconds

    def create(self) -> SessionData:
        sid = str(uuid.uuid4())
        with self._lock:
            self._sessions[sid] = SessionData(session_id=sid)
            return self._sessions[sid]

    def get(self, session_id: str, create_if_missing: bool = True) -> SessionData:
        with self._lock:
            self._evict_expired_locked()
            sess = self._sessions.get(session_id)
            if sess is None:
                if not create_if_missing:
                    raise KeyError(session_id)
                sess = SessionData(session_id=session_id)
                self._sessions[session_id] = sess
            sess.last_access = time.time()
            return sess

    def reset(self, session_id: str) -> None:
        with self._lock:
            self._sessions[session_id] = SessionData(session_id=session_id)

    def _evict_expired_locked(self) -> None:
        now = time.time()
        expired = [sid for sid, s in self._sessions.items() if now - s.last_access > self._ttl]
        for sid in expired:
            self._sessions.pop(sid, None)


store = SessionStore()


def resolve_session_id(header_value: Optional[str]) -> str:
    """Use the client's session ID if present, otherwise mint a new one."""
    return header_value if header_value else str(uuid.uuid4())
