"""Per-project on-disk storage for working DataFrames + analysis artifacts.

Each project owns a directory under ``backend/storage/projects/<id>/`` that
holds:

  working.parquet     the live DataFrame the user is editing
  original.parquet    the pristine upload, used by /data/reset
  rules.parquet       generated DQ rules (sess.ai_validation_rules)
  glossary.json       semantic glossary entries (sess.semantic_glossary)
  scope.json          columns_of_interest selection

We snapshot to disk after every mutation so a server restart doesn't lose
a user's work. The session-level state is the in-memory working copy; this
module makes sure it survives.
"""
from __future__ import annotations

import json
import logging
import shutil
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

logger = logging.getLogger(__name__)

_STORAGE_ROOT = Path(__file__).resolve().parents[3] / "backend" / "storage" / "projects"
_STORAGE_ROOT.mkdir(parents=True, exist_ok=True)


def project_dir(project_id: str) -> Path:
    d = _STORAGE_ROOT / project_id
    d.mkdir(parents=True, exist_ok=True)
    return d


def working_path(project_id: str) -> Path:
    return project_dir(project_id) / "working.parquet"


def original_path(project_id: str) -> Path:
    return project_dir(project_id) / "original.parquet"


def save_working(
    project_id: str,
    df: pd.DataFrame,
    original_df: Optional[pd.DataFrame] = None,
) -> None:
    """Snapshot the working DataFrame; optionally also store the original.

    Errors are logged but not re-raised so a transient disk failure can't
    crash the user's in-flight request — they keep their in-memory copy.
    """
    try:
        if df is not None:
            df.to_parquet(working_path(project_id), index=False)
        if original_df is not None and not original_path(project_id).exists():
            original_df.to_parquet(original_path(project_id), index=False)
    except Exception as exc:
        logger.error("save_working(%s) failed: %s", project_id, exc)


def load_working(project_id: str) -> Tuple[Optional[pd.DataFrame], Optional[pd.DataFrame]]:
    """Return ``(working_df, original_df)`` for the project, or ``(None, None)``."""
    wp = working_path(project_id)
    op = original_path(project_id)
    try:
        working = pd.read_parquet(wp) if wp.exists() else None
        original = pd.read_parquet(op) if op.exists() else None
        return working, original
    except Exception as exc:
        logger.error("load_working(%s) failed: %s", project_id, exc)
        return None, None


def has_working(project_id: str) -> bool:
    return working_path(project_id).exists()


def clear_working(project_id: str) -> None:
    """Delete the working DataFrame but keep the original.

    Mirrors ``POST /data/clear`` — the user wants to drop their edits and
    start over from the upload (or from nothing).
    """
    wp = working_path(project_id)
    if wp.exists():
        try:
            wp.unlink()
        except Exception as exc:
            logger.error("clear_working(%s) failed: %s", project_id, exc)


def rules_path(project_id: str) -> Path:
    return project_dir(project_id) / "rules.parquet"


def glossary_path(project_id: str) -> Path:
    return project_dir(project_id) / "glossary.json"


def scope_path(project_id: str) -> Path:
    return project_dir(project_id) / "scope.json"


def cde_meta_path(project_id: str) -> Path:
    return project_dir(project_id) / "cde_meta.json"


def save_rules(project_id: str, df_rules: Optional[pd.DataFrame]) -> None:
    """Persist the rules DataFrame. ``None`` deletes any existing file."""
    p = rules_path(project_id)
    try:
        if df_rules is None or df_rules.empty:
            if p.exists():
                p.unlink()
            return
        df_rules.to_parquet(p, index=False)
    except Exception as exc:
        logger.error("save_rules(%s) failed: %s", project_id, exc)


def load_rules(project_id: str) -> Optional[pd.DataFrame]:
    p = rules_path(project_id)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as exc:
        logger.error("load_rules(%s) failed: %s", project_id, exc)
        return None


def save_glossary(project_id: str, glossary: Optional[Dict[str, Dict[str, Any]]]) -> None:
    p = glossary_path(project_id)
    try:
        if not glossary:
            if p.exists():
                p.unlink()
            return
        p.write_text(json.dumps(glossary, ensure_ascii=False, indent=2), encoding="utf-8")
    except Exception as exc:
        logger.error("save_glossary(%s) failed: %s", project_id, exc)


def load_glossary(project_id: str) -> Optional[Dict[str, Dict[str, Any]]]:
    p = glossary_path(project_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("load_glossary(%s) failed: %s", project_id, exc)
        return None


def save_scope(project_id: str, columns: List[str]) -> None:
    p = scope_path(project_id)
    try:
        if not columns:
            if p.exists():
                p.unlink()
            return
        p.write_text(json.dumps(list(columns), ensure_ascii=False), encoding="utf-8")
    except Exception as exc:
        logger.error("save_scope(%s) failed: %s", project_id, exc)


def load_scope(project_id: str) -> List[str]:
    p = scope_path(project_id)
    if not p.exists():
        return []
    try:
        v = json.loads(p.read_text(encoding="utf-8"))
        return list(v) if isinstance(v, list) else []
    except Exception as exc:
        logger.error("load_scope(%s) failed: %s", project_id, exc)
        return []


def save_cde_meta(
    project_id: str,
    fingerprint: str,
    meta: Optional[Dict[str, Dict[str, Any]]],
) -> None:
    """Persist the AI-generated per-column CDE descriptions + recommendations.

    The on-disk shape is ``{"fingerprint": "...", "meta": {col: {...}}}`` so
    a reload can detect when the column set has drifted from what the meta
    was generated for, and discard the stale entry.
    """
    p = cde_meta_path(project_id)
    try:
        if not meta:
            if p.exists():
                p.unlink()
            return
        p.write_text(
            json.dumps({"fingerprint": fingerprint, "meta": meta}, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error("save_cde_meta(%s) failed: %s", project_id, exc)


def load_cde_meta(
    project_id: str,
    expected_fingerprint: str,
) -> Optional[Dict[str, Dict[str, Any]]]:
    """Return cached CDE meta IFF the cache is current AND schema-complete.

    Three reasons we return None:
      1. File missing.
      2. Fingerprint mismatch — columns differ from what was classified.
      3. Schema-stale — cached entries pre-date the ``semantic_type`` field
         (i.e. generated under the older prompt that only emitted
         description + recommended). Without semantic_type the Validation
         and Uniqueness scorers can't detect identifiers, so the cache is
         effectively unusable for downstream features. Treating as miss
         triggers a one-time regeneration that lights up every dimension.
    """
    p = cde_meta_path(project_id)
    if not p.exists():
        return None
    try:
        payload = json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("load_cde_meta(%s) failed: %s", project_id, exc)
        return None
    if not isinstance(payload, dict):
        return None
    if payload.get("fingerprint") != expected_fingerprint:
        return None
    meta = payload.get("meta")
    if not isinstance(meta, dict) or not meta:
        return None
    # Schema-stale check: any entry must carry the semantic_type key.
    # Even a value of 'other' counts — it means the column WAS classified
    # under the new schema. What we're rejecting is caches where the field
    # simply doesn't exist on any entry.
    if not any("semantic_type" in (v or {}) for v in meta.values()):
        logger.info(
            "load_cde_meta(%s): cache exists but lacks semantic_type — treating as miss so a fresh classification runs.",
            project_id,
        )
        return None
    return meta


def dq_config_path(project_id: str) -> Path:
    return project_dir(project_id) / "dq_config.json"


def rejected_path(project_id: str) -> Path:
    return project_dir(project_id) / "rejected.parquet"


def save_dq_config(project_id: str, dq_config: Optional[Dict[str, Any]]) -> None:
    p = dq_config_path(project_id)
    try:
        if not dq_config:
            if p.exists():
                p.unlink()
            return
        # dq_config can contain timestamps and other non-trivial types
        # written by the per-column editor — coerce anything non-JSON-able
        # to str via ``default=str``.
        p.write_text(
            json.dumps(dq_config, ensure_ascii=False, default=str, indent=2),
            encoding="utf-8",
        )
    except Exception as exc:
        logger.error("save_dq_config(%s) failed: %s", project_id, exc)


def load_dq_config(project_id: str) -> Optional[Dict[str, Any]]:
    p = dq_config_path(project_id)
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("load_dq_config(%s) failed: %s", project_id, exc)
        return None


def save_rejected(project_id: str, df: Optional[pd.DataFrame]) -> None:
    p = rejected_path(project_id)
    try:
        if df is None or df.empty:
            if p.exists():
                p.unlink()
            return
        df.to_parquet(p, index=False)
    except Exception as exc:
        logger.error("save_rejected(%s) failed: %s", project_id, exc)


def load_rejected(project_id: str) -> Optional[pd.DataFrame]:
    p = rejected_path(project_id)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as exc:
        logger.error("load_rejected(%s) failed: %s", project_id, exc)
        return None


def tables_dir(project_id: str) -> Path:
    """Subdir holding per-table parquet files for streams that use a
    multi-table schema (e.g. SAP Vendor → LFA1, LFB1, LFM1, ...).

    For single-file streams (file_upload) this directory stays empty;
    everything lives in ``working.parquet`` at the project root.
    """
    d = project_dir(project_id) / "tables"
    d.mkdir(parents=True, exist_ok=True)
    return d


def table_path(project_id: str, table_id: str) -> Path:
    return tables_dir(project_id) / f"{table_id}.parquet"


def save_table(
    project_id: str,
    table_id: str,
    df: pd.DataFrame,
    original_filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Persist one stream table as parquet + return its metadata.

    The metadata dict is what the project row's ``tables_meta`` field
    stores — a per-table summary the UI can render without re-reading
    the parquet (rows, columns, filename, when_uploaded).
    """
    p = table_path(project_id, table_id)
    df.to_parquet(p, index=False)
    return {
        "table_id": table_id,
        "filename": original_filename or f"{table_id}.parquet",
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "size_bytes": int(p.stat().st_size),
    }


def load_table(project_id: str, table_id: str) -> Optional[pd.DataFrame]:
    p = table_path(project_id, table_id)
    if not p.exists():
        return None
    try:
        return pd.read_parquet(p)
    except Exception as exc:
        logger.error("load_table(%s,%s) failed: %s", project_id, table_id, exc)
        return None


def delete_table(project_id: str, table_id: str) -> None:
    p = table_path(project_id, table_id)
    if p.exists():
        try:
            p.unlink()
        except Exception as exc:
            logger.error("delete_table(%s,%s) failed: %s", project_id, table_id, exc)


def list_uploaded_tables(project_id: str) -> List[str]:
    d = tables_dir(project_id)
    return sorted([p.stem for p in d.glob("*.parquet")])


def delete_project_storage(project_id: str) -> None:
    """Wipe the entire project directory. Called from ``DELETE /projects/{id}``."""
    d = _STORAGE_ROOT / project_id
    if d.exists():
        try:
            shutil.rmtree(d, ignore_errors=True)
        except Exception as exc:
            logger.error("delete_project_storage(%s) failed: %s", project_id, exc)
