"""Data Quality endpoints — 1:1 parity with features/quality/ui.py.

Per-column rule editor with 6 modes (Clean/Replace/Extract/Validate/Case/Length),
preview, save, run, undo, rule library, AI Regex suggestion, and Rule Generator
import.
"""
from __future__ import annotations

import io
import json
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd
from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from core.rule_library import (
    delete_rule_set as _delete_rule_set,
    list_rule_sets as _list_rule_sets,
    load_rule_set as _load_rule_set,
    save_rule_set as _save_rule_set,
)

from ..deps import require_dataframe
from ..services.azure_openai_config import AzureOpenAIConfig
from ..services.cross_field_engine import (
    _extract_value_list as _cf_extract_value_list,
    evaluate_cross_field_rule,
    make_azure_translator,
)
from ..services.dq_ai import get_ai_suggestion
from ..services.dq_engine import (
    apply_all_rules as _apply_all,
    apply_column_rules as _apply_col,
    default_config,
    generate_rule_name,
    get_preview,
    undo_last as _undo_last,
)
from ..services.dq_rg_mapping import get_enriched_rg_rules, get_rg_options_for_column
from ..session_store import SessionData

router = APIRouter(prefix="/quality", tags=["quality"])


# ---------- helpers ------------------------------------------------------

def _ensure_config(sess: SessionData) -> None:
    """Ensure every column has a dq_config entry (mirrors Streamlit per-row init)."""
    for col in sess.df.columns:
        if col not in sess.dq_config:
            sess.dq_config[col] = default_config()


def _df_records(df: Optional[pd.DataFrame], limit: Optional[int] = None) -> List[Dict[str, Any]]:
    if df is None or df.empty:
        return []
    out = df.head(limit) if limit else df
    out = out.where(pd.notnull(out), None)
    return out.astype(object).where(pd.notnull(out), None).to_dict(orient="records")


# ---------- schemas ------------------------------------------------------

class ColumnConfigPatch(BaseModel):
    enabled: Optional[bool] = None
    mode: Optional[str] = None
    pattern: Optional[str] = None
    replace: Optional[str] = None
    case: Optional[str] = None
    length_mode: Optional[str] = None
    min_length: Optional[int] = None
    max_length: Optional[int] = None
    exact_length: Optional[int] = None


class PreviewBody(BaseModel):
    column: str


class AiSuggestBody(BaseModel):
    column: str
    question: str = ""


class RgAddBody(BaseModel):
    labels: List[str]


class LibrarySaveBody(BaseModel):
    name: str
    description: str = ""


class LibraryLoadBody(BaseModel):
    name: str


class ImportRulesBody(BaseModel):
    rules: Dict[str, Any]


# ---------- columns / config ---------------------------------------------

@router.get("/columns")
def list_columns(sess: SessionData = Depends(require_dataframe)) -> List[Dict[str, Any]]:
    """List columns with sample values + their current dq_config entries."""
    _ensure_config(sess)
    out = []
    for col in sess.df.columns:
        sample_vals = sess.df[col].dropna().astype(str).head(5).tolist()
        sample_str = ", ".join(sample_vals[:5]) if sample_vals else "No data"
        if len(sample_str) > 80:
            sample_str = sample_str[:80] + "..."
        out.append({
            "column": str(col),
            "sample": sample_str,
            "config": sess.dq_config[col],
            "rule_count": len(sess.dq_config[col].get("applied_rules", [])),
        })
    return out


@router.get("/config")
def get_config(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    total_rules = sum(len(c.get("applied_rules", [])) for c in sess.dq_config.values())
    return {
        "rows": len(sess.df),
        "columns": len(sess.df.columns),
        "rejected": int(len(sess.reject_df)) if isinstance(sess.reject_df, pd.DataFrame) else 0,
        "total_rules": total_rules,
        "history_count": len(sess.validation_history),
        "config": sess.dq_config,
    }


@router.put("/config/{column}")
def update_config(column: str, patch: ColumnConfigPatch,
                  sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    if column not in sess.dq_config:
        raise HTTPException(status_code=404, detail="Column not found")
    cfg = sess.dq_config[column]
    for k, v in patch.dict(exclude_none=True).items():
        cfg[k] = v
    return {"ok": True, "config": cfg}


@router.post("/save-rule/{column}")
def save_rule(column: str, sess: SessionData = Depends(require_dataframe)) -> dict:
    """Push current column config into applied_rules (Streamlit Save button)."""
    _ensure_config(sess)
    if column not in sess.dq_config:
        raise HTTPException(status_code=404, detail="Column not found")
    cfg = sess.dq_config[column]
    rule_name = generate_rule_name(cfg)
    rule = {
        "name": rule_name,
        "mode": cfg["mode"],
        "pattern": cfg.get("pattern", ""),
        "replace": cfg.get("replace", ""),
        "case": cfg.get("case", "UPPERCASE"),
        "length_mode": cfg.get("length_mode", "Exact"),
        "min_length": cfg.get("min_length", 0),
        "max_length": cfg.get("max_length", 50),
        "exact_length": cfg.get("exact_length", 10),
        "timestamp": datetime.now().strftime("%H:%M:%S"),
    }
    cfg["applied_rules"].append(rule)
    return {"ok": True, "rule": rule, "rule_count": len(cfg["applied_rules"])}


@router.delete("/applied-rule/{column}/{rule_idx}")
def delete_applied_rule(column: str, rule_idx: int,
                        sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    cfg = sess.dq_config.get(column)
    if not cfg or rule_idx < 0 or rule_idx >= len(cfg["applied_rules"]):
        raise HTTPException(status_code=404, detail="Rule not found")
    removed = cfg["applied_rules"].pop(rule_idx)
    return {"ok": True, "removed": removed}


@router.post("/edit-rule/{column}/{rule_idx}")
def edit_applied_rule(column: str, rule_idx: int,
                      sess: SessionData = Depends(require_dataframe)) -> dict:
    """Streamlit 'Edit' button: load rule into config and pop it from applied_rules."""
    _ensure_config(sess)
    cfg = sess.dq_config.get(column)
    if not cfg or rule_idx < 0 or rule_idx >= len(cfg["applied_rules"]):
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = cfg["applied_rules"][rule_idx]
    cfg["mode"] = rule["mode"]
    cfg["pattern"] = rule.get("pattern", "")
    cfg["replace"] = rule.get("replace", "")
    cfg["case"] = rule.get("case", "UPPERCASE")
    cfg["length_mode"] = rule.get("length_mode", "Exact")
    cfg["min_length"] = rule.get("min_length", 0)
    cfg["max_length"] = rule.get("max_length", 50)
    cfg["exact_length"] = rule.get("exact_length", 10)
    cfg["applied_rules"].pop(rule_idx)
    return {"ok": True, "config": cfg}


# ---------- preview / apply / undo --------------------------------------

@router.post("/preview")
def preview(body: PreviewBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    cfg = sess.dq_config.get(body.column)
    if not cfg:
        raise HTTPException(status_code=404, detail="Column not found")
    rows = get_preview(sess.df, body.column, cfg) or []
    return {"rows": rows}


@router.post("/apply-column/{column}")
def apply_column(column: str, sess: SessionData = Depends(require_dataframe)) -> dict:
    if column not in sess.dq_config:
        raise HTTPException(status_code=404, detail="Column not found")
    applied, rejected = _apply_col(sess, column)
    return {"ok": True, "applied": applied, "rejected": rejected, "rows_remaining": len(sess.df)}


@router.post("/apply-all")
def apply_all(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    return _apply_all(sess)


@router.post("/undo")
def undo(sess: SessionData = Depends(require_dataframe)) -> dict:
    ok = _undo_last(sess)
    if not ok:
        raise HTTPException(status_code=400, detail="Nothing to undo")
    return {"ok": True, "rows": len(sess.df)}


# ---------- toolbar batch actions ---------------------------------------

@router.post("/enable-all")
def enable_all(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    for col in sess.df.columns:
        sess.dq_config[col]["enabled"] = True
    return {"ok": True}


@router.post("/disable-all")
def disable_all(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    for col in sess.df.columns:
        sess.dq_config[col]["enabled"] = False
    return {"ok": True}


@router.post("/clear-rules")
def clear_rules(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    for col in sess.df.columns:
        sess.dq_config[col]["applied_rules"] = []
    return {"ok": True}


# ---------- rejected / history ------------------------------------------

@router.get("/rejected")
def get_rejected(sess: SessionData = Depends(require_dataframe)) -> dict:
    df = sess.reject_df
    rows = _df_records(df, limit=50) if isinstance(df, pd.DataFrame) else []
    total = int(len(df)) if isinstance(df, pd.DataFrame) else 0
    return {"total": total, "preview": rows}


@router.post("/download-rejected")
def download_rejected(sess: SessionData = Depends(require_dataframe)):
    df = sess.reject_df
    if not isinstance(df, pd.DataFrame) or df.empty:
        raise HTTPException(status_code=400, detail="No rejected records")
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        df.to_excel(writer, sheet_name="Rejected", index=False)
    output.seek(0)
    fname = f"rejected_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return StreamingResponse(
        output,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.get("/history")
def get_history(sess: SessionData = Depends(require_dataframe)) -> List[Dict[str, Any]]:
    return [
        {
            "description": h.get("description"),
            "timestamp": h.get("timestamp"),
            "rejected_count": h.get("rejected_count", 0),
        }
        for h in sess.validation_history
    ]


# ---------- AI suggestion ------------------------------------------------

@router.post("/ai-suggest")
def ai_suggest(body: AiSuggestBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    if body.column not in sess.df.columns:
        raise HTTPException(status_code=404, detail="Column not found")
    sug = get_ai_suggestion(sess.df, body.column, body.question)
    if not sug:
        raise HTTPException(status_code=400, detail="No suggestion (column has no data?)")
    return {"suggestion": sug}


# ---------- Rule Generator integration -----------------------------------

@router.get("/rg-rules/{column}")
def rg_rules_for_column(column: str, sess: SessionData = Depends(require_dataframe)) -> dict:
    rg_full = get_enriched_rg_rules(sess.ai_validation_rules)
    if rg_full is None or rg_full.empty:
        return {"available": False, "options": []}
    options = get_rg_options_for_column(rg_full, column)
    return {"available": True, "options": options}


@router.post("/rg-add/{column}")
def rg_add(column: str, body: RgAddBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    cfg = sess.dq_config.get(column)
    if not cfg:
        raise HTTPException(status_code=404, detail="Column not found")
    rg_full = get_enriched_rg_rules(sess.ai_validation_rules)
    if rg_full is None or rg_full.empty:
        raise HTTPException(status_code=400, detail="No Rule Generator rules in session")
    options = get_rg_options_for_column(rg_full, column)
    label_to_rule = {o["label"]: o["rule"] for o in options}
    added = 0
    for lbl in body.labels:
        if lbl in label_to_rule:
            cfg["applied_rules"].append(label_to_rule[lbl])
            added += 1
    return {"ok": True, "added": added, "rule_count": len(cfg["applied_rules"])}


# ---------- Rule Library -------------------------------------------------

@router.get("/library")
def library_list() -> List[Dict[str, Any]]:
    try:
        return _list_rule_sets()
    except Exception:
        return []


@router.post("/library/save")
def library_save(body: LibrarySaveBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Name required")
    rid = _save_rule_set(body.name, sess.dq_config, body.description)
    return {"ok": True, "id": rid}


@router.post("/library/load")
def library_load(body: LibraryLoadBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    loaded = _load_rule_set(body.name)
    if not loaded:
        raise HTTPException(status_code=404, detail="Rule set not found")
    cols = sess.df.columns.tolist()
    imported = 0
    for cname, cfg in loaded.items():
        if cname in cols:
            sess.dq_config[cname] = cfg
            imported += 1
    return {"ok": True, "imported": imported}


@router.delete("/library/{name}")
def library_delete(name: str) -> dict:
    ok = _delete_rule_set(name)
    return {"ok": bool(ok)}


# ---------- Import / Export rules JSON -----------------------------------

@router.get("/export-rules")
def export_rules(sess: SessionData = Depends(require_dataframe)):
    _ensure_config(sess)
    if not sess.dq_config:
        raise HTTPException(status_code=400, detail="No rules configured")
    serializable = {}
    for col_name, cfg in sess.dq_config.items():
        serializable[col_name] = {
            "enabled": cfg.get("enabled", False),
            "mode": cfg.get("mode", "Clean"),
            "pattern": cfg.get("pattern", ""),
            "replace": cfg.get("replace", ""),
            "case": cfg.get("case", "UPPERCASE"),
            "length_mode": cfg.get("length_mode", "Exact"),
            "min_length": cfg.get("min_length", 0),
            "max_length": cfg.get("max_length", 50),
            "exact_length": cfg.get("exact_length", 10),
            "applied_rules": cfg.get("applied_rules", []),
        }
    payload = json.dumps({"version": 1, "rules": serializable}, indent=2)
    fname = f"dq_rules_{datetime.now():%Y%m%d_%H%M%S}.json"
    return StreamingResponse(
        io.BytesIO(payload.encode("utf-8")),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/import-rules")
async def import_rules(file: UploadFile = File(...),
                       sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    try:
        content = await file.read()
        data = json.loads(content.decode("utf-8"))
        rules = data.get("rules", data)
        cols = set(sess.df.columns.tolist())
        imported = 0
        for col_name, cfg in rules.items():
            if col_name not in cols:
                continue
            sess.dq_config[col_name] = {
                "enabled": cfg.get("enabled", False),
                "mode": cfg.get("mode", "Clean"),
                "pattern": cfg.get("pattern", ""),
                "replace": cfg.get("replace", ""),
                "case": cfg.get("case", "UPPERCASE"),
                "length_mode": cfg.get("length_mode", "Exact"),
                "min_length": cfg.get("min_length", 0),
                "max_length": cfg.get("max_length", 50),
                "exact_length": cfg.get("exact_length", 10),
                "applied_rules": cfg.get("applied_rules", []),
            }
            imported += 1
        return {"ok": True, "imported": imported}
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Import failed: {exc}")


# ---------- cross-field rules -------------------------------------------

def _build_cross_field_translator() -> Optional[Any]:
    """Lazily build the LLM translator for unparsed cross-field rules.

    Returns ``None`` if Azure OpenAI is not configured — the caller will
    then run only the rule-based family parsers.
    """
    if AzureOpenAIConfig.validate():
        return None
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            api_version=AzureOpenAIConfig.AZURE_OPENAI_API_VERSION,
            azure_endpoint=AzureOpenAIConfig.AZURE_OPENAI_ENDPOINT,
            api_key=AzureOpenAIConfig.AZURE_OPENAI_KEY,
        )
        return make_azure_translator(client, AzureOpenAIConfig.AZURE_OPENAI_DEPLOYMENT)
    except Exception:
        return None


@router.get("/cross-field/rules")
def list_cross_field_rules(
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Return every cross-field rule generated for this session, freshly
    evaluated against the current DataFrame.

    Each rule includes the column tuple, dimension, rule text, executable
    expression (when one was derived), issue count, and example failures.
    Rules whose shape couldn't be parsed by either the family classifier
    or the LLM translator are returned with ``family='manual'``.
    """
    df_rules = sess.ai_validation_rules
    if df_rules is None or not isinstance(df_rules, pd.DataFrame) or df_rules.empty:
        return {"rules": [], "evaluated": False}

    cross_mask = df_rules["Dimension"].astype(str).str.strip() == "Cross-field Validation"
    if not cross_mask.any():
        return {"rules": [], "evaluated": True}

    translator = _build_cross_field_translator()
    out: List[Dict[str, Any]] = []
    for idx, row in df_rules[cross_mask].iterrows():
        rule_text = str(row.get("Data Quality Rule", ""))
        try:
            result = evaluate_cross_field_rule(rule_text, sess.df, translator)
        except Exception as exc:
            out.append({
                "id": int(idx),
                "columns": str(row.get("Column", "")),
                "dimension": "Cross-field Validation",
                "rule": rule_text,
                "expression": "",
                "family": "manual",
                "count": 0,
                "example": f"Executor error: {exc}",
            })
            continue
        out.append({
            "id": int(idx),
            "columns": " + ".join(result.columns) if result.columns else str(row.get("Column", "")),
            "dimension": "Cross-field Validation",
            "rule": rule_text,
            "expression": result.expression,
            "family": result.family,
            "count": int(result.count),
            "example": result.example,
        })
    return {"rules": out, "evaluated": True}


@router.get("/cross-field/failing-rows/{rule_id}")
def cross_field_failing_rows(
    rule_id: int,
    limit: int = 50,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Return up to ``limit`` rows that violate a specific cross-field rule.

    ``rule_id`` is the dataframe index of the rule in
    ``sess.ai_validation_rules``. The endpoint re-runs the executor and
    returns the indices and values of the failing rows for the columns
    the rule actually involves.
    """
    df_rules = sess.ai_validation_rules
    if df_rules is None or not isinstance(df_rules, pd.DataFrame) or df_rules.empty:
        raise HTTPException(status_code=404, detail="No cross-field rules generated yet")
    if rule_id not in df_rules.index:
        raise HTTPException(status_code=404, detail="Rule not found")

    row = df_rules.loc[rule_id]
    if str(row.get("Dimension", "")).strip() != "Cross-field Validation":
        raise HTTPException(status_code=400, detail="Rule is not a cross-field rule")

    rule_text = str(row.get("Data Quality Rule", ""))
    translator = _build_cross_field_translator()

    # Re-run via the executor to get the column list + a fresh mask. The
    # cleanest way to surface failing rows is to evaluate the same logic
    # the executor used; for the four mechanical families we re-derive
    # the mask here. For LLM-translated rules we can't re-execute the
    # mask without re-calling the LLM, so we return the example string
    # already produced by the executor.
    try:
        result = evaluate_cross_field_rule(rule_text, sess.df, translator)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cross-field executor failed: {exc}")

    cols_to_show = [c for c in result.columns if c in sess.df.columns]
    return {
        "rule": rule_text,
        "expression": result.expression,
        "family": result.family,
        "count": int(result.count),
        "example": result.example,
        "columns": cols_to_show,
        "failing_sample": _df_records(
            sess.df.head(limit) if result.family == "manual" else _failing_subset(sess.df, rule_text, result, limit),
            limit=limit,
        ) if cols_to_show else [],
    }


def _failing_subset(df: pd.DataFrame, rule_text: str, result, limit: int) -> pd.DataFrame:
    """Re-derive the failing-row mask for the four mechanical families.

    For the LLM-translated family we don't re-evaluate here because that
    would need a second LLM call; we just return the head of the relevant
    columns so the user can eyeball them.
    """
    cols = [c for c in result.columns if c in df.columns]
    if not cols:
        return df.head(0)
    if result.family == "composite_unique":
        sub = df[cols]
        mask = sub.duplicated(keep=False)
        return sub[mask].head(limit)
    if result.family == "prefix_from_sibling" and len(cols) >= 2:
        target, sibling = cols[0], cols[1]
        target_str = df[target].astype(str).str.upper().str.strip()
        sibling_str = df[sibling].astype(str).str.upper().str.strip()
        either_blank = (
            df[target].isnull() | df[target].astype(str).str.strip().eq("")
            | df[sibling].isnull() | df[sibling].astype(str).str.strip().eq("")
        )
        mask = ~target_str.combine(sibling_str, lambda t, s: bool(s) and t.startswith(s)) & ~either_blank
        return df.loc[mask, cols].head(limit)
    if result.family == "arithmetic" and len(cols) >= 3:
        target = cols[0]
        addends = cols[1:]
        target_num = pd.to_numeric(df[target], errors="coerce")
        expected = sum(pd.to_numeric(df[c], errors="coerce") for c in addends)
        # Pull the tolerance back out of the description: e.g. "± 0.01".
        import re
        m = re.search(r"[±\+\-]\s*([0-9]*\.?[0-9]+)", result.expression)
        tol = float(m.group(1)) if m else 0.0
        mask = (target_num - expected).abs() > tol
        mask = mask & target_num.notna() & expected.notna()
        return df.loc[mask, cols].head(limit)
    if result.family == "conditional_presence" and len(cols) >= 2:
        target, context = cols[0], cols[1]
        values = _cf_extract_value_list(rule_text) or []
        if not values:
            return df.head(0)
        values_norm = {v.strip().lower() for v in values}
        in_scope = df[context].astype(str).str.strip().str.lower().isin(values_norm)
        blank = df[target].isnull() | df[target].astype(str).str.strip().eq("")
        mask = in_scope & blank
        return df.loc[mask, cols].head(limit)
    return df.head(0)
