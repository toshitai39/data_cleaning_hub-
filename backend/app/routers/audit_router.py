"""Audit log retrieval."""
from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Query

from core.audit_log import get_recent_logs

from ..schemas import AuditEntry

router = APIRouter(prefix="/audit", tags=["audit"])


@router.get("/", response_model=List[AuditEntry])
def list_audit(
    limit: int = Query(100, ge=1, le=1000),
    category: Optional[str] = None,
):
    try:
        rows = get_recent_logs(limit=limit, category=category)
    except Exception:
        rows = []
    out = []
    for r in rows:
        out.append(AuditEntry(
            id=int(r.get("id", 0) or 0),
            timestamp=str(r.get("timestamp", "")),
            username=r.get("username"),
            action=r.get("action"),
            detail=r.get("detail"),
            category=r.get("category"),
            row_count=r.get("row_count"),
            col_count=r.get("col_count"),
            filename=r.get("filename"),
        ))
    return out
