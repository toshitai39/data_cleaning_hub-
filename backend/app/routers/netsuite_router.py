"""NetSuite SuiteQL connector endpoints.

Surface area:

    POST /netsuite/test-connection      → verify creds against DUAL
    POST /netsuite/credentials          → save creds (encrypted) to project.extra
    DELETE /netsuite/credentials        → remove saved creds
    GET  /netsuite/credentials/status   → "saved" / "not_saved" + masked Account ID
    GET  /netsuite/streams              → list streams + tables NetSuite supports
    POST /netsuite/load-stream          → fetch every table in one stream into the session

Credentials are encrypted at rest via ``credential_vault`` keyed off
SECRET_KEY. The frontend only ever sends the raw five fields on
``test-connection`` or ``credentials``; subsequent ``load-stream``
calls don't take a credential payload — the router decrypts what's
saved on the project.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from ..catalog import STREAM_SCHEMAS
from ..db import get_db
from ..deps import get_session, require_active_project
from ..models import Project
from ..session_store import SessionData
from ..services import credential_vault
from ..services.netsuite_connector import (
    NetSuiteCredentials,
    get_global_credentials,
    list_supported_streams,
    query_for_table,
    run_suiteql,
    test_connection,
)
from ..services.project_storage import save_table, save_working

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/netsuite", tags=["netsuite"])


# ── Schemas ───────────────────────────────────────────────────────────────

class NetSuiteCredsBody(BaseModel):
    account_id: str = Field(min_length=1)
    consumer_key: str = Field(min_length=1)
    consumer_secret: str = Field(min_length=1)
    token_id: str = Field(min_length=1)
    token_secret: str = Field(min_length=1)


class LoadStreamBody(BaseModel):
    stream: str = Field(min_length=1)              # 'customer' / 'vendor' / ...
    tables: Optional[List[str]] = None              # subset; None = all
    row_limit: int = Field(default=1000, ge=10, le=10000)
    primary_only: bool = False                      # convenience: load just the primary


# ── Helpers ───────────────────────────────────────────────────────────────

def _resolve_creds(project: Project) -> NetSuiteCredentials:
    """Return credentials for the active project.

    Priority: global env vars (NETSUITE_*) → per-project encrypted vault.
    Global env vars win so client deployments never need per-project setup.
    """
    global_creds = get_global_credentials()
    if global_creds:
        return global_creds
    payload = credential_vault.load_credentials(project, "netsuite")
    if not payload:
        raise HTTPException(
            status_code=400,
            detail="No NetSuite credentials found. Ask your admin to set NETSUITE_* environment variables, or connect via Load Data → NetSuite.",
        )
    return NetSuiteCredentials(
        account_id=payload.get("account_id", ""),
        consumer_key=payload.get("consumer_key", ""),
        consumer_secret=payload.get("consumer_secret", ""),
        token_id=payload.get("token_id", ""),
        token_secret=payload.get("token_secret", ""),
    )


def _mask(s: str, keep: int = 4) -> str:
    """Return a masked version of a secret — keep first 2 + last 2
    chars, dots in between. Used for read-back so the UI can show
    "TD30...591" rather than re-revealing the full secret."""
    if not s:
        return ""
    if len(s) <= keep * 2:
        return "•" * len(s)
    return f"{s[:2]}•••••{s[-2:]}"


# ── Endpoints ─────────────────────────────────────────────────────────────

@router.post("/test-connection")
def netsuite_test_connection(body: NetSuiteCredsBody) -> Dict[str, Any]:
    """Verify a credential bundle works against NetSuite without saving
    it. Hits a SELECT 1 FROM DUAL — the cheapest possible round-trip
    that exercises the OAuth 1.0a signing path."""
    creds = NetSuiteCredentials(
        account_id=body.account_id,
        consumer_key=body.consumer_key,
        consumer_secret=body.consumer_secret,
        token_id=body.token_id,
        token_secret=body.token_secret,
    )
    result = test_connection(creds)
    return result


@router.post("/credentials")
def save_netsuite_credentials(
    body: NetSuiteCredsBody,
    project: Project = Depends(require_active_project),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Save (encrypted) NetSuite credentials onto the active project.

    Performs a connection test first — refuses to persist credentials
    we know won't work, so the user can't end up with a "saved" status
    that doesn't actually authenticate.
    """
    creds = NetSuiteCredentials(
        account_id=body.account_id,
        consumer_key=body.consumer_key,
        consumer_secret=body.consumer_secret,
        token_id=body.token_id,
        token_secret=body.token_secret,
    )
    test = test_connection(creds)
    if not test.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=f"NetSuite rejected those credentials: {test.get('error', 'unknown error')}",
        )
    credential_vault.save_credentials(project, "netsuite", body.dict())
    db.commit()
    return {
        "ok": True,
        "account_label": creds.account_id,
        "saved_at": datetime.utcnow().isoformat(),
    }


@router.delete("/credentials")
def delete_netsuite_credentials(
    project: Project = Depends(require_active_project),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Drop the saved NetSuite credentials from this project. Useful
    when the integration record is rotated."""
    removed = credential_vault.delete_credentials(project, "netsuite")
    if removed:
        db.commit()
    return {"ok": True, "removed": removed}


@router.get("/credentials/status")
def netsuite_credentials_status(
    project: Project = Depends(require_active_project),
) -> Dict[str, Any]:
    """Return whether credentials are available + how they were sourced.

    ``via_env=True``  → NETSUITE_* env vars are set; no per-project form needed.
    ``via_env=False`` → credentials were saved manually for this project.
    ``saved=False``   → no credentials anywhere; show the entry form.
    """
    global_creds = get_global_credentials()
    if global_creds:
        return {
            "saved": True,
            "via_env": True,
            "account_label": global_creds.account_id,
            "account_label_masked": _mask(global_creds.account_id),
        }
    payload = credential_vault.load_credentials(project, "netsuite")
    if not payload:
        return {"saved": False, "via_env": False}
    return {
        "saved": True,
        "via_env": False,
        "account_label_masked": _mask(payload.get("account_id", "")),
        "account_label": payload.get("account_id", ""),
    }


@router.get("/streams")
def list_netsuite_streams() -> Dict[str, Any]:
    """Catalog of NetSuite streams the connector can fetch.

    Returns the same shape as the SAP catalog: stream id + label +
    list of tables. Frontend uses this to render the stream picker
    and per-stream table list, mirroring the SAP multi-table flow.
    """
    streams: List[Dict[str, Any]] = []
    for sid in list_supported_streams():
        tables_meta = STREAM_SCHEMAS.get(("netsuite", sid), [])
        streams.append({
            "id": sid,
            "label": _STREAM_LABELS.get(sid, sid.title()),
            "tables": [
                {
                    "id": t["id"],
                    "label": t["label"],
                    "role": t.get("role"),
                    "required": t.get("required", False),
                    "description": t.get("description", ""),
                    "expected_columns": t.get("expected_columns", []),
                    "has_query": query_for_table(sid, t["id"]) is not None,
                }
                for t in tables_meta
            ],
        })
    return {"streams": streams}


_STREAM_LABELS = {
    "customer":   "Customer Master",
    "vendor":     "Vendor Master",
    "material":   "Item / Material Master",
    "employee":   "Employee Master",
    "gl_account": "GL Account Master",
}


_CURATED_SUITEQL_TABLES: List[str] = [
    # Customer master
    "customer", "customeraddressbook", "customercategory", "customerstatus",
    "contact", "contactrole",
    # Vendor master
    "vendor", "vendoraddressbook", "vendorcategory",
    # Items / material master
    "item", "inventoryitem", "inventorybalance", "noninventoryitem",
    "serviceitem", "kititem", "assemblyitem", "discountitem",
    "pricing", "pricelevel",
    # Employee master
    "employee",
    # GL / accounting
    "account", "accountingperiod", "accountingbook", "department",
    "classification", "location", "subsidiary",
    # Currency
    "currency", "currencyrate",
    # Transactions (header + lines)
    "transaction", "transactionline", "transactionaccountingline",
    # Project / job
    "job", "project", "projecttask",
    # Misc reference
    "partner", "salesrole", "role",
]


@router.get("/available-tables")
def list_available_netsuite_tables(
    project: Project = Depends(require_active_project),
    probe: bool = False,
) -> Dict[str, Any]:
    """Return SuiteQL-queryable tables for the current credentials.

    NetSuite's REST SuiteQL endpoint does NOT expose ``OA_TABLES`` (that's
    the legacy ODBC catalog), so dynamic discovery via SQL isn't possible
    over this transport. Instead we return a curated list of the master-
    data + GL + transactional record types that SuiteQL universally
    supports. The list is stable, well-documented, and avoids the trap
    of showing record types the user's role can't read.

    Set ``probe=true`` to also send a 1-row probe query to each table
    and filter to the ones the current role can actually read. This
    costs ~40 HTTP calls so it's opt-in.
    """
    creds = _resolve_creds(project)
    tables = sorted(_CURATED_SUITEQL_TABLES)
    if not probe:
        return {"tables": tables, "count": len(tables)}

    from concurrent.futures import ThreadPoolExecutor

    def _probe(t: str):
        try:
            run_suiteql(creds, f"SELECT id FROM {t}", limit=1)
            return (t, None)
        except RuntimeError as exc:
            return (t, str(exc)[:160])

    accessible: List[str] = []
    inaccessible: List[Dict[str, str]] = []
    with ThreadPoolExecutor(max_workers=8) as pool:
        for table_name, err in pool.map(_probe, tables):
            if err is None:
                accessible.append(table_name)
            else:
                inaccessible.append({"table": table_name, "reason": err})
    accessible.sort()
    return {
        "tables": accessible,
        "count": len(accessible),
        "probed": True,
        "inaccessible": inaccessible,
    }


class LoadTablesBody(BaseModel):
    tables: List[str] = Field(min_length=1)   # ordered; first entry = primary dataset
    row_limit: int = Field(default=1000, ge=10, le=10000)


@router.post("/load-tables")
def load_netsuite_tables(
    body: LoadTablesBody,
    sess: SessionData = Depends(get_session),
    project: Project = Depends(require_active_project),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Load arbitrary NetSuite tables by name with generic SELECT *.
    No canned queries or stream definitions needed — works with any token.
    The first table in the list becomes the primary working dataset;
    the rest are stashed as supplementary tables."""
    creds = _resolve_creds(project)

    loaded: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    primary_df: Optional[pd.DataFrame] = None
    tables_payload: Dict[str, Any] = {}

    for i, table_name in enumerate(body.tables):
        is_primary = (i == 0)
        try:
            df, qmeta = run_suiteql(creds, f"SELECT * FROM {table_name}", limit=body.row_limit)
        except RuntimeError as exc:
            if is_primary:
                raise HTTPException(status_code=502, detail=str(exc))
            logger.warning("Skipped table %s: %s", table_name, exc)
            skipped.append({"table": table_name, "reason": str(exc)})
            continue

        role = "primary" if is_primary else "lookup"
        tables_payload[table_name] = {
            "filename": f"{table_name}.netsuite",
            "rows": int(len(df)),
            "columns": int(df.shape[1]),
            "uploaded_at": datetime.utcnow().isoformat(),
            "role": role,
            "label": table_name,
        }
        loaded.append({
            "table": table_name,
            "role": role,
            "rows": int(len(df)),
            "columns": int(df.shape[1]),
            "has_more": bool(qmeta.get("hasMore", False)),
        })
        if is_primary:
            primary_df = df

    sess.df = primary_df
    sess.original_df = primary_df.copy()
    sess.filename = f"NetSuite · {body.tables[0]}"
    sess.column_profiles = {}
    sess.quality_report = None
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    sess.fixes_applied = []
    sess.validation_history = []
    sess.reject_df = pd.DataFrame()
    sess.applied_rules_by_dim = {}
    sess.ai_validation_rules = None
    sess.semantic_glossary = None
    sess.columns_of_interest = []

    primary_label = body.tables[0]
    project.system_id = "netsuite"
    project.system_label = "NetSuite"
    project.stream_id = primary_label
    project.stream_label = primary_label
    project.dataset_filename = sess.filename
    project.dataset_rows = int(len(primary_df))
    project.dataset_columns = int(primary_df.shape[1])
    project.dataset_size_bytes = None
    project.tables_meta = tables_payload
    project.status = "data_loaded"
    db.commit()

    save_working(project.id, primary_df, primary_df.copy())
    for entry in loaded:
        if entry["role"] != "primary":
            t_id = entry["table"]
            try:
                df_aux, _ = run_suiteql(creds, f"SELECT * FROM {t_id}", limit=body.row_limit)
                save_table(project.id, t_id, df_aux)
            except RuntimeError:
                pass

    return {
        "ok": True,
        "loaded": loaded,
        "skipped": skipped,
        "primary_rows": int(len(primary_df)),
        "primary_columns": int(primary_df.shape[1]),
    }


@router.post("/load-stream")
def load_netsuite_stream(
    body: LoadStreamBody,
    sess: SessionData = Depends(get_session),
    project: Project = Depends(require_active_project),
    db: Session = Depends(get_db),
) -> Dict[str, Any]:
    """Fetch every table in a NetSuite stream and land them in the session.

    The PRIMARY table is loaded into ``sess.df`` / ``sess.original_df``
    so the rest of the pipeline (profiling, rule generation, cleansing)
    behaves identically to a file upload. Extension and lookup tables
    are stashed under ``sess.tables_meta[<table_id>]`` for the multi-
    table view, mirroring the SAP multi-table flow.

    Each table's SuiteQL query is pulled from
    ``netsuite_connector._STREAM_QUERIES``; the user doesn't write SQL.
    """
    creds = _resolve_creds(project)

    schemas = STREAM_SCHEMAS.get(("netsuite", body.stream), [])
    if not schemas:
        raise HTTPException(
            status_code=400,
            detail=f"NetSuite doesn't have a stream definition for '{body.stream}'.",
        )

    # Resolve which tables to load — default: all that have a canned query.
    requested = body.tables
    table_meta_by_id = {t["id"]: t for t in schemas}
    target_ids = []
    for t in schemas:
        if requested and t["id"] not in requested:
            continue
        if body.primary_only and t.get("role") != "primary":
            continue
        if query_for_table(body.stream, t["id"]) is None:
            continue
        target_ids.append(t["id"])

    if not target_ids:
        raise HTTPException(
            status_code=400,
            detail="No NetSuite tables to load for this stream.",
        )

    loaded: List[Dict[str, Any]] = []
    skipped: List[Dict[str, Any]] = []
    primary_df: Optional[pd.DataFrame] = None
    tables_payload: Dict[str, Any] = {}

    for table_id in target_ids:
        meta = table_meta_by_id[table_id]
        is_primary = meta.get("role") == "primary"
        query = query_for_table(body.stream, table_id)
        try:
            df, qmeta = run_suiteql(creds, query, limit=body.row_limit)
        except RuntimeError as exc:
            if is_primary:
                # Primary table must succeed — the pipeline has nothing to work with otherwise.
                raise HTTPException(status_code=502, detail=str(exc))
            # Lookup / extension table — skip gracefully so the primary still loads.
            logger.warning("Skipped non-primary table %s (%s): %s", table_id, body.stream, exc)
            skipped.append({
                "table": table_id,
                "label": meta.get("label", table_id),
                "reason": str(exc),
            })
            continue

        tables_payload[table_id] = {
            "filename": f"{table_id}.netsuite",
            "rows": int(len(df)),
            "columns": int(df.shape[1]),
            "uploaded_at": datetime.utcnow().isoformat(),
            "role": meta.get("role"),
            "label": meta.get("label"),
        }
        loaded.append({
            "table": table_id,
            "label": meta.get("label"),
            "role": meta.get("role"),
            "rows": int(len(df)),
            "columns": int(df.shape[1]),
            "has_more": bool(qmeta.get("hasMore", False)),
        })
        if is_primary:
            primary_df = df

    if primary_df is None:
        # No primary in this batch — pick the first table as the working df
        # so downstream profiling at least has something to look at.
        first_id = target_ids[0]
        primary_df = run_suiteql(creds, query_for_table(body.stream, first_id),
                                 limit=body.row_limit)[0]

    # Land the primary into the session — identical handling to file upload
    # so every downstream tab (profiling, cleansing, dashboard) just works.
    sess.df = primary_df
    sess.original_df = primary_df.copy()
    sess.filename = f"NetSuite · {_STREAM_LABELS.get(body.stream, body.stream)}"
    sess.column_profiles = {}
    sess.quality_report = None
    sess.exact_duplicates = []
    sess.fuzzy_duplicates = []
    sess.combined_duplicates = []
    sess.fixes_applied = []
    sess.validation_history = []
    sess.reject_df = pd.DataFrame()
    sess.applied_rules_by_dim = {}
    sess.ai_validation_rules = None
    sess.semantic_glossary = None
    sess.columns_of_interest = []

    # Update the project record so the Home tile reflects the load.
    project.system_id = "netsuite"
    project.system_label = "NetSuite"
    project.stream_id = body.stream
    project.stream_label = _STREAM_LABELS.get(body.stream, body.stream)
    project.dataset_filename = sess.filename
    project.dataset_rows = int(len(primary_df))
    project.dataset_columns = int(primary_df.shape[1])
    project.dataset_size_bytes = None
    project.tables_meta = tables_payload
    project.status = "data_loaded"
    db.commit()

    save_working(project.id, primary_df, primary_df.copy())
    for table_id in target_ids:
        meta = table_meta_by_id[table_id]
        if meta.get("role") == "primary":
            continue
        q = query_for_table(body.stream, table_id)
        if q is None:
            continue
        try:
            df_aux, _ = run_suiteql(creds, q, limit=body.row_limit)
            save_table(project.id, table_id, df_aux)
        except RuntimeError:
            pass

    return {
        "ok": True,
        "stream": body.stream,
        "loaded": loaded,
        "skipped": skipped,
        "primary_rows": int(len(primary_df)),
        "primary_columns": int(primary_df.shape[1]),
    }
