"""Rule Generator endpoints — 1:1 parity with features/rule_generator/ui.py.

Endpoints:
  POST /rule-generator/generate         run comprehensive rule generation pipeline
  GET  /rule-generator/rules            current rules dataframe (or empty)
  POST /rule-generator/regenerate       clear rules + flag (UI-side trigger; same as clear)
  POST /rule-generator/clear            clear current rules
  POST /rule-generator/export/excel     download Excel of rules
  POST /rule-generator/export/pdf       download PDF report (xhtml2pdf)
"""
from __future__ import annotations

import io
import logging
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse

# Import engine + report directly via spec_from_file_location to avoid the
# features/rule_generator/__init__.py which imports the Streamlit UI module.
import importlib.util as _imp
import sys as _sys
from pathlib import Path as _Path

_root = _Path(__file__).resolve().parents[3]
def _load(name: str, rel: str):
    spec = _imp.spec_from_file_location(name, str(_root / rel))
    mod = _imp.module_from_spec(spec)
    _sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod

_engine = _load("_rg_engine", "features/rule_generator/engine.py")
enrich_dataframe_regex_patterns = _engine.enrich_dataframe_regex_patterns
# The original report.py has a name-shadowing bug (`import html` shadowed by
# local `html = f"..."`); we use a patched copy that produces identical output.
from ..services.rg_report_patched import export_dq_report_to_pdf  # noqa: E402

from ..deps import require_dataframe
from ..services.azure_openai_config import AzureOpenAIConfig
from ..services.rule_generator import generate_complete
from ..session_store import SessionData

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rule-generator", tags=["rule-generator"])


def _safe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


@router.get("/llm-status")
def llm_status() -> dict:
    missing = AzureOpenAIConfig.validate()
    return {"configured": not missing, "missing": missing}


@router.post("/generate")
def generate(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Run the comprehensive engine: deep scan Excel + AI per column + validation + regex enrichment.

    Mirrors the Streamlit button "Generate AI Validation Rules" exactly.
    """
    missing = AzureOpenAIConfig.validate()
    if missing:
        raise HTTPException(status_code=503, detail=f"Azure OpenAI not configured. Missing: {', '.join(missing)}")

    file_path = sess.file_path
    sheet_name = sess.sheet_name
    header_row = 0  # Streamlit uses state.header_row; we hardcode 0 since loader uses it for read

    progress_log: List[Dict[str, Any]] = []
    def cb(payload: Dict[str, Any]) -> None:
        progress_log.append(payload)

    try:
        df_rules = generate_complete(file_path, sheet_name, header_row, sess.df, progress_cb=cb)
    except Exception as exc:
        logger.error("Rule generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rule generation failed: {exc}")

    sess.ai_validation_rules = df_rules

    return {
        "ok": True,
        "total_rules": len(df_rules),
        "columns_covered": int(df_rules["Column"].nunique()) if "Column" in df_rules.columns else 0,
        "dq_dimensions": int(df_rules["Dimension"].nunique()) if "Dimension" in df_rules.columns else 0,
        "rules": _safe_records(df_rules),
        "progress": progress_log,
    }


@router.get("/rules")
def get_rules(sess: SessionData = Depends(require_dataframe)) -> dict:
    df = sess.ai_validation_rules
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return {"generated": False, "rules": []}
    if isinstance(df, pd.DataFrame) and "Regex Pattern" not in df.columns:
        df = df.copy()
        df["Regex Pattern"] = ""
    df = enrich_dataframe_regex_patterns(df) if isinstance(df, pd.DataFrame) else df
    return {
        "generated": True,
        "total_rules": len(df),
        "columns_covered": int(df["Column"].nunique()) if "Column" in df.columns else 0,
        "dq_dimensions": int(df["Dimension"].nunique()) if "Dimension" in df.columns else 0,
        "rules": _safe_records(df),
    }


@router.post("/clear")
def clear(sess: SessionData = Depends(require_dataframe)) -> dict:
    sess.ai_validation_rules = None
    return {"ok": True}


@router.post("/regenerate")
def regenerate(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Streamlit's 'Regenerate Rules' button just clears state — UI calls /generate after."""
    sess.ai_validation_rules = None
    return {"ok": True}


@router.post("/export/excel")
def export_excel(sess: SessionData = Depends(require_dataframe)):
    df = sess.ai_validation_rules
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="No rules generated yet")
    if "Regex Pattern" not in df.columns:
        df = df.copy()
        df["Regex Pattern"] = ""
    df = enrich_dataframe_regex_patterns(df)
    buffer = io.BytesIO()
    with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="Data Quality Rule")
    buffer.seek(0)
    fname = f"data_quality_rules_{sess.filename}.xlsx"
    return StreamingResponse(
        buffer,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/export/pdf")
def export_pdf(sess: SessionData = Depends(require_dataframe)):
    df = sess.ai_validation_rules
    if df is None or df.empty:
        raise HTTPException(status_code=400, detail="No rules generated yet")
    if "Regex Pattern" not in df.columns:
        df = df.copy()
        df["Regex Pattern"] = ""
    df = enrich_dataframe_regex_patterns(df)
    pdf_bytes = export_dq_report_to_pdf(df, sess.filename, len(sess.df) if sess.df is not None else 0)
    if not pdf_bytes:
        raise HTTPException(status_code=500, detail="PDF generation failed (xhtml2pdf may be missing)")
    fname = f"dq_report_{sess.filename}.pdf"
    return StreamingResponse(
        io.BytesIO(pdf_bytes),
        media_type="application/pdf",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
