"""Data Quality endpoints — 1:1 parity with features/quality/ui.py.

Per-column rule editor with 6 modes (Clean/Replace/Extract/Validate/Case/Length),
preview, save, run, undo, rule library, AI Regex suggestion, and Rule Generator
import.
"""
from __future__ import annotations

import io
import json
import re
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

from ..deps import require_dataframe, scoped_columns
from ..services.azure_openai_config import AzureOpenAIConfig
from ..services.project_storage import (
    save_dq_config as _save_dq_config,
    save_rejected as _save_rejected,
    save_working as _save_working,
)
from ..services.cross_field_engine import (
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
    get_preview_failing,
    undo_last as _undo_last,
    _stringify,
)
from ..services.dq_rg_mapping import (
    get_enriched_rg_rules,
    get_rg_options_for_column,
    rg_row_to_applied_rule,
)
from ..session_store import SessionData

router = APIRouter(prefix="/quality", tags=["quality"])


# ---------- helpers ------------------------------------------------------

def _ensure_config(sess: SessionData) -> None:
    """Ensure every in-scope column has a dq_config entry."""
    for col in scoped_columns(sess):
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


class CrossFieldFixBody(BaseModel):
    action: str  # 'drop' | 'deduplicate'


# ---------- columns / config ---------------------------------------------

@router.get("/columns")
def list_columns(sess: SessionData = Depends(require_dataframe)) -> List[Dict[str, Any]]:
    """List columns with sample values + their current dq_config entries.

    Only returns columns the user has flagged as in-scope on Load Data.
    """
    _ensure_config(sess)
    out = []
    for col in scoped_columns(sess):
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


# Canonical DAMA-DMBOK dimension order — mirrors the Rule Generator
# so the Cleansing tabs land in the same sequence the steward already
# scanned in the previous step.
_DIM_ORDER = [
    "Completeness", "Validation", "Standardisation",
    "Uniqueness", "Accuracy", "Timeliness", "Cross-field Validation",
]

# Inferred DAMA dimension for legacy rules that pre-date the source/
# dimension tagging. Also used as the default when a user authors a
# custom rule from the per-column editor (where the steward doesn't
# pick a dimension explicitly).
_MODE_TO_DEFAULT_DIM = {
    "Validate": "Validation",
    "Clean":    "Standardisation",
    "Replace":  "Standardisation",
    "Case":     "Standardisation",
    "Length":   "Validation",
    "Extract":  "Standardisation",
}


def _compute_issue_count(df: pd.DataFrame, column: str, rule: Dict[str, Any]) -> int:
    """How many rows violate this rule? Drives the "only show rules
    with work to do" filter in /by-dimension.

    Returns the issue count, or ``-1`` when the rule has no mechanical
    interpretation (caller hides it — manual review is dead).
    """
    if column not in df.columns:
        return 0
    series = df[column]
    pattern = (rule.get("pattern") or "").strip()
    mode = rule.get("mode", "")
    dim = rule.get("dimension", "")
    rule_text = (rule.get("rule_text") or rule.get("name") or "").lower()

    # 1) Completeness FIRST. The rule's regex is by design a "not-blank"
    #    check (^(?=.*\S).*$), so we count nulls/blanks directly.
    #    Running it through the format-match path would exclude null
    #    rows and always return 0 — that was the bug.
    if dim == "Completeness" or "must not be blank" in rule_text or "not be null" in rule_text \
            or "cannot be null" in rule_text or "must be present" in rule_text:
        mask = series.isnull() | series.astype(str).str.strip().eq("")
        return int(mask.sum())

    # 2) Regex Validate / Length — strict pattern match. Null cells are
    #    a Completeness concern, not a format concern, so exclude them.
    #    Use _stringify so float-stored ints (2017.0 → "2017") match
    #    AI-generated integer regexes correctly.
    if pattern and mode in ("Validate", "Length", "Extract"):
        try:
            str_series = _stringify(series)
            non_null = series.notna() & str_series.str.strip().ne("")
            mask = ~str_series.str.match(pattern, na=False)
            return int((mask & non_null).sum())
        except Exception:
            return -1

    # 3) Uniqueness — duplicate rows.
    if dim == "Uniqueness" or "must be unique" in rule_text or "no duplicates" in rule_text:
        non_null = series.dropna()
        if non_null.empty:
            return 0
        return int(non_null.duplicated(keep=False).sum())

    # 4) Numeric coercion failures.
    if "must be numeric" in rule_text or "must be a numeric" in rule_text \
            or "must be an integer" in rule_text or "must be a number" in rule_text:
        non_null = series.dropna().astype(str)
        coerced = pd.to_numeric(non_null, errors="coerce")
        return int(coerced.isnull().sum())

    # 5) Date / timestamp parse failures.
    if any(tok in rule_text for tok in ("yyyy-mm-dd", "dd-mm-yyyy", "mm/dd/yyyy",
                                         "iso 8601", "iso8601", "valid date", "must be a date")):
        non_null = series.dropna().astype(str)
        coerced = pd.to_datetime(non_null, errors="coerce")
        return int(coerced.isnull().sum())

    # 6) Pure transforms (Clean / Replace / Case) don't reject rows but
    #    change values — show them if there's anything non-null to act on.
    if mode in ("Clean", "Replace", "Case"):
        return int(series.notna().sum())

    return -1


def _resolve_rule_dimension(rule: Dict[str, Any]) -> str:
    """Pick a dimension for a rule that was persisted before the source/
    dimension tags existed. Falls back to mode-based inference so old
    projects don't disappear from the new dimension tabs."""
    dim = (rule.get("dimension") or "").strip()
    if dim:
        return dim
    return _MODE_TO_DEFAULT_DIM.get(rule.get("mode", ""), "Standardisation")


def _rule_entry_from_applied(rule: Dict[str, Any], rule_idx: int) -> Dict[str, Any]:
    """Shape a dq_config applied_rule for the by-dimension response."""
    return {
        "rule_idx": rule_idx,
        "name": rule.get("name", ""),
        "mode": rule.get("mode", ""),
        "pattern": rule.get("pattern", ""),
        "replace": rule.get("replace", ""),
        "case": rule.get("case", ""),
        "length_mode": rule.get("length_mode", ""),
        "min_length": rule.get("min_length", 0),
        "max_length": rule.get("max_length", 50),
        "exact_length": rule.get("exact_length", 10),
        "source": rule.get("source", "custom"),
        "dimension": _resolve_rule_dimension(rule),
        "rule_text": rule.get("rule_text", ""),
        "status": "pending",         # imported, waiting to apply
        "executable": True,
        "multi_cde": False,
        "atomic_columns": [],
    }


RULE_STATUS_LABELS = {
    "actionable":         "Actionable",
    "passed":             "Passed",
    "applied":            "Applied",
    "unmapped":           "Needs regex mapping",
    "blocked_empty":      "Blocked — empty column",
    "blocked_incomplete": "Blocked — fix completeness first",
    "multi_cde":          "Cross-field (multi-CDE)",
    "invalid":            "Invalid — column missing",
    "dropped":            "Dropped by steward",
}

# Threshold below which a column is too sparse for Standardisation /
# Validation / Accuracy rules to produce meaningful results — they
# should be deferred until Completeness has been improved.
_INCOMPLETE_THRESHOLD = 0.20  # 20% filled

# Status order — only Actionable, Applied, Blocked, Unmapped, Invalid
# count as "needs attention" for the top progress meter. Passed is good.
_BUSY_STATUSES = {"actionable", "blocked_empty", "blocked_incomplete", "unmapped", "multi_cde", "invalid"}


def _applied_signatures(sess: SessionData) -> set:
    """Pull (column, mode, pattern) tuples for rules that have been
    executed against the data, so the lifecycle pipeline can mark them
    ``applied`` and stop offering Preview / Apply."""
    sigs = set()
    for entry in sess.validation_history or []:
        col = entry.get("column")
        for r in (entry.get("backup_applied_rules") or []):
            sigs.add((col, r.get("mode", ""), r.get("pattern", "")))
    return sigs


def _pending_signature_map(sess: SessionData) -> Dict[tuple, int]:
    """Map (column, mode, pattern) → rule_idx for rules sitting in
    ``dq_config[col].applied_rules`` (imported, awaiting preview/apply).
    """
    out: Dict[tuple, int] = {}
    for col, cfg in sess.dq_config.items():
        for idx, r in enumerate(cfg.get("applied_rules", [])):
            sig = (col, r.get("mode", ""), r.get("pattern", ""))
            out[sig] = idx
    return out


def _evaluate_rule_status(
    rg_row: pd.Series,
    rule_id: int,
    df: pd.DataFrame,
    col_health: Dict[str, Dict[str, Any]],
    real_cols: set,
    empty_set: set,
    applied_sigs: set,
    pending_sigs: Dict[tuple, int],
) -> Dict[str, Any]:
    """Run the full lifecycle pipeline for one RG rule. Always returns
    an entry — nothing is silently dropped. The ``status`` field is the
    terminal state; ``reason`` explains it in human terms; ``failure_count``
    is the rule's evaluated impact on the data when applicable."""
    dim = str(rg_row.get("Dimension", "") or "Other").strip()
    raw_col = str(rg_row.get("Column", "") or "").strip()
    raw_cols_meta = str(rg_row.get("Columns", "") or "").strip()
    rule_text = str(rg_row.get("Data Quality Rule", "") or "")
    pattern = str(rg_row.get("Regex Pattern", "") or "").strip()

    atomic = (
        [c.strip() for c in raw_cols_meta.split(",") if c.strip()]
        if raw_cols_meta else ([raw_col] if raw_col else [])
    )
    is_multi = len(atomic) > 1
    primary_col = atomic[0] if atomic else raw_col

    mapped = rg_row_to_applied_rule(rg_row) or {}
    mode = mapped.get("mode", "Validate" if pattern else "")

    base = {
        "rule_id": int(rule_id),
        "column": primary_col,
        "atomic_columns": atomic,
        "dimension": dim,
        "rule_text": rule_text,
        "pattern": pattern or mapped.get("pattern", ""),
        "mode": mode,
        "source": "ai",
        "is_multi_cde": is_multi,
        "rule_idx": None,
        "failure_count": 0,
        "reason": None,
        "suggested_action": None,
        # Carry full executable shape so /apply-rule / /preview-rule
        # have everything they need without re-querying rg_df.
        "replace": mapped.get("replace", ""),
        "case": mapped.get("case", ""),
        "length_mode": mapped.get("length_mode", ""),
        "min_length": mapped.get("min_length", 0),
        "max_length": mapped.get("max_length", 50),
        "exact_length": mapped.get("exact_length", 10),
        "name": mapped.get("name") or f"RG · {dim}: {rule_text[:48]}",
    }

    # 1) INVALID — column referenced by the rule doesn't exist.
    if not primary_col or primary_col not in real_cols:
        base["status"] = "invalid"
        base["reason"] = f"Column '{primary_col}' is not in the working dataset."
        return base

    # 2) MULTI-CDE — composite rules belong on the Cross-field tab.
    if is_multi:
        base["status"] = "multi_cde"
        base["reason"] = f"Composite rule across {' + '.join(atomic)} — evaluate on the Cross-field tab."
        return base

    # 3) BLOCKED_EMPTY — column is 100% null/blank.
    health = col_health.get(primary_col, {})
    if primary_col in empty_set and dim != "Completeness":
        base["status"] = "blocked_empty"
        base["reason"] = (
            f"Column is 100% empty. Drop or backfill before running {dim} rules — "
            "Completeness must be fixed first."
        )
        return base

    # 4) BLOCKED_INCOMPLETE — column too sparse for non-Completeness work.
    fill = float(health.get("fill_rate", 1.0))
    if dim not in ("Completeness", "Uniqueness") and fill < _INCOMPLETE_THRESHOLD and primary_col not in empty_set:
        base["status"] = "blocked_incomplete"
        base["reason"] = (
            f"Column is only {int(round(fill * 100))}% filled. "
            f"Apply Completeness rules first; rerun {dim} after backfill."
        )
        return base

    # 5) UNMAPPED — can't be evaluated mechanically (no regex / no rule_generator interpreter).
    if not mapped:
        base["status"] = "unmapped"
        base["reason"] = "Rule could not be converted to a mechanical check — dismiss or handle manually."
        base["suggested_action"] = "Drop"
        return base

    # 6) APPLIED — already executed against the dataset.
    sig = (primary_col, mode, pattern or mapped.get("pattern", ""))
    if sig in applied_sigs:
        base["status"] = "applied"
        base["reason"] = "Already applied — visible in history."
        return base

    # 7) ACTIONABLE vs PASSED — evaluate the rule.
    issues = _compute_issue_count(df, primary_col, mapped)
    if issues == -1:
        base["status"] = "unmapped"
        base["reason"] = "Could not evaluate mechanically — dismiss or handle manually."
        base["suggested_action"] = "Drop"
        return base
    base["failure_count"] = int(issues)

    # 8) Carry the imported rule_idx if it's already in dq_config (so
    #    the per-row Apply button can call /apply-rule directly).
    if sig in pending_sigs:
        base["rule_idx"] = pending_sigs[sig]

    if issues > 0:
        base["status"] = "actionable"
        base["suggested_action"] = (
            "Reject row" if mode in ("Validate", "Length", "Extract") else "Fix value"
        )
    else:
        base["status"] = "passed"
        base["reason"] = "All rows in the working dataset already satisfy this rule."
    return base


@router.get("/by-dimension")
def by_dimension(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Audit-grade lifecycle view of every Rule-Generator rule.

    Each rule lands in exactly one of these terminal states:
      • ``actionable``         – evaluated, has failing rows, ready to clean
      • ``passed``             – evaluated, no failing rows (audit evidence)
      • ``applied``            – already executed
      • ``unmapped``           – needs AI regex resolution or manual review
      • ``blocked_empty``      – target column is 100% empty
      • ``blocked_incomplete`` – column too sparse for this dimension
      • ``multi_cde``          – composite rule (use Cross-field tab)
      • ``invalid``            – references a column that doesn't exist

    The response surfaces every rule with its status, failure_count,
    and human-readable reason so the steward can answer "what happened
    to rule X?" for every generated rule.
    """
    _ensure_config(sess)

    # ── Column health
    real_cols = set(map(str, sess.df.columns)) if sess.df is not None else set()
    col_health: Dict[str, Dict[str, Any]] = {}
    empty_columns: List[Dict[str, Any]] = []
    if sess.df is not None and not sess.df.empty:
        total_rows = len(sess.df)
        for c in real_cols:
            try:
                series = sess.df[c]
                non_empty = int(series.dropna().astype(str).str.strip().ne("").sum())
                col_health[c] = {
                    "non_empty": non_empty,
                    "total": total_rows,
                    "fill_rate": (non_empty / total_rows) if total_rows else 0.0,
                    "is_empty": non_empty == 0,
                }
                if non_empty == 0:
                    empty_columns.append({"column": c, "total": total_rows})
            except Exception:
                col_health[c] = {"non_empty": 0, "total": total_rows, "fill_rate": 0.0, "is_empty": True}
                empty_columns.append({"column": c, "total": total_rows})

    empty_set = {ec["column"] for ec in empty_columns}
    applied_sigs = _applied_signatures(sess)
    pending_sigs = _pending_signature_map(sess)

    # ── Evaluate every generated rule
    rg_df = get_enriched_rg_rules(sess.ai_validation_rules)
    dim_to_rules: Dict[str, List[Dict[str, Any]]] = {d: [] for d in _DIM_ORDER}
    cross_count = 0

    if rg_df is not None and not rg_df.empty:
        for rg_idx, rg_row in rg_df.iterrows():
            dim = str(rg_row.get("Dimension", "") or "Other").strip()
            if dim == "Cross-field Validation":
                cross_count += 1
                continue
            entry = _evaluate_rule_status(
                rg_row, int(rg_idx), sess.df, col_health, real_cols,
                empty_set, applied_sigs, pending_sigs,
            )
            dim_to_rules.setdefault(dim, []).append(entry)

    # Surface user-authored rules that aren't in rg_df (e.g. custom
    # rules added directly through the per-column editor).
    rg_signatures = set()
    if rg_df is not None and not rg_df.empty:
        for _, r in rg_df.iterrows():
            col = str(r.get("Column", "") or "").strip()
            pat = str(r.get("Regex Pattern", "") or "").strip()
            rg_signatures.add((col, pat))
    for col, cfg in sess.dq_config.items():
        for idx, rule in enumerate(cfg.get("applied_rules", [])):
            sig = (col, rule.get("pattern", ""))
            if sig in rg_signatures:
                continue
            dim = _resolve_rule_dimension(rule)
            mode = rule.get("mode", "")
            pat = rule.get("pattern", "")
            applied_sig = (col, mode, pat)
            entry = {
                "rule_id": -1,
                "column": col,
                "atomic_columns": [col],
                "dimension": dim,
                "rule_text": rule.get("rule_text", "") or rule.get("name", ""),
                "pattern": pat,
                "mode": mode,
                "source": rule.get("source", "custom"),
                "is_multi_cde": False,
                "rule_idx": idx,
                "failure_count": 0,
                "reason": None,
                "suggested_action": None,
                "replace": rule.get("replace", ""),
                "case": rule.get("case", ""),
                "length_mode": rule.get("length_mode", ""),
                "min_length": rule.get("min_length", 0),
                "max_length": rule.get("max_length", 50),
                "exact_length": rule.get("exact_length", 10),
                "name": rule.get("name", ""),
            }
            if col not in real_cols:
                entry["status"] = "invalid"
                entry["reason"] = f"Column '{col}' is not in the working dataset."
            elif col in empty_set and dim != "Completeness":
                entry["status"] = "blocked_empty"
                entry["reason"] = "Column is 100% empty."
            elif applied_sig in applied_sigs:
                entry["status"] = "applied"
                entry["reason"] = "Already applied — visible in history."
            else:
                issues = _compute_issue_count(sess.df, col, rule)
                entry["failure_count"] = max(0, issues)
                if issues > 0:
                    entry["status"] = "actionable"
                    entry["suggested_action"] = (
                        "Reject row" if mode in ("Validate", "Length", "Extract") else "Fix value"
                    )
                else:
                    entry["status"] = "passed"
                    entry["reason"] = "All rows already satisfy this rule."
            dim_to_rules.setdefault(dim, []).append(entry)

    # ── Build per-dimension response
    dimensions = []
    for d in _DIM_ORDER:
        rules = dim_to_rules.get(d, [])
        applied_for_d = int(sess.applied_rules_by_dim.get(d, 0))
        if d == "Cross-field Validation":
            dimensions.append({
                "name": d,
                "rules": [],
                "generated_count": cross_count,
                "applied_count": applied_for_d,
                "counts": {
                    "actionable": 0, "passed": 0, "applied": applied_for_d,
                    "unmapped": 0, "blocked_empty": 0, "blocked_incomplete": 0,
                    "multi_cde": cross_count, "invalid": 0,
                },
                "failing_rows_total": 0,
            })
            continue
        counts = {k: 0 for k in RULE_STATUS_LABELS.keys()}
        for r in rules:
            counts[r.get("status", "invalid")] = counts.get(r.get("status", "invalid"), 0) + 1
        failing_rows_total = sum(r.get("failure_count", 0) for r in rules if r.get("status") == "actionable")
        rules.sort(key=lambda r: (
            # Actionable first, then unmapped, blocked, passed, applied, invalid
            {"actionable": 0, "unmapped": 1, "blocked_incomplete": 2, "blocked_empty": 3,
             "passed": 4, "applied": 5, "multi_cde": 6, "invalid": 7}.get(r.get("status"), 8),
            -r.get("failure_count", 0),
            r.get("column", ""),
        ))
        dimensions.append({
            "name": d,
            "rules": rules,
            "generated_count": len(rules),
            "applied_count": applied_for_d,
            "counts": counts,
            "failing_rows_total": failing_rows_total,
        })

    # ── Top-level totals
    all_rules = [r for d in dimensions for r in d["rules"]]
    # Row-count summary so the Cleansing UI can show "X of Y rows
    # cleansed" without an extra API hop. original_rows = the row count
    # at project load; current_rows = sess.df after every cleansing
    # action; rejected_rows = what landed in sess.reject_df.
    original_rows = int(len(sess.original_df)) if isinstance(sess.original_df, pd.DataFrame) else int(len(sess.df) if sess.df is not None else 0)
    current_rows = int(len(sess.df)) if sess.df is not None else 0
    rejected_rows = int(len(sess.reject_df)) if isinstance(sess.reject_df, pd.DataFrame) else 0
    columns_count = int(sess.df.shape[1]) if sess.df is not None else 0
    totals = {
        "generated": len(all_rules) + cross_count,
        "actionable": sum(1 for r in all_rules if r["status"] == "actionable"),
        "passed":     sum(1 for r in all_rules if r["status"] == "passed"),
        "applied":    sum(int(d.get("applied_count", 0)) for d in dimensions),
        "unmapped":   sum(1 for r in all_rules if r["status"] == "unmapped"),
        "blocked_empty":      sum(1 for r in all_rules if r["status"] == "blocked_empty"),
        "blocked_incomplete": sum(1 for r in all_rules if r["status"] == "blocked_incomplete"),
        "multi_cde":  cross_count + sum(1 for r in all_rules if r["status"] == "multi_cde"),
        "invalid":    sum(1 for r in all_rules if r["status"] == "invalid"),
        "rejected":   rejected_rows,
        "history":    len(sess.validation_history),
        "empty_columns": len(empty_columns),
        "failing_rows_total": sum(d.get("failing_rows_total", 0) for d in dimensions),
        # Dataset shape — rows before/after cleansing + the steady column count.
        "original_rows": original_rows,
        "current_rows":  current_rows,
        "rows_removed":  max(0, original_rows - current_rows),
        "columns":       columns_count,
    }
    return {
        "totals": totals,
        "status_labels": RULE_STATUS_LABELS,
        "empty_columns": empty_columns,
        "dimensions": dimensions,
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
    _persist_dq_config(sess)
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
        "source": "custom",
        "dimension": _MODE_TO_DEFAULT_DIM.get(cfg.get("mode", ""), "Standardisation"),
    }
    cfg["applied_rules"].append(rule)
    _persist_dq_config(sess)
    return {"ok": True, "rule": rule, "rule_count": len(cfg["applied_rules"])}


@router.delete("/applied-rule/{column}/{rule_idx}")
def delete_applied_rule(column: str, rule_idx: int,
                        sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    cfg = sess.dq_config.get(column)
    if not cfg or rule_idx < 0 or rule_idx >= len(cfg["applied_rules"]):
        raise HTTPException(status_code=404, detail="Rule not found")
    removed = cfg["applied_rules"].pop(rule_idx)
    _persist_dq_config(sess)
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
    _persist_dq_config(sess)
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


def _preview_one_rule(sess: SessionData, column: str, rule: Dict[str, Any]) -> Dict[str, Any]:
    """Run the failing-row preview against THIS specific rule's config.

    Returns the new shape from ``get_preview_failing`` — full rows of
    the dataset (all columns) that the rule would reject, capped at 20.
    For pure-transform rules (Clean / Replace / Case) which never reject,
    falls back to a 20-row Before/After sample with ``is_transform=True``
    so the UI can render the diff in a different style.
    """
    cfg_for_rule = {
        "mode": rule.get("mode", "Clean"),
        "pattern": rule.get("pattern", ""),
        "replace": rule.get("replace", ""),
        "case": rule.get("case", "UPPERCASE"),
        "length_mode": rule.get("length_mode", "Exact"),
        "min_length": rule.get("min_length", 0),
        "max_length": rule.get("max_length", 50),
        "exact_length": rule.get("exact_length", 10),
    }
    return get_preview_failing(sess.df, column, cfg_for_rule) or {
        "column": column, "rows": [], "total_failing": 0, "is_transform": False,
    }


@router.post("/preview-rule/{column}/{rule_idx}")
def preview_rule(column: str, rule_idx: int,
                 sess: SessionData = Depends(require_dataframe)) -> dict:
    """Preview a single rule against the working DataFrame. Returns the
    rule's config + 10 sample before/after rows. Used by the per-row
    Preview button on the Cleansing tab.
    """
    _ensure_config(sess)
    cfg = sess.dq_config.get(column)
    if not cfg:
        raise HTTPException(status_code=404, detail="Critical data element not found")
    rules = cfg.get("applied_rules", [])
    if rule_idx < 0 or rule_idx >= len(rules):
        raise HTTPException(status_code=404, detail="Rule not found")
    rule = rules[rule_idx]
    if rule.get("mode") == "ManualReview":
        return {
            "rows": [],
            "manual": True,
            "message": "This rule needs human review — no mechanical preview is possible.",
        }
    # Short-circuit on columns with no data — applying a rule to an
    # empty column produces no signal, just noise.
    if column in sess.df.columns:
        non_empty = int(sess.df[column].dropna().astype(str).str.strip().ne("").sum())
        if non_empty == 0:
            return {
                "rows": [],
                "manual": False,
                "column_empty": True,
                "message": f"Column '{column}' is 100% empty. Drop or backfill it before applying rules.",
                "rule_name": rule.get("name", ""),
            }
    preview = _preview_one_rule(sess, column, rule)
    return {
        "rows": preview.get("rows", []),
        "column": preview.get("column", column),
        "total_failing": int(preview.get("total_failing", 0)),
        "is_transform": bool(preview.get("is_transform", False)),
        "manual": False,
        "column_empty": False,
        "rule_name": rule.get("name", ""),
    }


class AiResolveBody(BaseModel):
    column: str
    rule_text: str
    dimension: str = "Validation"


class FailingRowsBody(BaseModel):
    column: str
    rule_text: str = ""
    regex_pattern: str = ""
    dimension: str = "Validation"
    limit: int = 20


def _try_llm_regex_for_rule(column: str, rule_text: str, samples: List[str]) -> Optional[str]:
    """Ask Azure OpenAI to turn a free-text rule into a regex. Returns the
    regex on success, ``None`` if the LLM refused or the answer didn't
    compile. Cheaper than re-running the full rule-generation pipeline
    because we only need one pattern."""
    if not AzureOpenAIConfig.AZURE_OPENAI_KEY or not AzureOpenAIConfig.AZURE_OPENAI_ENDPOINT:
        return None
    try:
        from openai import AzureOpenAI
        client = AzureOpenAI(
            azure_endpoint=AzureOpenAIConfig.AZURE_OPENAI_ENDPOINT,
            api_key=AzureOpenAIConfig.AZURE_OPENAI_KEY,
            api_version=AzureOpenAIConfig.AZURE_OPENAI_API_VERSION or "2024-02-01",
        )
        prompt = (
            f"Column: {column}\n"
            f"Sample values: {samples[:15]}\n"
            f"Data quality rule: {rule_text}\n\n"
            "Return ONLY a JSON object: "
            "{\"regex\": \"<python re pattern that ACCEPTS valid values>\", \"applies\": true|false, \"explanation\": \"<one line>\"}\n"
            "Set applies=false if the rule cannot be encoded as a single-cell regex "
            "(e.g. cross-row uniqueness, fuzzy accuracy checks, business judgement). "
            "The regex must be a complete pattern (anchor with ^ and $ unless inappropriate)."
        )
        resp = client.chat.completions.create(
            model=AzureOpenAIConfig.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a data quality regex expert. Output strict JSON only."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=250,
        )
        text = resp.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        import json as _json
        data = _json.loads(text)
        if not data.get("applies"):
            return None
        regex = (data.get("regex") or "").strip()
        if not regex:
            return None
        # Validate the regex compiles before handing it back.
        re.compile(regex)
        return regex
    except Exception:
        return None


class DropColumnsBody(BaseModel):
    columns: List[str]


class DropRuleBody(BaseModel):
    rule_id: Optional[int] = None
    column: Optional[str] = None
    rule_idx: Optional[int] = None


@router.post("/drop-rule")
def drop_rule(body: DropRuleBody,
              sess: SessionData = Depends(require_dataframe)) -> dict:
    """Drop a rule explicitly so it disappears from the lifecycle table.

    Two paths:
      • ``rule_id`` is an index into ``sess.ai_validation_rules`` — drops
        the row so the AI-generated rule is gone for good.
      • ``column`` + ``rule_idx`` drops a hand-imported rule from
        ``dq_config[col].applied_rules`` instead.

    Either way the rule no longer appears in /by-dimension.
    """
    dropped = False
    if body.rule_id is not None and isinstance(sess.ai_validation_rules, pd.DataFrame):
        df_r = sess.ai_validation_rules
        if int(body.rule_id) in df_r.index:
            sess.ai_validation_rules = df_r.drop(int(body.rule_id))
            dropped = True
    if body.column and body.rule_idx is not None:
        cfg = sess.dq_config.get(body.column)
        if cfg and 0 <= body.rule_idx < len(cfg.get("applied_rules", [])):
            cfg["applied_rules"].pop(body.rule_idx)
            _persist_dq_config(sess)
            dropped = True
    if not dropped:
        raise HTTPException(status_code=404, detail="Rule not found")
    return {"ok": True}


@router.post("/drop-unmapped")
def drop_unmapped(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Drop every AI rule that the system couldn't convert to an
    executable regex. These rules clutter the lifecycle table without
    contributing any mechanical signal — the steward can dismiss them
    in one click instead of going row by row.

    Identification logic mirrors the unmapped branch of
    ``_evaluate_rule_status``: a rule is unmapped when
    ``rg_row_to_applied_rule`` returns no mapping. We keep the rules
    that map cleanly + the rules that fall into blocked/multi-CDE
    states (those have legitimate reasons that aren't "AI couldn't
    figure it out").
    """
    if not isinstance(sess.ai_validation_rules, pd.DataFrame) or sess.ai_validation_rules.empty:
        return {"dropped": 0}
    df_r = sess.ai_validation_rules
    keep_mask = []
    for _, row in df_r.iterrows():
        mapped = rg_row_to_applied_rule(row)
        keep_mask.append(bool(mapped))
    dropped = int(len(df_r) - sum(keep_mask))
    sess.ai_validation_rules = df_r[keep_mask].reset_index(drop=True)
    return {"dropped": dropped}


@router.post("/reset-cleansing")
def reset_cleansing(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Restore the working DataFrame to its pre-cleansing state.

    Different from ``/undo`` (which pops the most recent step) — this
    rewinds every applied step, clears rejects, and resets the
    per-dimension applied counter so the progress meter goes back to 0.
    The rule definitions in ``dq_config`` stay so the steward can
    re-preview / re-apply without re-importing.
    """
    if sess.original_df is None:
        raise HTTPException(status_code=400, detail="No original dataset snapshot to restore.")
    sess.df = sess.original_df.copy()
    sess.reject_df = pd.DataFrame()
    sess.validation_history = []
    sess.applied_rules_by_dim = {}
    # Move every applied rule back into pending so the steward can re-apply.
    for col, cfg in sess.dq_config.items():
        cfg["enabled"] = bool(cfg.get("applied_rules"))
    _persist_cleansing_state(sess)
    return {"ok": True, "rows": int(len(sess.df))}


@router.post("/drop-columns")
def drop_columns(body: DropColumnsBody,
                 sess: SessionData = Depends(require_dataframe)) -> dict:
    """Remove fully-empty CDEs from the working DataFrame in one click.
    Drops the column data, the dq_config entry, and any AI rules that
    target it. The original_df is left intact so undo is still possible
    via the project's reset path."""
    if sess.df is None:
        raise HTTPException(status_code=400, detail="No working dataset loaded.")
    dropped = []
    for col in body.columns:
        if col in sess.df.columns:
            sess.df = sess.df.drop(columns=[col])
            dropped.append(col)
        sess.dq_config.pop(col, None)
    # Prune AI rules that targeted the dropped columns so they don't
    # come back as "unresolved" on the next /by-dimension call.
    if isinstance(sess.ai_validation_rules, pd.DataFrame) and not sess.ai_validation_rules.empty:
        df_r = sess.ai_validation_rules
        if "Column" in df_r.columns:
            mask = df_r["Column"].astype(str).isin(dropped)
            sess.ai_validation_rules = df_r[~mask].reset_index(drop=True)
    _persist_cleansing_state(sess)
    return {"dropped": dropped, "rows": int(len(sess.df)), "columns": int(len(sess.df.columns))}


@router.post("/resolve-all-manual")
def resolve_all_manual(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Batch-call the LLM to convert every unresolved manual-review rule
    into an executable regex. Adds the resolved ones to dq_config so they
    show up as pending. Dramatically cuts the "noise" residue."""
    _ensure_config(sess)
    rg_df = get_enriched_rg_rules(sess.ai_validation_rules)
    if rg_df is None or rg_df.empty:
        return {"resolved": 0, "skipped": 0}
    if sess.df is None:
        return {"resolved": 0, "skipped": 0}
    resolved = 0
    skipped = 0
    real_cols = set(map(str, sess.df.columns))
    for _, rg_row in rg_df.iterrows():
        dim = str(rg_row.get("Dimension", "") or "").strip()
        if dim == "Cross-field Validation":
            continue
        raw_col = str(rg_row.get("Column", "") or "").strip()
        raw_cols_meta = str(rg_row.get("Columns", "") or "").strip()
        atomic = (
            [c.strip() for c in raw_cols_meta.split(",") if c.strip()]
            if raw_cols_meta else ([raw_col] if raw_col else [])
        )
        if len(atomic) != 1:
            continue  # multi-CDE composites can't be regex'd
        col = atomic[0]
        if col not in real_cols:
            continue
        # Already mappable / has a regex? Not a manual rule.
        if rg_row_to_applied_rule(rg_row) is not None:
            continue
        non_null = sess.df[col].dropna().astype(str)
        if non_null.empty:
            continue
        rule_text = str(rg_row.get("Data Quality Rule", "") or "")
        regex = _try_llm_regex_for_rule(col, rule_text, non_null.head(15).tolist())
        if not regex:
            skipped += 1
            continue
        new_rule = {
            "name": f"AI-resolved · {rule_text[:60]}",
            "mode": "Validate",
            "pattern": regex,
            "replace": "",
            "case": "UPPERCASE",
            "length_mode": "Exact",
            "min_length": 0,
            "max_length": 50,
            "exact_length": 10,
            "timestamp": datetime.now().strftime("%H:%M:%S"),
            "source": "ai",
            "dimension": dim,
            "rule_text": rule_text,
        }
        # Skip if same pattern already applied for this column.
        existing = sess.dq_config.get(col, {}).get("applied_rules", [])
        if any(r.get("pattern") == regex and r.get("mode") == "Validate" for r in existing):
            continue
        sess.dq_config.setdefault(col, default_config())
        sess.dq_config[col]["applied_rules"].append(new_rule)
        sess.dq_config[col]["enabled"] = True
        resolved += 1
    _persist_dq_config(sess)
    return {"resolved": resolved, "skipped": skipped}


@router.post("/ai-resolve-rule")
def ai_resolve_rule(body: AiResolveBody,
                    sess: SessionData = Depends(require_dataframe)) -> dict:
    """Turn a free-text manual-review rule into an executable Validate
    rule by asking the LLM for a regex. On success, the rule is appended
    to ``dq_config[col].applied_rules`` so the steward can preview &
    apply it like any other pending rule. On failure (LLM declines or
    the regex doesn't compile) returns ``{success: false}`` and the UI
    keeps the rule in manual-review."""
    _ensure_config(sess)
    if body.column not in sess.dq_config:
        raise HTTPException(status_code=404, detail="Critical data element not found")
    if body.column not in sess.df.columns:
        raise HTTPException(status_code=404, detail="Column not in working DataFrame")

    samples = (
        sess.df[body.column].dropna().astype(str).head(15).tolist()
        if not sess.df[body.column].empty else []
    )
    regex = _try_llm_regex_for_rule(body.column, body.rule_text, samples)
    if not regex:
        return {
            "success": False,
            "message": "AI couldn't translate this rule into a single-cell regex. Keep as manual review.",
        }
    rule = {
        "name": f"AI-resolved · {body.rule_text[:60]}",
        "mode": "Validate",
        "pattern": regex,
        "replace": "",
        "case": "UPPERCASE",
        "length_mode": "Exact",
        "min_length": 0,
        "max_length": 50,
        "exact_length": 10,
        "timestamp": datetime.now().strftime("%H:%M:%S"),
        "source": "ai",
        "dimension": body.dimension,
        "rule_text": body.rule_text,
    }
    sess.dq_config[body.column]["applied_rules"].append(rule)
    sess.dq_config[body.column]["enabled"] = True
    _persist_dq_config(sess)
    return {
        "success": True,
        "regex": regex,
        "rule_idx": len(sess.dq_config[body.column]["applied_rules"]) - 1,
        "message": f"Resolved to regex: {regex}",
    }


@router.post("/failing-rows")
def failing_rows(body: FailingRowsBody,
                 sess: SessionData = Depends(require_dataframe)) -> dict:
    """Return up to ``body.limit`` rows from the working DataFrame that
    violate the supplied rule. Used by the manual-review workflow so a
    steward staring at 10k rows can focus on the suspicious ones.

    Resolution order:
      1. Regex (if ``regex_pattern`` is supplied) — run against the column.
      2. Completeness → null/blank rows.
      3. Uniqueness → duplicated-value rows.
      4. Otherwise → empty result with ``manual: true``.
    """
    if body.column not in sess.df.columns:
        raise HTTPException(status_code=404, detail="Column not in working DataFrame")
    df = sess.df
    col_series = df[body.column]
    rule_lower = (body.rule_text or "").lower()
    fail_mask = None

    if body.regex_pattern:
        try:
            fail_mask = ~col_series.astype(str).str.match(body.regex_pattern, na=False)
            # Treat null cells as non-failing for pattern matches so we
            # don't double-count them with completeness.
            fail_mask = fail_mask & col_series.notna() & col_series.astype(str).str.strip().ne("")
        except Exception as exc:
            raise HTTPException(status_code=400, detail=f"Invalid regex: {exc}")
    elif body.dimension == "Completeness" or "must not be blank" in rule_lower or "not be null" in rule_lower:
        fail_mask = col_series.isnull() | col_series.astype(str).str.strip().eq("")
    elif body.dimension == "Uniqueness" or "must be unique" in rule_lower:
        non_null = col_series.dropna()
        dup_values = set(non_null[non_null.duplicated(keep=False)].astype(str).tolist())
        fail_mask = col_series.astype(str).isin(dup_values)

    if fail_mask is None:
        return {
            "manual": True,
            "total": 0,
            "rows": [],
            "message": "This rule needs human inspection — no mechanical check is possible.",
        }

    total = int(fail_mask.sum())
    if total == 0:
        return {"manual": False, "total": 0, "rows": [], "message": "No failing rows — this rule already passes."}
    rows = df.loc[fail_mask].head(int(body.limit))
    return {
        "manual": False,
        "total": total,
        "rows": _df_records(rows),
    }


@router.post("/apply-rule/{column}/{rule_idx}")
def apply_rule(column: str, rule_idx: int,
               sess: SessionData = Depends(require_dataframe)) -> dict:
    """Apply ONE rule on ONE column. The engine's apply path pops the
    full applied_rules list on success, so we stash the off-target rules
    aside and reinstate them afterwards.
    """
    _ensure_config(sess)
    cfg = sess.dq_config.get(column)
    if not cfg:
        raise HTTPException(status_code=404, detail="Critical data element not found")
    rules = cfg.get("applied_rules", [])
    if rule_idx < 0 or rule_idx >= len(rules):
        raise HTTPException(status_code=404, detail="Rule not found")
    target = rules[rule_idx]
    if target.get("mode") == "ManualReview":
        raise HTTPException(
            status_code=400,
            detail="Manual-review rules can't be auto-applied. Edit the data manually and mark resolved.",
        )
    rest = rules[:rule_idx] + rules[rule_idx + 1:]
    cfg["applied_rules"] = [target]
    prev_enabled = cfg.get("enabled", False)
    cfg["enabled"] = True
    try:
        applied, rejected = _apply_col(sess, column)
    finally:
        cfg["applied_rules"] = rest + cfg.get("applied_rules", [])
        cfg["enabled"] = prev_enabled
    _persist_cleansing_state(sess)
    return {
        "ok": True,
        "applied": applied,
        "rejected": rejected,
        "rule": target.get("name", ""),
    }


def _persist_working(sess: SessionData) -> None:
    """Snapshot the in-memory working DataFrame to disk if a project is
    active. No-op otherwise (legacy session-only flow stays working)."""
    if sess.active_project_id and sess.df is not None:
        _save_working(sess.active_project_id, sess.df, sess.original_df)


def _persist_dq_config(sess: SessionData) -> None:
    if sess.active_project_id:
        _save_dq_config(sess.active_project_id, sess.dq_config)


def _persist_rejected(sess: SessionData) -> None:
    if sess.active_project_id:
        _save_rejected(sess.active_project_id, sess.reject_df)


def _persist_cleansing_state(sess: SessionData) -> None:
    """Snapshot every Cleansing-touched artifact in one call."""
    _persist_working(sess)
    _persist_dq_config(sess)
    _persist_rejected(sess)


@router.post("/apply-column/{column}")
def apply_column(column: str, sess: SessionData = Depends(require_dataframe)) -> dict:
    if column not in sess.dq_config:
        raise HTTPException(status_code=404, detail="Column not found")
    applied, rejected = _apply_col(sess, column)
    _persist_cleansing_state(sess)
    return {"ok": True, "applied": applied, "rejected": rejected, "rows_remaining": len(sess.df)}


@router.post("/apply-all")
def apply_all(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    result = _apply_all(sess)
    _persist_cleansing_state(sess)
    return result


@router.post("/import-ai/{dimension}")
def import_ai_dimension(dimension: str,
                        sess: SessionData = Depends(require_dataframe)) -> dict:
    """Pull every "unimported" AI rule for ``dimension`` into dq_config so
    it shows up as a pending rule the steward can preview and apply.

    Idempotent — rules already present in dq_config (same mode+pattern
    on the same column) are skipped.
    """
    _ensure_config(sess)
    rg_df = get_enriched_rg_rules(sess.ai_validation_rules)
    if rg_df is None or rg_df.empty:
        return {"imported": 0}
    imported = 0
    for _, rg_row in rg_df.iterrows():
        rg_dim = str(rg_row.get("Dimension", "") or "")
        if rg_dim != dimension:
            continue
        col = str(rg_row.get("Column", "") or "")
        if not col or col not in sess.dq_config:
            continue
        applied = rg_row_to_applied_rule(rg_row)
        if not applied:
            continue
        existing = sess.dq_config[col].get("applied_rules", [])
        if any(
            r.get("mode") == applied.get("mode")
            and r.get("pattern") == applied.get("pattern")
            for r in existing
        ):
            continue
        sess.dq_config[col]["applied_rules"].append(applied)
        sess.dq_config[col]["enabled"] = True
        imported += 1
    _persist_dq_config(sess)
    return {"imported": imported}


@router.post("/preview-dimension/{dimension}")
def preview_dimension(dimension: str,
                      sess: SessionData = Depends(require_dataframe)) -> dict:
    """Return per-column preview rows for every pending rule in this
    dimension. Used by the "Preview" step before the steward confirms
    Apply — human-in-the-loop, never auto-fix.
    """
    _ensure_config(sess)
    out: List[Dict[str, Any]] = []
    for col, cfg in sess.dq_config.items():
        rules = cfg.get("applied_rules", [])
        if not rules:
            continue
        dim_rules = [r for r in rules if _resolve_rule_dimension(r) == dimension]
        if not dim_rules:
            continue
        # Compose a synthetic config that runs only this dimension's
        # rules — fold each rule into a single preview pass.
        per_rule_preview = []
        for r in dim_rules:
            preview_cfg = {
                "mode": r.get("mode", "Clean"),
                "pattern": r.get("pattern", ""),
                "replace": r.get("replace", ""),
                "case": r.get("case", "UPPERCASE"),
                "length_mode": r.get("length_mode", "Exact"),
                "min_length": r.get("min_length", 0),
                "max_length": r.get("max_length", 50),
                "exact_length": r.get("exact_length", 10),
            }
            rows = get_preview(sess.df, col, preview_cfg) or []
            rejected = sum(1 for x in rows if x.get("Status") == "Rejected")
            per_rule_preview.append({
                "name": r.get("name", ""),
                "mode": r.get("mode", ""),
                "source": r.get("source", "custom"),
                "rule_text": r.get("rule_text", ""),
                "sample_rows": rows[:5],
                "sample_rejected": rejected,
            })
        out.append({"column": col, "rules": per_rule_preview})
    return {"dimension": dimension, "columns": out}


@router.post("/apply-dimension/{dimension}")
def apply_dimension(dimension: str,
                    sess: SessionData = Depends(require_dataframe)) -> dict:
    """Apply only the pending rules tagged with ``dimension`` and leave
    rules from other dimensions in dq_config untouched. Implemented by
    temporarily filtering applied_rules per column, running the existing
    engine path (so undo/history still work), and stitching the
    untouched rules back in afterward.
    """
    _ensure_config(sess)
    total_applied = 0
    total_rejected = 0
    cols_touched: List[str] = []
    for col in list(sess.dq_config.keys()):
        cfg = sess.dq_config[col]
        all_rules = cfg.get("applied_rules", [])
        if not all_rules:
            continue
        match = [r for r in all_rules if _resolve_rule_dimension(r) == dimension]
        rest = [r for r in all_rules if _resolve_rule_dimension(r) != dimension]
        if not match:
            continue
        # The engine pops applied_rules on success, so the stash-and-
        # restore dance keeps off-dimension rules safe.
        cfg["applied_rules"] = match
        prev_enabled = cfg.get("enabled", False)
        cfg["enabled"] = True
        try:
            applied, rejected = _apply_col(sess, col)
        finally:
            # Restore the off-dimension queue. The engine cleared
            # applied_rules on success — prepend any rest that survived.
            cfg["applied_rules"] = rest + cfg.get("applied_rules", [])
            cfg["enabled"] = prev_enabled
        total_applied += applied
        total_rejected += rejected
        cols_touched.append(col)
    _persist_cleansing_state(sess)
    return {
        "dimension": dimension,
        "applied": total_applied,
        "rejected": total_rejected,
        "columns": cols_touched,
    }


@router.post("/undo")
def undo(sess: SessionData = Depends(require_dataframe)) -> dict:
    ok = _undo_last(sess)
    if not ok:
        raise HTTPException(status_code=400, detail="Nothing to undo")
    _persist_cleansing_state(sess)
    return {"ok": True, "rows": len(sess.df)}


# ---------- toolbar batch actions ---------------------------------------

@router.post("/enable-all")
def enable_all(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    for col in scoped_columns(sess):
        sess.dq_config[col]["enabled"] = True
    _persist_dq_config(sess)
    return {"ok": True}


@router.post("/disable-all")
def disable_all(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    for col in scoped_columns(sess):
        sess.dq_config[col]["enabled"] = False
    _persist_dq_config(sess)
    return {"ok": True}


@router.post("/clear-rules")
def clear_rules(sess: SessionData = Depends(require_dataframe)) -> dict:
    _ensure_config(sess)
    for col in scoped_columns(sess):
        sess.dq_config[col]["applied_rules"] = []
    _persist_dq_config(sess)
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
    failing_sample: List[Dict[str, Any]] = []
    if result.failing_mask is not None and cols_to_show:
        failing_subset = sess.df.loc[result.failing_mask, cols_to_show].head(limit)
        failing_sample = _df_records(failing_subset, limit=limit)
    return {
        "rule": rule_text,
        "expression": result.expression,
        "family": result.family,
        "count": int(result.count),
        "example": result.example,
        "columns": cols_to_show,
        "failing_sample": failing_sample,
    }


def _resolve_cross_field_rule(
    rule_id: int, sess: SessionData,
) -> tuple:
    """Re-run the executor for a stored cross-field rule.

    Returns ``(rule_text, result)`` where ``result`` is the freshest
    ``CrossFieldResult`` against ``sess.df``. Raises HTTPException if the
    id is invalid or the rule is not a cross-field rule.
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
    try:
        result = evaluate_cross_field_rule(rule_text, sess.df, translator)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Cross-field executor failed: {exc}")
    return rule_text, result


@router.post("/cross-field/fix/{rule_id}")
def fix_cross_field(
    rule_id: int,
    body: CrossFieldFixBody,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Apply an automated fix to a cross-field rule's failing rows.

    Supported actions:
      - ``drop``: remove every row in the failing mask. Works for any
        family. WARNING: for ``composite_unique`` this drops *all*
        copies including the first occurrence.
      - ``deduplicate``: only valid for ``composite_unique``. Keeps the
        first occurrence of each tuple, drops the subsequent duplicates.

    Always operates on ``sess.df`` only; ``sess.original_df`` is left
    untouched so the user can reset via the Compare tab.
    """
    rule_text, result = _resolve_cross_field_rule(rule_id, sess)

    if result.failing_mask is None or int(result.count) == 0:
        return {
            "ok": True, "action": body.action, "rows_dropped": 0,
            "rows_remaining": int(len(sess.df)),
            "note": "Rule has no failing rows; nothing to do.",
        }

    # Snapshot state BEFORE the mutation so undo_last can restore it.
    # Cross-field fixes previously bypassed validation_history entirely —
    # which meant Undo Last did nothing, Reset All forgot the rejection
    # log, and the dropped rows never appeared in the Rejected Rows panel.
    backup_df = sess.df.copy()
    backup_reject = sess.reject_df.copy() if isinstance(sess.reject_df, pd.DataFrame) else pd.DataFrame()
    backup_dim_counts = dict(sess.applied_rules_by_dim)

    if body.action == "deduplicate":
        if result.family != "composite_unique":
            raise HTTPException(
                status_code=400,
                detail="'deduplicate' is only valid for composite_unique rules",
            )
        cols = [c for c in result.columns if c in sess.df.columns]
        before = int(len(sess.df))
        # Identify the rows we'll drop so we can copy them into reject_df.
        dup_mask = sess.df.duplicated(subset=cols, keep="first")
        dropped_rows_df = sess.df.loc[dup_mask].copy()
        # Preserve the pandas index — see apply_column_rules for why.
        sess.df = sess.df.loc[~dup_mask]
        dropped = before - int(len(sess.df))
    elif body.action == "drop":
        before = int(len(sess.df))
        dropped_rows_df = sess.df.loc[result.failing_mask].copy()
        sess.df = sess.df.loc[~result.failing_mask]
        dropped = before - int(len(sess.df))
    else:
        raise HTTPException(status_code=400, detail=f"Unknown action: {body.action}")

    # ── Funnel into the same state plumbing the per-column path uses ──
    # 1) Push the dropped rows into reject_df with rule context, so the
    #    Rejected Rows accordion shows them.
    if not dropped_rows_df.empty:
        rule_label = f"Cross-field · {rule_text[:80]}"
        dropped_rows_df["Rejection_Reason"] = f"{rule_label} — {body.action}"
        dropped_rows_df["Rejected_Column"] = " + ".join(result.columns or [])
        dropped_rows_df["Rejected_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if sess.reject_df is None or sess.reject_df.empty:
            sess.reject_df = dropped_rows_df
        else:
            sess.reject_df = pd.concat([sess.reject_df, dropped_rows_df], ignore_index=True)

    # 2) Increment the per-dimension applied counter so the Cleansing
    #    progress tile for Cross-field reflects the action.
    sess.applied_rules_by_dim["Cross-field Validation"] = (
        sess.applied_rules_by_dim.get("Cross-field Validation", 0) + 1
    )

    # 3) Push a validation_history entry shaped exactly like the per-
    #    column path's, so undo_last() can roll it back without special
    #    casing cross-field.
    sess.validation_history.append({
        "description": f"Applied cross-field rule · {result.family} · {body.action}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rejected_count": dropped,
        "backup_df": backup_df,
        "backup_reject_df": backup_reject,
        "backup_applied_rules": [{
            "mode": "CrossField",
            "name": f"CF rule {rule_id}",
            "pattern": "",
            "dimension": "Cross-field Validation",
            "source": "ai",
            "rule_text": rule_text,
        }],
        "backup_applied_dim_counts": backup_dim_counts,
        "column": " + ".join(result.columns or []),
    })

    sess.fixes_applied.append({
        "type": "cross_field",
        "rule_id": int(rule_id),
        "rule": rule_text[:120],
        "action": body.action,
        "family": result.family,
        "rows_dropped": dropped,
        "timestamp": datetime.now().isoformat(),
    })

    # Persist the mutation + rejects so a server restart picks them up.
    _persist_cleansing_state(sess)

    return {
        "ok": True,
        "action": body.action,
        "rows_dropped": dropped,
        "rows_remaining": int(len(sess.df)),
    }


@router.get("/cross-field/export/{rule_id}")
def export_cross_field_failing(
    rule_id: int,
    sess: SessionData = Depends(require_dataframe),
):
    """Stream a CSV of the rows that violate one cross-field rule.

    The export includes the full row (all columns) so the user has the
    context they need for review outside the tool.
    """
    rule_text, result = _resolve_cross_field_rule(rule_id, sess)

    if result.failing_mask is None or int(result.count) == 0:
        failing = sess.df.head(0)
    else:
        failing = sess.df.loc[result.failing_mask]

    buf = io.StringIO()
    failing.to_csv(buf, index_label="row_index")
    buf.seek(0)
    safe_name = "".join(c if c.isalnum() else "_" for c in rule_text[:50]).strip("_") or f"rule_{rule_id}"
    fname = f"failing_{safe_name}.csv"
    return StreamingResponse(
        iter([buf.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )
