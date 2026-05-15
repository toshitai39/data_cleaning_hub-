"""SQLAlchemy ORM models.

Users are persisted in the ``users`` table so registrations survive a
Render redeploy / container restart (Render's filesystem is ephemeral —
users written to ``auth/users.json`` at runtime would be wiped on the
next deploy). ``auth/users.json`` is now seed data only, copied into
the table on first startup.
"""
from __future__ import annotations

import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    String, Integer, DateTime, Float, JSON, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from .db import Base


def _new_project_id() -> str:
    """Short, opaque, URL-safe project ID — e.g. ``proj_d4f81a6c``."""
    return f"proj_{uuid.uuid4().hex[:12]}"


class User(Base):
    """Authenticated user — primary identity for project ownership.

    Username is the natural key (no surrogate id) because projects
    already reference users by ``user_username`` string. Password is a
    SHA-256 hex digest of the salted password (same scheme as the legacy
    ``auth/users.json``).
    """

    __tablename__ = "users"

    username: Mapped[str] = mapped_column(String(64), primary_key=True)
    name: Mapped[str] = mapped_column(String(120), nullable=False)
    password: Mapped[str] = mapped_column(String(128), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())


class Project(Base):
    """One analysis run owned by one user.

    The ``status`` field tracks where the user is in the pipeline so the
    Home page can render a "Resume" or "Open report" button.
    """

    __tablename__ = "projects"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_new_project_id)
    user_username: Mapped[str] = mapped_column(String(64), nullable=False, index=True)

    name: Mapped[str] = mapped_column(String(200), nullable=False)
    system_id: Mapped[str] = mapped_column(String(40), nullable=False)
    system_label: Mapped[str] = mapped_column(String(120), nullable=False)
    stream_id: Mapped[str] = mapped_column(String(40), nullable=False)
    stream_label: Mapped[str] = mapped_column(String(120), nullable=False)

    status: Mapped[str] = mapped_column(String(32), default="empty")
    # empty | data_loaded | profiled | rules_generated | cleansed | exported | archived

    # Cached dataset metadata (mirrors what /data/file-info would report).
    dataset_filename: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    dataset_rows: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dataset_columns: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    dataset_size_bytes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)

    # Cached rollups for the Home dashboard — refreshed when the session
    # snapshots itself. JSON keeps the schema flexible during early dev.
    quality_score: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    rules_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    issues_total: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    columns_in_scope: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    # Per-table upload metadata for multi-table streams (e.g. SAP Vendor).
    # Shape: { "<table_id>": {"filename": "...", "rows": N, "columns": N,
    #                          "size_bytes": N, "uploaded_at": "...iso..."} }
    tables_meta: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)
    extra: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now(),
    )
    last_opened_at: Mapped[Optional[datetime]] = mapped_column(DateTime, nullable=True)

    __table_args__ = (
        Index("ix_projects_user_updated", "user_username", "updated_at"),
    )

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "system": {"id": self.system_id, "label": self.system_label},
            "stream": {"id": self.stream_id, "label": self.stream_label},
            "status": self.status,
            "dataset": {
                "filename": self.dataset_filename,
                "rows": self.dataset_rows,
                "columns": self.dataset_columns,
                "size_bytes": self.dataset_size_bytes,
            },
            "quality_score": self.quality_score,
            "rules_total": self.rules_total,
            "issues_total": self.issues_total,
            "columns_in_scope": self.columns_in_scope,
            "tables_meta": self.tables_meta or {},
            "created_at": self.created_at.isoformat() if self.created_at else None,
            "updated_at": self.updated_at.isoformat() if self.updated_at else None,
            "last_opened_at": self.last_opened_at.isoformat() if self.last_opened_at else None,
        }
