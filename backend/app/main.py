"""FastAPI entrypoint for the Data Profiler Pro backend.

Run from the project root with:
    python -m uvicorn backend.app.main:app --host 0.0.0.0 --port 8000 --reload
"""
from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Make the original project root importable so we can re-use core/, models/, auth/, utils/.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from .db import init_db  # noqa: E402
from .routers import (  # noqa: E402  (import after sys.path tweak)
    admin_router,
    audit_router,
    auth_router,
    data_router,
    duplicates_router,
    export_router,
    profile_router,
    projects_router,
    quality_router,
    rule_generator_router,
)

app = FastAPI(
    title="Data Profiler Pro API",
    description="REST API for the Master Data Profiler — FastAPI rewrite.",
    version="2.0.0",
)

# Allow the React dev server (and same-origin prod) to call us.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "timestamp": datetime.utcnow().isoformat()}


app.include_router(auth_router.router)
app.include_router(projects_router.router)
app.include_router(data_router.router)
app.include_router(profile_router.router)
app.include_router(duplicates_router.router)
app.include_router(quality_router.router)
app.include_router(rule_generator_router.router)
app.include_router(export_router.router)
app.include_router(audit_router.router)
app.include_router(admin_router.router)


@app.on_event("startup")
def _on_startup() -> None:
    """Create the projects table on first run (idempotent)."""
    init_db()
