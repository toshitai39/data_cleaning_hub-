"""SQLAlchemy engine + session factory.

Driven by the ``DATABASE_URL`` env var:

  • Local dev (default):  sqlite:///./backend/storage/projects.db
  • Render / production:  set DATABASE_URL to a Postgres URL (Neon, Supabase,
    etc.) — the rest of the code does not change.

The choice between SQLite and Postgres is invisible to the application code
because every model is SQLAlchemy-mapped. Use the ``get_db`` dependency in
FastAPI routes — it yields a session and closes it after the request.
"""
from __future__ import annotations

import os
from pathlib import Path
from typing import Generator

from sqlalchemy import create_engine, inspect, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


_DEFAULT_SQLITE_PATH = (
    Path.home() / "Library" / "Application Support" / "MasterDataProfiler"
    / "storage" / "projects.db"
)
_DEFAULT_SQLITE_PATH.parent.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "DATABASE_URL",
    f"sqlite:///{_DEFAULT_SQLITE_PATH.as_posix()}",
)

# Render / Heroku hand out connection strings starting with
# ``postgres://`` but SQLAlchemy 2.x dropped support for that legacy
# prefix — it wants ``postgresql://``. Normalising here is the
# difference between "user data persists" and "boot loop on every
# deploy because the dialect is unknown".
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# SQLite needs ``check_same_thread=False`` because FastAPI hands sessions to
# worker threads; Postgres does not. Adapt connect args accordingly.
_connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}

engine = create_engine(
    DATABASE_URL,
    connect_args=_connect_args,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False, future=True)


class Base(DeclarativeBase):
    """Common SQLAlchemy declarative base for every model in this app."""


def get_db() -> Generator[Session, None, None]:
    """FastAPI dependency that yields a database session per request."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create every table declared on ``Base`` if it doesn't already
    exist, and add any new columns to existing tables (lightweight
    auto-migration so model evolutions don't require a manual ALTER).

    Called once at application startup. Safe to run repeatedly.
    """
    # Import models so they register on ``Base.metadata`` before create_all.
    from . import models  # noqa: F401
    Base.metadata.create_all(bind=engine)

    # Light forward-only migration: for every declared table, compare
    # the live columns to the model's expected columns and ``ALTER TABLE
    # ADD COLUMN`` whatever's missing. SQLite and Postgres both support
    # ``ADD COLUMN`` without a backfill; the new column lands as NULL,
    # which is fine for nullable JSON / metadata fields.
    inspector = inspect(engine)
    is_sqlite = engine.url.get_backend_name() == "sqlite"
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            live_cols = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in live_cols:
                    continue
                # Render a portable column type. SQLite has loose typing
                # so a generic ``TEXT`` works for everything we add; on
                # Postgres we let SQLAlchemy compile the real type.
                if is_sqlite:
                    col_type = "TEXT"
                else:
                    col_type = col.type.compile(dialect=engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE {table.name} ADD COLUMN {col.name} {col_type}'
                ))
