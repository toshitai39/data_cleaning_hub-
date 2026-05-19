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
import re
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
from ..services.cross_field_engine import _run_llm_expression, evaluate_cross_field_rule
from ..services.stream_context import build_project_context
from ..services.rule_generator import (
    evaluate_cross_field_rules_in_df,
    generate_complete,
    validate_all_rules,
)
from ..session_store import SessionData

_VALID_DIMENSIONS = {
    "Accuracy", "Completeness", "Standardisation", "Validation",
    "Uniqueness", "Timeliness", "Cross-field Validation",
    # Pre-rename aliases — accept rules persisted before the 2026-05
    # Consistency→Standardisation / Validity→Validation rename.
    "Consistency", "Validity",
}

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rule-generator", tags=["rule-generator"])


def _atomic_cdes_covered(df: pd.DataFrame) -> int:
    """Count atomic CDEs covered by the rules, not composite labels.

    A multi-CDE custom rule stores ``Column`` as a composite string like
    ``"name AND pan"`` or ``"col_a + col_b"``. Counting nunique() on
    Column directly inflates the figure — every composite label counts
    as a new CDE. We split on the known operators and dedupe.
    """
    if df is None or df.empty or "Column" not in df.columns:
        return 0
    atomic: set[str] = set()
    for raw in df["Column"].dropna().astype(str).tolist():
        # The "Columns" metadata column (comma-joined atomic names) is
        # the authoritative source when present — fall back to parsing
        # the label only when Columns is empty / missing.
        used = False
        if "Columns" in df.columns:
            # We can't index by Column value alone, so just parse label.
            pass
        text = raw
        for sep in (" AND ", " OR ", " + ", ",", ";"):
            text = text.replace(sep, "|")
        for part in text.split("|"):
            cleaned = part.strip()
            if cleaned:
                atomic.add(cleaned)
        if used:
            pass
    return len(atomic)


def _safe_records(df: pd.DataFrame) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    df = df.where(pd.notnull(df), None)
    return df.to_dict(orient="records")


def _purge_ai_synced_from_dq_config(sess: SessionData) -> None:
    """Drop every applied_rule in dq_config whose source is "ai".

    These were auto-synced by an earlier generate call. We DO NOT delete
    the dq_config entries themselves (config flags like ``enabled`` are
    preserved) — only the rules array is filtered. Truly custom rules
    (source != "ai", e.g. user-authored via Add Custom Rule, or loaded
    from the library) are kept untouched.
    """
    if not sess.dq_config:
        return
    for col, cfg in sess.dq_config.items():
        rules = cfg.get("applied_rules", []) or []
        kept = [r for r in rules if r.get("source", "ai") != "ai"]
        if len(kept) != len(rules):
            cfg["applied_rules"] = kept
    if sess.active_project_id:
        save_dq_config(sess.active_project_id, sess.dq_config)


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
            detail="No columns are in scope. Select at least one Critical Data Element on Load Data.",
        )

    progress_log: List[Dict[str, Any]] = []
    def cb(payload: Dict[str, Any]) -> None:
        progress_log.append(payload)

    # Resolve master-data context so the LLM prompts adapt to the stream
    # type (entity master vs joined view). Works for any source system —
    # SAP, Oracle, Workday, Snowflake, or file upload — keyed on stream_id.
    active_project = None
    if sess.active_project_id and sess.user and sess.user.get("username"):
        active_project = (
            db.query(Project)
            .filter(
                Project.id == sess.active_project_id,
                Project.user_username == sess.user["username"],
            )
            .one_or_none()
        )
    project_context = build_project_context(active_project)

    try:
        df_rules = generate_complete(
            file_path, sheet_name, header_row, df_in_scope,
            progress_cb=cb,
            semantic_glossary=sess.semantic_glossary,
            project_context=project_context,
        )
    except Exception as exc:
        logger.error("Rule generation failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"Rule generation failed: {exc}")

    sess.ai_validation_rules = df_rules

    # Purge AI rules carried over from a previous generation, but
    # preserve user-authored ones. Without this, regenerating after
    # editing rules accumulates duplicates in dq_config.
    _purge_ai_synced_from_dq_config(sess)

    # NOTE: We DELIBERATELY no longer auto-sync AI rules into dq_config.
    # The Cleansing tab reads AI rules directly via get_enriched_rg_rules
    # and lazily imports them per-dimension on first Preview / Apply.
    # Auto-syncing here caused the same rule to appear twice (once as AI,
    # once as Custom) and accumulated across regenerations.

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
        "columns_covered": _atomic_cdes_covered(df_rules),
        "columns_in_scope": int(df_in_scope.shape[1]),
        "columns_total": int(sess.df.shape[1]) if sess.df is not None else 0,
        "dq_dimensions": int(df_rules["Dimension"].nunique()) if "Dimension" in df_rules.columns else 0,
        "glossary_used": bool(sess.semantic_glossary),
        "rules": _safe_records(df_rules),
        "progress": progress_log,
    }


def _drop_unverifiable_accuracy_rows(df: pd.DataFrame) -> pd.DataFrame:
    """Strip per-column Accuracy rules with no mechanical check.

    Call this on the RAW dataframe BEFORE enrich_dataframe_regex_patterns
    — enrichment infers regexes from column names, making has_check=True
    for every Accuracy row and preventing the filter from ever firing.
    """
    if "Dimension" not in df.columns:
        return df
    raw_regex = df["Regex Pattern"].astype(str).str.strip() if "Regex Pattern" in df.columns else pd.Series("", index=df.index)
    raw_expr = df["Validation Expression"].astype(str).str.strip() if "Validation Expression" in df.columns else pd.Series("", index=df.index)
    is_accuracy = df["Dimension"].astype(str).str.strip() == "Accuracy"
    has_check = raw_regex.ne("") | raw_expr.ne("")
    drop_mask = is_accuracy & ~has_check
    if not drop_mask.any():
        return df
    return df.loc[~drop_mask].reset_index(drop=True)


def _refresh_cross_field_issue_counts(df: pd.DataFrame, sess: SessionData) -> pd.DataFrame:
    """Re-evaluate every Cross-field Validation row against the current
    ``sess.df`` and overwrite its ``Issues Found`` / ``Issues Found Example``
    columns.

    The counts on disk were frozen at generation time, but executor logic
    can evolve (e.g. composite_unique now excludes all-null tuples). Without
    this refresh the Rule Generator view shows stale numbers while the
    Cleansing view, which re-runs the executor on every fetch, shows the
    correct ones — a real source of confusion for the user.
    """
    if df is None or df.empty or "Dimension" not in df.columns or sess.df is None:
        return df
    cross_mask = df["Dimension"].astype(str).str.strip() == "Cross-field Validation"
    if not cross_mask.any():
        return df
    for idx in df.index[cross_mask]:
        rule_text = str(df.at[idx, "Data Quality Rule"]) if "Data Quality Rule" in df.columns else ""
        if not rule_text:
            continue
        try:
            result = evaluate_cross_field_rule(rule_text, sess.df)
        except Exception as exc:
            logger.warning("refresh cross-field count failed on %r: %s", rule_text[:60], exc)
            continue
        if "Issues Found" in df.columns:
            df.at[idx, "Issues Found"] = int(result.count)
        if "Issues Found Example" in df.columns:
            df.at[idx, "Issues Found Example"] = result.example
    return df


@router.get("/rules")
def get_rules(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Return the AI-generated rules dataframe only.

    The Cleansing tab is the place where AI + user-authored rules are
    blended together. The Rule Generator view is, by design, just the
    AI output. Mixing the two here was the cause of the duplicate-rule
    bug (same rule appearing as AI and Custom) and unstable totals.
    """
    df = sess.ai_validation_rules
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return {"generated": False, "rules": []}
    df = df.copy()
    if "Regex Pattern" not in df.columns:
        df["Regex Pattern"] = ""
    if "Dimension" in df.columns:
        df["Dimension"] = df["Dimension"].astype(str).replace({
            "Consistency": "Standardisation",
            "Validity":    "Validation",
        })
    # Drop unverifiable Accuracy narratives BEFORE enrichment — enrich
    # adds inferred regexes from column names, which would mask the filter.
    df = _drop_unverifiable_accuracy_rows(df)
    df = enrich_dataframe_regex_patterns(df)
    # Refresh cross-field issue counts so this endpoint agrees with the
    # Cleansing tab. Without this the two views diverge whenever executor
    # logic changes (the user's "Why does Data Quality Rules show 6 issues
    # while Cleansing shows 0?" complaint).
    df = _refresh_cross_field_issue_counts(df, sess)

    return {
        "generated": True,
        "total_rules": len(df),
        "columns_covered": _atomic_cdes_covered(df),
        "dq_dimensions": int(df["Dimension"].nunique()) if "Dimension" in df.columns else 0,
        "rules": _safe_records(df),
    }


@router.post("/clear")
def clear(sess: SessionData = Depends(require_dataframe)) -> dict:
    sess.ai_validation_rules = None
    _purge_ai_synced_from_dq_config(sess)
    if sess.active_project_id:
        save_rules(sess.active_project_id, None)
    return {"ok": True}


@router.post("/regenerate")
def regenerate(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Streamlit's 'Regenerate Rules' button just clears state — UI calls /generate after.

    Also wipes AI-sourced rules from dq_config so the next /generate
    doesn't accumulate duplicates. User-authored custom rules stay.
    """
    sess.ai_validation_rules = None
    _purge_ai_synced_from_dq_config(sess)
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
    # AND / OR — meaningful for Validation, Completeness, Uniqueness multi-CDE
    # rules. Ignored elsewhere. Defaults to AND server-side when omitted.
    operator: Optional[str] = None
    dimension: str
    data_quality_rule: str
    regex_pattern: Optional[str] = ""
    validation_expression: Optional[str] = ""


# Per-dimension capability map — mirror of frontend DIM_CAPS.
# - multi: dimension can target N CDEs in a single rule
# - operator: AND/OR is meaningful (vs ignored / not applicable)
_DIM_CAPS = {
    "Validation":             {"multi": True, "operator": True},
    "Completeness":           {"multi": True, "operator": True},
    "Uniqueness":             {"multi": True, "operator": True},
    "Standardisation":        {"multi": True, "operator": True},
    "Accuracy":               {"multi": True, "operator": True},
    "Timeliness":             {"multi": True, "operator": True},
    "Cross-field Validation": {"multi": True, "operator": False},
    # Legacy aliases — accept rules persisted before the rename.
    "Validity":               {"multi": True, "operator": True},
    "Consistency":            {"multi": True, "operator": True},
}


def _evaluate_multi_custom_rule(
    df: pd.DataFrame,
    columns: List[str],
    dimension: str,
    operator: str,
    regex_pattern: str,
) -> tuple[int, str]:
    """Compute (issues_found, example) for a multi-CDE custom rule.

    Semantics are dimension-aware per the steward's choice on the dialog:

      Uniqueness + AND  → composite-key uniqueness (tuple over the CDEs).
                          Issues = rows whose tuple is duplicated.
      Uniqueness + OR   → each CDE independently unique. Issues = rows that
                          fail uniqueness on ANY one of the CDEs.

      Completeness + AND → all CDEs non-null per row. Issues = rows with
                           any null in the selected CDEs.
      Completeness + OR  → at least one non-null per row. Issues = rows
                           where every selected CDE is null.

      Validation + AND  → every CDE matches the regex on every row.
                          Issues = rows where any selected CDE fails.
      Validation + OR   → at least one CDE matches per row. Issues =
                          rows where none of the selected CDEs match.
                          (Validation without a regex is treated as a
                          placeholder; we report 0 issues + a hint so
                          stewards see the rule landed but isn't scored.)
    """
    n_rows = len(df)
    if n_rows == 0 or not columns:
        return 0, "No rows to evaluate"
    op = (operator or "AND").upper()
    if op not in ("AND", "OR"):
        op = "AND"

    # --- Uniqueness ----------------------------------------------------
    if dimension == "Uniqueness":
        if op == "AND":
            sub = df[columns]
            # NaN-aware: rows whose tuple is duplicated.
            dup_mask = sub.duplicated(keep=False)
            bad = int(dup_mask.sum())
            example = "All composite keys unique" if bad == 0 else (
                f"{bad} rows share their ({' + '.join(columns)}) tuple with another row"
            )
            return bad, example
        # OR — fail if ANY CDE independently has a duplicate.
        any_bad = pd.Series(False, index=df.index)
        per_col_bad: Dict[str, int] = {}
        for c in columns:
            col_dup = df[c].dropna()
            if col_dup.empty:
                per_col_bad[c] = 0
                continue
            bad_mask = df[c].duplicated(keep=False) & df[c].notna()
            per_col_bad[c] = int(bad_mask.sum())
            any_bad = any_bad | bad_mask
        bad = int(any_bad.sum())
        if bad == 0:
            return 0, "Every selected CDE is independently unique"
        worst = max(per_col_bad.items(), key=lambda kv: kv[1])
        return bad, f"{bad} rows fail uniqueness (worst CDE: {worst[0]} → {worst[1]} dup rows)"

    # --- Completeness --------------------------------------------------
    if dimension == "Completeness":
        sub_null = df[columns].isna()
        if op == "AND":
            bad_mask = sub_null.any(axis=1)
            bad = int(bad_mask.sum())
            example = "All selected CDEs filled on every row" if bad == 0 else (
                f"{bad} rows missing at least one of: {', '.join(columns)}"
            )
            return bad, example
        # OR — fail only when EVERY selected CDE is null on that row.
        bad_mask = sub_null.all(axis=1)
        bad = int(bad_mask.sum())
        example = "At least one selected CDE filled on every row" if bad == 0 else (
            f"{bad} rows where all of ({' or '.join(columns)}) are blank"
        )
        return bad, example

    # --- Validation (regex-based) -------------------------------------
    if dimension in ("Validation", "Validity"):
        pat = (regex_pattern or "").strip()
        if not pat:
            return 0, "Validation rule saved — supply a regex pattern to score it"
        try:
            re.compile(pat)
        except re.error as exc:
            return 0, f"Invalid regex pattern: {exc}"
        # Per-cell match. NaN counts as non-match (a blank can't satisfy a regex).
        match_frame = pd.DataFrame({
            c: df[c].astype(str).where(df[c].notna(), "").str.match(pat, na=False)
            for c in columns
        })
        if op == "AND":
            bad_mask = ~match_frame.all(axis=1)
            bad = int(bad_mask.sum())
            example = "All selected CDEs match the pattern on every row" if bad == 0 else (
                f"{bad} rows where at least one of ({', '.join(columns)}) fails the pattern"
            )
            return bad, example
        # OR — pass if ANY CDE matches per row; fail only when all fail.
        bad_mask = ~match_frame.any(axis=1)
        bad = int(bad_mask.sum())
        example = "At least one selected CDE matches on every row" if bad == 0 else (
            f"{bad} rows where none of ({', '.join(columns)}) match the pattern"
        )
        return bad, example

    # --- Generic fallback for Standardisation / Accuracy / Timeliness ----
    # AND → all selected CDEs must be non-null (presence check).
    # OR  → at least one non-null per row.
    # These dimensions don't have a universal per-cell evaluator without
    # the specific rule context, so we treat presence as the measurable
    # proxy and let the rule text carry the human-readable intent.
    sub_null = df[columns].isna()
    if op == "AND":
        bad_mask = sub_null.any(axis=1)
        bad = int(bad_mask.sum())
        example = "All selected CDEs present on every row" if bad == 0 else (
            f"{bad} rows missing at least one of: {', '.join(columns)}"
        )
    else:
        bad_mask = sub_null.all(axis=1)
        bad = int(bad_mask.sum())
        example = "At least one selected CDE present on every row" if bad == 0 else (
            f"{bad} rows where all of ({', '.join(columns)}) are blank"
        )
    return bad, example


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
    caps = _DIM_CAPS.get(dimension, {"multi": False, "operator": False})

    is_cross_field = dimension == "Cross-field Validation"

    # Decide single vs multi mode. A multi-capable dimension uses `columns`
    # when provided (any length ≥ 1); otherwise we fall back to the single
    # `column` field for backwards compatibility with old callers.
    multi_mode = False
    cols: List[str] = []
    single_col = ""
    operator = (body.operator or "AND").strip().upper()
    if operator not in ("AND", "OR"):
        operator = "AND"

    if caps["multi"] and (body.columns or is_cross_field):
        cols = [str(c).strip() for c in (body.columns or []) if str(c).strip()]
        if not cols and body.column:
            # Allow "a + b + c" or "a, b, c" syntax in the single field
            parts = [p.strip() for p in body.column.replace(",", "+").split("+") if p.strip()]
            cols = parts
        if is_cross_field:
            if len(cols) < 2:
                raise HTTPException(
                    status_code=400,
                    detail="Cross-field rules must reference at least 2 critical data elements",
                )
        else:
            if not cols:
                raise HTTPException(
                    status_code=400,
                    detail="At least one critical data element is required",
                )
        unknown = [c for c in cols if c not in all_columns]
        if unknown:
            raise HTTPException(
                status_code=400,
                detail=f"Unknown critical data element(s): {', '.join(unknown)}",
            )
        # Single-CDE on a multi-capable dimension — fall through to the
        # single-column path so operator is ignored and downstream
        # evaluation uses the regular validate_all_rules pipeline.
        if not is_cross_field and len(cols) == 1:
            multi_mode = False
            single_col = cols[0]
            cols = []
        else:
            multi_mode = True
    else:
        col = (body.column or "").strip()
        if not col:
            raise HTTPException(status_code=400, detail="Critical data element is required")
        if col not in all_columns:
            raise HTTPException(status_code=400, detail=f"Unknown critical data element: {col}")
        single_col = col

    # Column label is what shows in the rule table. For multi-CDE we
    # join with the operator so stewards see "name AND pan" or
    # "email OR phone" at a glance; cross-field keeps its plus-joined
    # convention (the resolver doesn't see an explicit operator).
    if multi_mode:
        if is_cross_field:
            column_label = " + ".join(cols)
        elif caps["operator"]:
            column_label = f" {operator} ".join(cols)
        else:
            column_label = " + ".join(cols)
    else:
        column_label = single_col

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
        # New: persist operator + atomic columns so downstream tools (and
        # future re-evaluations) don't have to re-parse the composite label.
        "Operator": operator if (multi_mode and caps["operator"]) else "",
        "Columns": ",".join(cols) if multi_mode else "",
    }

    existing = sess.ai_validation_rules
    if existing is None or (isinstance(existing, pd.DataFrame) and existing.empty):
        df_rules = pd.DataFrame([new_row])
    else:
        # Ensure newly added columns exist on the existing frame before concat.
        for new_col in ("Operator", "Columns"):
            if new_col not in existing.columns:
                existing = existing.copy()
                existing[new_col] = ""
        df_rules = pd.concat([existing, pd.DataFrame([new_row])], ignore_index=True)

    last_idx = df_rules.index[-1]

    # Evaluation routing:
    #   Cross-field   → existing engine path (expression sandbox or family resolver).
    #   Multi-CDE     → new dimension-aware evaluator (AND/OR semantics).
    #   Single-CDE    → unchanged validate_all_rules pipeline.
    if is_cross_field and new_row["Validation Expression"]:
        result = _run_llm_expression(
            {"code": new_row["Validation Expression"], "description": rule_text},
            df_data,
            cols,
        )
        if result is None:
            df_rules.at[last_idx, "Issues Found"] = 0
            df_rules.at[last_idx, "Issues Found Example"] = (
                "Cross-field — could not evaluate user-supplied expression"
            )
        else:
            df_rules.at[last_idx, "Issues Found"] = int(result.count)
            df_rules.at[last_idx, "Issues Found Example"] = result.example
    elif is_cross_field:
        df_rules = evaluate_cross_field_rules_in_df(df_rules, df_data)
    elif multi_mode:
        try:
            issues, example = _evaluate_multi_custom_rule(
                df_data, cols, dimension, operator, new_row["Regex Pattern"],
            )
        except Exception as exc:
            logger.warning("Multi-CDE custom rule eval failed: %s", exc, exc_info=True)
            issues, example = 0, f"Could not evaluate rule: {exc}"
        df_rules.at[last_idx, "Issues Found"] = int(issues)
        df_rules.at[last_idx, "Issues Found Example"] = example
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
