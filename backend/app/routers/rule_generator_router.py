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
from typing import Any, Dict, List, Optional

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

from pydantic import BaseModel

from sqlalchemy.orm import Session

from ..db import get_db
from ..deps import require_dataframe, scoped_dataframe
from ..models import Project
from ..services.azure_openai_config import AzureOpenAIConfig
from ..services.dq_rg_mapping import rg_row_to_applied_rule
from ..services.dq_engine import default_config as _dq_default_config
from ..services.project_storage import save_dq_config, save_rules
from ..services.cross_field_engine import _run_llm_expression
from ..services.rule_generator import (
    evaluate_cross_field_rules_in_df,
    generate_complete,
    validate_all_rules,
)
from ..session_store import SessionData

_VALID_DIMENSIONS = {
    "Accuracy", "Completeness", "Consistency", "Validity",
    "Uniqueness", "Timeliness", "Cross-field Validation",
}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rule-generator", tags=["rule-generator"])


def _safe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def _sync_rules_into_dq_config(sess: SessionData, df_rules: pd.DataFrame) -> None:
    """Bridge: every single-column row in ``df_rules`` that translates to
    a Cleansing operation gets appended into ``sess.dq_config[col]
    .applied_rules`` (deduped by rule name).

    This is what makes "Add Custom Rule" feel like it actually does
    something — the moment a rule is created in Rule Generator it shows
    up on the Cleansing tab under that column, ready to be applied
    against the data. Cross-field rules are left alone — they don't fit
    the per-column ``dq_config`` shape and are applied through the
    Cross-field panel's Drop / Deduplicate buttons instead.
    """
    if df_rules is None or df_rules.empty or sess.df is None:
        return

    cols_in_df = {str(c) for c in sess.df.columns}
    for _, row in df_rules.iterrows():
        dim = str(row.get("Dimension", "")).strip()
        if dim == "Cross-field Validation":
            continue
        column = str(row.get("Column", "")).strip()
        if not column or column not in cols_in_df:
            continue
        applied = rg_row_to_applied_rule(row)
        if applied is None:
            continue
        cfg = sess.dq_config.get(column)
        if cfg is None:
            cfg = _dq_default_config()
            sess.dq_config[column] = cfg
        # Dedupe — don't re-add the same rule on every Generate / Add.
        existing_names = {r.get("name") for r in cfg.get("applied_rules", [])}
        if applied.get("name") in existing_names:
            continue
        cfg.setdefault("applied_rules", []).append(applied)

    if sess.active_project_id:
        save_dq_config(sess.active_project_id, sess.dq_config)


@router.get("/llm-status")
def llm_status() -> dict:
    missing = AzureOpenAIConfig.validate()
    return {"configured": not missing, "missing": missing}


@router.post("/generate")
def generate(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """Run the comprehensive engine: deep scan Excel + AI per column + validation + regex enrichment.

    Mirrors the Streamlit button "Generate AI Validation Rules" exactly.
    """
    missing = AzureOpenAIConfig.validate()
    if missing:
        raise HTTPException(status_code=503, detail=f"Azure OpenAI not configured. Missing: {', '.join(missing)}")

    file_path = sess.file_path
    sheet_name = sess.sheet_name
    header_row = 0  # Streamlit uses state.header_row; we hardcode 0 since loader uses it for read

    # Restrict analysis to the columns the user flagged on the Load Data page.
    # When no explicit selection has been saved, `scoped_dataframe` returns the
    # full DataFrame, so existing flows are unchanged.
    df_in_scope = scoped_dataframe(sess)
    if df_in_scope is None or df_in_scope.shape[1] == 0:
        raise HTTPException(
            status_code=400,
            detail="No columns are in scope. Select at least one column under 'Columns of interest' on Load Data.",
        )

    progress_log: List[Dict[str, Any]] = []
    def cb(payload: Dict[str, Any]) -> None:
        progress_log.append(payload)

    try:
        df_rules = generate_complete(
            file_path, sheet_name, header_row, df_in_scope,
            progress_cb=cb,
            semantic_glossary=sess.semantic_glossary,
        )
    except Exception as exc:
        logger.error("Rule generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rule generation failed: {exc}")

    sess.ai_validation_rules = df_rules

    # Bridge to Cleansing — every column rule in the freshly generated
    # set becomes an applied_rule under that column's dq_config, ready
    # to be applied with one click on the Cleansing tab.
    _sync_rules_into_dq_config(sess, df_rules)

    # Reflect generation in the project so Home tiles show "Rules ready",
    # and persist the rules DataFrame to disk so it survives a server
    # restart or a project re-open.
    if sess.active_project_id:
        save_rules(sess.active_project_id, df_rules)
        project = (
            db.query(Project).filter(Project.id == sess.active_project_id).one_or_none()
        )
        if project is not None:
            project.rules_total = int(len(df_rules))
            if "Issues Found" in df_rules.columns:
                try:
                    project.issues_total = int(
                        df_rules["Issues Found"].fillna(0).astype(int).sum()
                    )
                except Exception:
                    pass
            if project.status not in ("cleansed", "exported"):
                project.status = "rules_generated"
            db.commit()

    return {
        "ok": True,
        "total_rules": len(df_rules),
        "columns_covered": int(df_rules["Column"].nunique()) if "Column" in df_rules.columns else 0,
        "columns_in_scope": int(df_in_scope.shape[1]),
        "columns_total": int(sess.df.shape[1]) if sess.df is not None else 0,
        "dq_dimensions": int(df_rules["Dimension"].nunique()) if "Dimension" in df_rules.columns else 0,
        "glossary_used": bool(sess.semantic_glossary),
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
    if sess.active_project_id:
        save_rules(sess.active_project_id, None)
    return {"ok": True}


@router.post("/regenerate")
def regenerate(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Streamlit's 'Regenerate Rules' button just clears state — UI calls /generate after."""
    sess.ai_validation_rules = None
    if sess.active_project_id:
        save_rules(sess.active_project_id, None)
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


# ─── Custom rules (user-authored) ────────────────────────────────────


class CustomRuleBody(BaseModel):
    column: Optional[str] = None
    columns: Optional[List[str]] = None
    dimension: str
    data_quality_rule: str
    regex_pattern: Optional[str] = ""
    validation_expression: Optional[str] = ""


def _renumber(df: pd.DataFrame) -> pd.DataFrame:
    df = df.reset_index(drop=True)
    df["S.No"] = range(1, len(df) + 1)
    return df


@router.post("/rules/custom")
def add_custom_rule(
    body: CustomRuleBody,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Append a user-authored rule to the current rule set and validate it.

    The new row carries ``Rule Source: Custom`` so the UI can label it,
    the Data Quality apply flow can pick it up, and exports include it.
    """
    dimension = (body.dimension or "").strip()
    rule_text = (body.data_quality_rule or "").strip()
    if dimension not in _VALID_DIMENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid dimension. Use one of: {', '.join(sorted(_VALID_DIMENSIONS))}",
        )
    if not rule_text:
        raise HTTPException(status_code=400, detail="Data Quality Rule text is required")

    df_data = sess.df
    all_columns = {str(c) for c in df_data.columns}

    is_cross_field = dimension == "Cross-field Validation"
    if is_cross_field:
        cols = list(body.columns or [])
        if not cols and body.column:
            # Allow "a + b + c" or "a, b, c" syntax in the single field
            parts = [p.strip() for p in body.column.replace(",", "+").split("+") if p.strip()]
            cols = parts
        if len(cols) < 2:
            raise HTTPException(
                status_code=400,
                detail="Cross-field rules must reference at least 2 columns",
            )
        unknown = [c for c in cols if c not in all_columns]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown columns: {', '.join(unknown)}",
            )
        column_label = " + ".join(cols)
    else:
        col = (body.column or "").strip()
        if not col:
            raise HTTPException(status_code=400, detail="Column is required for non-cross-field rules")
        if col not in all_columns:
            raise HTTPException(status_code=400, detail=f"Unknown column: {col}")
        column_label = col

    new_row = {
        "S.No": 0,  # filled by _renumber below
        "Column": column_label,
        "Business Field": column_label,
        "Rule Source": "Custom",
        "Dimension": dimension,
        "Data Quality Rule": rule_text,
        "Regex Pattern": (body.regex_pattern or "").strip(),
        "Issues Found": 0,
        "Issues Found Example": "Pending validation",
        "Validation Expression": (body.validation_expression or "").strip(),
    }

    existing = sess.ai_validation_rules
    if existing is None or (isinstance(existing, pd.DataFrame) and existing.empty):
        df_rules = pd.DataFrame([new_row])
    else:
        df_rules = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)

    # Evaluate the newly appended rule. For non-cross-field, validate_all_rules
    # re-runs every row (cheap); for cross-field with a user-supplied
    # validation_expression we evaluate it directly through the AST sandbox.
    if is_cross_field and new_row["Validation Expression"]:
        result = _run_llm_expression(
            {"code": new_row["Validation Expression"], "description": rule_text},
            df_data,
            cols,
        )
        last_idx = df_rules.index[-1]
        if result is None:
            df_rules.at[last_idx, "Issues Found"] = 0
            df_rules.at[last_idx, "Issues Found Example"] = (
                "Cross-field — could not evaluate user-supplied expression"
            )
        else:
            df_rules.at[last_idx, "Issues Found"] = int(result.count)
            df_rules.at[last_idx, "Issues Found Example"] = result.example
    else:
        if is_cross_field:
            df_rules = evaluate_cross_field_rules_in_df(df_rules, df_data)
        else:
            df_rules = validate_all_rules(df_data, df_rules)

    df_rules = enrich_dataframe_regex_patterns(df_rules)
    df_rules = _renumber(df_rules)
    sess.ai_validation_rules = df_rules
    # Mirror the just-added custom rule into Cleansing so the user can
    # click into the Cleansing tab and immediately apply it.
    _sync_rules_into_dq_config(sess, df_rules.tail(1))
    if sess.active_project_id:
        save_rules(sess.active_project_id, df_rules)

    return {
        "ok": True,
        "total_rules": len(df_rules),
        "rule": df_rules.iloc[-1].where(pd.notnull(df_rules.iloc[-1]), None).to_dict(),
        "rules": _safe_records(df_rules),
    }


@router.delete("/rules/{rule_idx}")
def delete_rule(
    rule_idx: int,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Remove a rule by zero-based index (mapped to the current rule list)."""
    df = sess.ai_validation_rules
    if df is None or df.empty:
        raise HTTPException(status_code=404, detail="No rules to delete")
    if rule_idx < 0 or rule_idx >= len(df):
        raise HTTPException(status_code=404, detail="Rule index out of range")
    df = df.drop(df.index[rule_idx]).reset_index(drop=True)
    df = _renumber(df)
    sess.ai_validation_rules = df
    if sess.active_project_id:
        save_rules(sess.active_project_id, df)
    return {"ok": True, "total_rules": len(df), "rules": _safe_records(df)}
