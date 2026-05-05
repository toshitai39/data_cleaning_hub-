"""Wrappers around core/db_connector.py for the Load Data tab.

Imports SUPPORTED_ENGINES + helper functions directly from the original module
(which is Streamlit-free) so the parity is byte-perfect.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.db_connector import (  # type: ignore
    SUPPORTED_ENGINES,
    _driver_available,
    build_url as _build_url,
    list_tables as _list_tables,
    load_table as _load_table,
    run_query as _run_query,
    test_connection as _test_connection,
)


def list_supported_engines() -> List[Dict[str, Any]]:
    """Return engine catalogue with driver status, exactly as the Streamlit
    selectbox enumerates."""
    out: List[Dict[str, Any]] = []
    for label, meta in SUPPORTED_ENGINES.items():
        ok, hint = _driver_available(label)
        out.append({
            "label": label,
            "default_port": meta.get("default_port"),
            "driver_installed": ok,
            "install_hint": hint or meta.get("hint", ""),
            "is_file_based": label in ("SQLite", "DuckDB"),
            "is_cloud": label in ("BigQuery",),
            "is_snowflake": label == "Snowflake",
        })
    return out


def build_url(engine_label: str, **params: Any) -> str:
    return _build_url(engine_label, **params)


def connect_and_list(url: str) -> Tuple[bool, List[str]]:
    """Test connection then list tables."""
    if not _test_connection(url):
        return False, []
    return True, _list_tables(url)


def load_from_database(url: str, table: Optional[str], custom_query: Optional[str]) -> pd.DataFrame:
    if custom_query and custom_query.strip():
        return _run_query(url, custom_query.strip())
    if not table:
        raise ValueError("Either table or custom_query must be provided")
    return _load_table(url, table)
