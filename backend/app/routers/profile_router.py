"""Profiling endpoints — 1:1 parity with features/profiling/ui.py.

Endpoints:
  POST /profile/run                       run DataProfilerEngine and store profiles
  GET  /profile/kpi                       6 top KPIs (rows, cols, quality, completeness, missing, fill rate)
  GET  /profile/overview                  data for all 18 Plotly charts in Overview tab
  GET  /profile/correlation               correlation matrix + high pairs (param: method)
  GET  /profile/columns                   list of column profile cards (with duplicate values + groups)
  POST /profile/match-rules               generate_match_rules
  GET  /profile/llm-status                Azure OpenAI configured?
  POST /profile/ai-rules/generate         DynamicValidationDetector.generate_comprehensive_dq_rules
  GET  /profile/ai-rules                  current unified rules (DataFrame)
  POST /profile/ai-rules/clear            clear unified rules
  POST /profile/export/excel              7-sheet Excel report
  POST /profile/export/json               JSON report
  POST /profile/drift/save-baseline       save_baseline
  GET  /profile/drift/baselines           list_baselines
  DELETE /profile/drift/baselines/{name}  delete_baseline
  POST /profile/drift/detect              detect_drift
"""
from __future__ import annotations

import io
from collections import Counter
from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from core.drift_detector import (
    delete_baseline as _delete_baseline,
    detect_drift as _detect_drift,
    list_baselines as _list_baselines,
    load_baseline as _load_baseline,
    save_baseline as _save_baseline,
)
from core.profiler import DataProfilerEngine

from ..db import get_db
from ..deps import require_dataframe, scoped_dataframe
from ..models import Project
from ..services.ai_validation_engine import (
    AIValidationEngine,
    DynamicValidationDetector,
)
from ..services.azure_openai_config import AzureOpenAIConfig
from ..services.match_rules import (
    find_duplicate_groups,
    generate_match_rules,
    get_duplicate_count_values,
    safe_get_special_chars,
)
from ..services.dashboard import collect_risk_counts, collect_top_issues
from ..services.profile_export import build_excel_report, build_json_report
from ..services.project_storage import save_glossary
from ..services.accuracy_report import compute_accuracy_report
from ..services.cde_recommender import column_set_fingerprint as _cde_fingerprint
from ..services.completeness_report import compute_completeness_report
from ..services.dama_assessment import compute_executive_summary
from ..services.project_storage import load_cde_meta as _load_cde_meta
from ..services.quality_dashboard import compute_quality_dashboard
from ..services.semantic_glossary import generate_semantic_glossary
from ..services.standardisation_report import compute_standardisation_report
from ..services.stream_context import build_project_context
from ..services.timeliness_report import compute_timeliness_report
from ..services.uniqueness_report import compute_uniqueness_report
from ..services.validation_report import compute_validation_report
from ..session_store import SessionData

router = APIRouter(prefix="/profile", tags=["profile"])


# ---------- helpers ------------------------------------------------------

def _ensure_profiles(sess: SessionData) -> Dict[str, Any]:
    if not sess.column_profiles:
        df = scoped_dataframe(sess)
        engine = DataProfilerEngine(df, sess.filename)
        engine.profile(fast_mode=True)
        sess.column_profiles = dict(engine.column_profiles)
        sess.quality_report = engine.quality_report
    return sess.column_profiles


def _profile_df(df: pd.DataFrame, profiles: Dict[str, Any]) -> pd.DataFrame:
    rows = []
    for col, p in profiles.items():
        dup_count = p.total_rows - p.unique_count
        rows.append({
            "Column Name": col,
            "Data Type": str(p.dtype),
            "Total Rows": int(p.total_rows),
            "Non-Null Count": int(p.total_rows - p.null_count),
            "Null Count": int(p.null_count),
            "Null Percentage": float(p.null_percentage),
            "Unique Count": int(p.unique_count),
            "Duplicate Count": int(dup_count),
            "Duplicate Count Values": get_duplicate_count_values(df, col, max_items=None),
            "Unique Percentage": float(p.unique_percentage),
            "Min Length": int(getattr(p, "min_length", 0) or 0),
            "Max Length": int(getattr(p, "max_length", 0) or 0),
            "Avg Length": float(getattr(p, "avg_length", 0) or 0),
            "Risk Level": str(getattr(p, "risk_level", "Low")),
            "Risk Score": int(getattr(p, "risk_score", 0) or 0),
        })
    return pd.DataFrame(rows)


# ---------- run ----------------------------------------------------------

@router.post("/run")
def run_profile(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """Run profiler and persist column_profiles + quality_report on session."""
    df = scoped_dataframe(sess)
    engine = DataProfilerEngine(df, sess.filename)
    try:
        engine.profile(fast_mode=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Profiling failed: {exc}")
    sess.column_profiles = dict(engine.column_profiles)
    sess.quality_report = engine.quality_report

    # Push the quality score + status back to the project row so the
    # Home page's tiles reflect the latest profile.
    if sess.active_project_id and engine.quality_report is not None:
        project = (
            db.query(Project).filter(Project.id == sess.active_project_id).one_or_none()
        )
        if project is not None:
            score = getattr(engine.quality_report, "overall_score", None)
            if isinstance(score, (int, float)):
                project.quality_score = float(score)
            if project.status in ("empty", "data_loaded", None):
                project.status = "profiled"
            db.commit()

    return {
        "ok": True,
        "rows": int(len(df)),
        "columns": int(len(df.columns)),
        "profiled_columns": len(sess.column_profiles),
    }


# ---------- KPI ----------------------------------------------------------

@router.get("/dashboard")
def dashboard(sess: SessionData = Depends(require_dataframe)) -> dict:
    """1:1 port of features/dashboard/ui.py:render_dashboard.

    Returns everything the Dashboard React page needs in one payload:
      - 6 KPI values
      - quality_score for the gauge
      - top_issues list (severity-sorted)
      - dtype_distribution for donut
      - top_null_columns for horizontal bar
      - risk_counts (Low/Medium/High)
      - recent_operations (last 10 from fixes_applied)

    Safe to call before /profile/run — falls back gracefully when profiles
    haven't been computed yet.
    """
    df = scoped_dataframe(sess)
    profiles = sess.column_profiles  # may be empty
    quality_report = sess.quality_report

    total_rows = len(df)
    total_cols = len(df.columns)
    total_cells = total_rows * total_cols
    missing_cells = int(df.isna().sum().sum())
    missing_percentage = round((missing_cells / total_cells * 100) if total_cells else 0.0, 2)
    duplicate_rows = (
        int(getattr(quality_report, "exact_duplicate_rows", 0))
        if quality_report else int(df.duplicated().sum())
    )
    memory_mb = round(df.memory_usage(deep=True).sum() / (1024 * 1024), 2)

    overall_score = getattr(quality_report, "overall_score", None) if quality_report else None
    quality_score = float(overall_score) if isinstance(overall_score, (int, float)) else None

    dtype_counts = Counter(str(t) for t in df.dtypes.astype(str))

    # Top missing-value columns: prefer profiles' null_percentage (matches Streamlit),
    # fall back to direct df calc.
    if profiles:
        null_data = [
            {"column": c, "null_pct": round(float(p.null_percentage), 1)}
            for c, p in profiles.items()
            if getattr(p, "null_percentage", 0) > 0
        ]
        null_data.sort(key=lambda x: x["null_pct"], reverse=True)
        top_null = null_data[:10]
    else:
        null_pct_per_col = (df.isna().mean() * 100).round(2).to_dict()
        top_null = [
            {"column": c, "null_pct": float(p)}
            for c, p in sorted(null_pct_per_col.items(), key=lambda kv: kv[1], reverse=True)
            if p > 0
        ][:10]

    risk_counts = collect_risk_counts(profiles) if profiles else {"Low": 0, "Medium": 0, "High": 0}
    top_issues = collect_top_issues(
        profiles or {}, quality_report, missing_percentage, duplicate_rows, total_rows,
    )[:8]

    recent_operations = list(reversed((sess.fixes_applied or [])[-10:]))

    return {
        "rows": total_rows,
        "columns": total_cols,
        "memory_mb": memory_mb,
        "missing_cells": missing_cells,
        "missing_percentage": missing_percentage,
        "duplicate_rows": duplicate_rows,
        "quality_score": quality_score,
        "dtype_distribution": dict(dtype_counts),
        "top_null_columns": top_null,
        "risk_counts": risk_counts,
        "top_issues": top_issues,
        "recent_operations": recent_operations,
        "has_profiles": bool(profiles),
    }


@router.get("/kpi")
def kpi(sess: SessionData = Depends(require_dataframe)) -> dict:
    df = scoped_dataframe(sess)
    profiles = _ensure_profiles(sess)
    total_rows = len(df)
    total_cols = len(df.columns)
    total_cells = total_rows * total_cols
    missing_cells = sum(int(p.null_count) for p in profiles.values())
    completeness = ((total_cells - missing_cells) / total_cells * 100) if total_cells else 0

    quality_scores: List[float] = []
    for p in profiles.values():
        comp = float(getattr(p, "non_null_percentage", 100))
        uniq = min(100.0, p.unique_percentage * 1.2) if p.unique_percentage < 100 else 90.0
        consistency = 100.0 - (20 if hasattr(p, "formatting_info") and p.formatting_info
                               and not p.formatting_info.get("consistent_case", True) else 0)
        validity = 100.0 - min(20.0, len(safe_get_special_chars(p)) * 2)
        quality_scores.append(comp * 0.4 + uniq * 0.3 + consistency * 0.2 + validity * 0.1)
    avg_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0
    fill_rate = (100 - (missing_cells / total_cells * 100)) if total_cells else None

    return {
        "rows": total_rows,
        "columns": total_cols,
        "quality_pct": float(avg_quality),
        "completeness_pct": round(float(completeness), 2),
        "missing_cells": missing_cells,
        "fill_rate_pct": round(float(fill_rate), 2) if fill_rate is not None else None,
    }


# ---------- DAMA Executive Summary --------------------------------------

def _resolve_glossary(sess: SessionData, df: pd.DataFrame) -> Optional[Dict[str, Any]]:
    """Find the best available AI-generated column classification.

    Priority order — entirely AI-driven, no column-name keyword fallback:
      1. ``cde_meta`` cached per project by ``cde_recommender.generate_cde_meta``
         (canonical: description, semantic_type, recommended).
      2. The older ``semantic_glossary`` from the Data Glossary tab, if the
         user generated it before opening Data Profiling.

    Returns ``None`` when neither exists — downstream scorers degrade to
    their disabled state and the UI nudges the user to run the CDE picker.

    **Important fingerprint detail**: the CDE recommender writes its cache
    keyed on the full dataset's column set (``sess.df.columns``), not on
    whatever subset the steward later picks for analytical scope. Computing
    the fingerprint from the scoped frame here would produce a fingerprint
    mismatch every time the scope narrows, falsely invalidating a perfectly
    good classification. So we always fingerprint against the full schema.
    """
    if sess.active_project_id:
        # Fingerprint by the FULL dataset columns to match how the recommender
        # writes the cache — narrowing scope on Load Data shouldn't invalidate
        # the AI's per-column classification, only filter which rows we score.
        full_cols = (
            [str(c) for c in sess.df.columns]
            if sess.df is not None else [str(c) for c in df.columns]
        )
        cached = _load_cde_meta(sess.active_project_id, _cde_fingerprint(full_cols))
        if cached:
            return cached
    sg = getattr(sess, "semantic_glossary", None)
    if isinstance(sg, dict):
        return sg
    if isinstance(sg, list):
        return {
            (e.get("column") or e.get("name") or ""): e
            for e in sg
            if isinstance(e, dict)
        }
    return None


def _resolve_project_context(sess: SessionData, db: Session) -> Dict[str, Any]:
    """Compact master-data context for the current session's project.

    Includes ``system_id``, ``stream_id``, and the behavioural flags
    (``identifier_repeats_expected``, ``is_entity_master``) that
    downstream scorers and the rule generator key off of.
    """
    project = None
    if sess.active_project_id and sess.user and sess.user.get("username"):
        project = (
            db.query(Project)
            .filter(
                Project.id == sess.active_project_id,
                Project.user_username == sess.user["username"],
            )
            .one_or_none()
        )
    return build_project_context(project)


def _resolve_cross_field_rules(sess: SessionData, df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Cross-field rule violations seeded from generated AI rules.

    Reads rules whose Dimension contains "cross"; their ``Issues Found``
    counts feed the Accuracy scorer.
    """
    out: List[Dict[str, Any]] = []
    ai_rules = getattr(sess, "ai_validation_rules", None)
    if isinstance(ai_rules, pd.DataFrame) and not ai_rules.empty:
        cf = ai_rules[ai_rules.get("Dimension", "").astype(str).str.lower().str.contains("cross", na=False)]
        for _, row in cf.iterrows():
            out.append({
                "rule": row.get("Data Quality Rule") or row.get("Rule") or "",
                "issues_found": int(row.get("Issues Found", 0) or 0),
                "rows_evaluated": int(len(df) or 1),
            })
    return out


@router.get("/executive-summary")
def executive_summary(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """DAMA-aligned scorecard: 6 dimensions + key stats + remediation actions.

    Designed for the first tab of Data Profiling — a 30-second read of
    where the data is sick. The scorer is fully AI-driven: per-column
    classification flows from ``cde_meta`` produced by the CDE picker,
    and master-data semantics (e.g. "identifier repetition is expected
    for material masters") flow from the project's stream.
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    cross_field_rules = _resolve_cross_field_rules(sess, df)
    return compute_executive_summary(
        df,
        glossary=glossary,
        cross_field_rules=cross_field_rules,
        project_context=project_context,
    )


@router.get("/completeness")
def completeness(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """Per-field fill-rate analysis (DAMA Completeness, reference Sheet 1).

    Returns bucket summary + a sortable per-field table. Each field is
    tagged with its AI-assigned ``semantic_type`` and CDE flag so the
    picker UI can let stewards filter to "blanks on CDEs only".
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    return compute_completeness_report(df, glossary=glossary, project_context=project_context)


@router.get("/validation")
def validation(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """Per-attribute format Validation report (DAMA Validation, ref Sheet 2).

    For every column the AI tagged with a known semantic_type (PAN /
    GSTIN / Email / postal / ISO country / etc.), runs the canonical
    regex against the actual values and returns valid / invalid / blank
    counts plus up to 10 sample invalid rows.
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    result = compute_validation_report(df, glossary=glossary, project_context=project_context)
    result["needs_classification"] = glossary is None
    return result


@router.get("/uniqueness")
def uniqueness(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """DAMA Uniqueness deep-dive (ref Sheet 3).

    Returns four sections: record overview, composite-key duplicates,
    shared-identifier risk (same PAN / GSTIN across multiple entity
    rows), and per-column uniqueness rollup. Severity language adapts
    to master-data stream — repetition is informational for Material /
    GL / Cost Centre joined views, high-risk for Customer / Vendor /
    Employee entity masters.
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    result = compute_uniqueness_report(df, glossary=glossary, project_context=project_context)
    # Signal to the frontend that the AI hasn't classified columns yet —
    # tells the drill-down to auto-trigger regeneration before giving up.
    result["needs_classification"] = glossary is None
    return result


@router.get("/standardisation")
def standardisation(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """DAMA Standardisation deep-dive (ref Sheet 4).

    Case-pattern analysis per text column, fuzzy spelling-variant
    clusters within a column, and whitespace / control-character
    issues. Identifier-typed columns are excluded (their format is
    Validation's territory).
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    return compute_standardisation_report(df, glossary=glossary, project_context=project_context)


@router.get("/accuracy")
def accuracy(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """DAMA Accuracy deep-dive (ref Sheet 5).

    Per-rule pass / fail rollup of generated cross-field rules, with
    sample failing examples and the underlying validation expression.
    Returns ``needs_rules: true`` when no cross-field rules exist —
    the frontend uses that to render a one-click "Run Rule Generator"
    CTA instead of an empty table.
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    return compute_accuracy_report(
        df,
        ai_validation_rules=getattr(sess, "ai_validation_rules", None),
        glossary=glossary,
        project_context=project_context,
    )


@router.get("/quality-dashboard")
def quality_dashboard(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """Consolidated payload for the Data Quality Dashboard page.

    Returns KPI counts, the six dimension scores, threshold-category
    distribution, semantic-type distribution, per-dimension rule counts,
    and the per-field score table — everything the dashboard renders in
    one round-trip. All numbers flow from the existing scorers + cached
    AI classification, so the dashboard never disagrees with the
    profiling pages.
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    cross_field_rules = _resolve_cross_field_rules(sess, df)
    exec_summary = compute_executive_summary(
        df, glossary=glossary,
        cross_field_rules=cross_field_rules,
        project_context=project_context,
    )
    # Pull the generated rules dataframe so dashboard rule counts match
    # what the Rule Generator page shows (e.g. 108 of 108 rules) rather
    # than being approximated from "fields where a dimension applies".
    ai_rules_df = getattr(sess, "ai_validation_rules", None)
    return compute_quality_dashboard(
        df,
        glossary=glossary,
        executive_summary=exec_summary,
        cross_field_rules=cross_field_rules,
        project_context=project_context,
        ai_rules_df=ai_rules_df,
    )


@router.get("/timeliness")
def timeliness(
    sess: SessionData = Depends(require_dataframe),
    db: Session = Depends(get_db),
) -> dict:
    """DAMA Timeliness deep-dive.

    Per-datetime-column analysis: populated / blank counts, oldest /
    newest values, future-dated and very-old rows with samples, and
    a per-column timeliness rate. Empty when the dataset has no
    datetime columns — Timeliness is the only dimension that can
    legitimately be N/A.
    """
    df = scoped_dataframe(sess)
    glossary = _resolve_glossary(sess, df)
    project_context = _resolve_project_context(sess, db)
    return compute_timeliness_report(df, glossary=glossary, project_context=project_context)


# ---------- Overview chart data -----------------------------------------

@router.get("/overview")
def overview(sess: SessionData = Depends(require_dataframe)) -> dict:
    df = scoped_dataframe(sess)
    profiles = _ensure_profiles(sess)
    pdf = _profile_df(df, profiles)

    # Sorted slices used by the React Plotly charts.
    non_null_sorted = pdf.sort_values("Non-Null Count", ascending=True).tail(15)
    head15 = pdf.head(15)
    unique_sorted = pdf.sort_values("Unique Count", ascending=False).head(15)

    # Risk-level distribution for radar + donut.
    risk_counts = pdf["Risk Level"].value_counts().to_dict()
    avg_lengths = {
        "Min Length": float(pdf["Min Length"].mean() or 0),
        "Avg Length": float(pdf["Avg Length"].mean() or 0),
        "Max Length": float(pdf["Max Length"].mean() or 0),
    }

    # Data Type donut categories: Numeric / DateTime / Text / Other
    def _type_bucket(t: str) -> str:
        t = str(t)
        if any(x in t for x in ["int", "float"]):
            return "Numeric"
        if "date" in t.lower():
            return "DateTime"
        if "object" in t:
            return "Text"
        return "Other"
    type_counts = pdf["Data Type"].apply(_type_bucket).value_counts().to_dict()

    # Quality + Duplicate Risk gauge values
    quality_scores: List[float] = []
    for _, row in pdf.iterrows():
        comp = 100 - row["Null Percentage"]
        uniq = (min(100.0, row["Unique Percentage"] * 1.2)
                if row["Unique Percentage"] < 100 else 90.0)
        risk_penalty = row["Risk Score"]
        quality_scores.append(comp * 0.5 + uniq * 0.3 + (100 - risk_penalty) * 0.2)
    overall_quality = float(np.mean(quality_scores)) if quality_scores else 0.0
    duplicate_cols = int((pdf["Duplicate Count"] > 0).sum())
    dup_risk = (duplicate_cols / max(1, len(pdf))) * 100

    # Detailed table rows
    detail = pdf.to_dict(orient="records")

    return {
        "non_null_sorted": non_null_sorted.to_dict(orient="records"),
        "stack_15": head15[["Column Name", "Non-Null Count", "Null Count"]].to_dict(orient="records"),
        "unique_top15": unique_sorted.to_dict(orient="records"),
        "unique_vs_dup_15": head15[["Column Name", "Unique Count", "Duplicate Count"]].to_dict(orient="records"),
        "risk_trend": pdf[["Column Name", "Risk Score"]].to_dict(orient="records"),
        "null_pct_trend": pdf[["Column Name", "Null Percentage"]].to_dict(orient="records"),
        "scatter_unique_null": pdf[["Column Name", "Unique Percentage", "Null Percentage",
                                     "Duplicate Count", "Risk Score"]].to_dict(orient="records"),
        "risk_heatmap": pdf[["Column Name", "Risk Score"]].head(20).to_dict(orient="records"),
        "risk_radar": [{"label": k, "value": int(v)} for k, v in risk_counts.items()],
        "length_radar": [{"label": k, "value": float(v)} for k, v in avg_lengths.items()],
        "type_donut": [{"label": k, "value": int(v)} for k, v in type_counts.items()],
        "risk_donut": [{"label": k, "value": int(v)} for k, v in risk_counts.items()],
        "quality_gauge": round(overall_quality, 1),
        "duplicate_risk_gauge": round(dup_risk, 1),
        "scatter_unique_dup": pdf[["Column Name", "Unique Count", "Duplicate Count",
                                    "Risk Level", "Risk Score", "Null Percentage"]].to_dict(orient="records"),
        "detail_table": detail,
    }


# ---------- Correlation --------------------------------------------------

@router.get("/correlation")
def correlation(method: str = Query("pearson", regex="^(pearson|spearman)$"),
                sess: SessionData = Depends(require_dataframe)) -> dict:
    df = scoped_dataframe(sess)
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    if len(numeric_cols) < 2:
        return {"columns": [], "matrix": [], "high_pairs": []}
    corr = df[numeric_cols].corr(method=method).fillna(0.0)
    matrix = corr.round(3).values.tolist()
    high_pairs: List[Dict[str, Any]] = []
    cols = corr.columns.tolist()
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            v = float(corr.iloc[i, j])
            if abs(v) >= 0.8:
                high_pairs.append({"Column A": cols[i], "Column B": cols[j],
                                    "Correlation": round(v, 3)})
    return {"columns": cols, "matrix": matrix, "high_pairs": high_pairs}


# ---------- Column profile cards ----------------------------------------

@router.get("/columns")
def columns(sess: SessionData = Depends(require_dataframe)) -> List[Dict[str, Any]]:
    df = scoped_dataframe(sess)
    profiles = _ensure_profiles(sess)
    out: List[Dict[str, Any]] = []
    for col, p in profiles.items():
        dup_values_str = (get_duplicate_count_values(df, col, max_items=None)
                          if p.unique_count < p.total_rows else "")
        groups = (find_duplicate_groups(df, col)
                  if p.unique_count < p.total_rows else [])
        out.append({
            "column": col,
            "dtype": str(p.dtype),
            "total_rows": int(p.total_rows),
            "non_null_count": int(getattr(p, "non_null_count", p.total_rows - p.null_count)),
            "null_count": int(p.null_count),
            "null_percentage": float(p.null_percentage),
            "unique_count": int(p.unique_count),
            "duplicate_count": int(p.total_rows - p.unique_count),
            "unique_percentage": float(p.unique_percentage),
            "min_length": int(getattr(p, "min_length", 0) or 0),
            "max_length": int(getattr(p, "max_length", 0) or 0),
            "avg_length": float(getattr(p, "avg_length", 0) or 0),
            "risk_level": str(getattr(p, "risk_level", "Low")),
            "risk_score": int(getattr(p, "risk_score", 0) or 0),
            "duplicate_count_values": dup_values_str,
            "duplicate_groups": groups,
        })
    return out


# ---------- Match Rules --------------------------------------------------

@router.post("/match-rules")
def match_rules_endpoint(sess: SessionData = Depends(require_dataframe)) -> List[Dict[str, Any]]:
    profiles = _ensure_profiles(sess)
    return generate_match_rules(scoped_dataframe(sess), profiles)


# ---------- AI Rules -----------------------------------------------------

@router.get("/llm-status")
def llm_status() -> dict:
    missing = AzureOpenAIConfig.validate()
    return {
        "configured": not missing,
        "missing": missing,
        "deployment": AzureOpenAIConfig.AZURE_OPENAI_DEPLOYMENT,
        "max_rpm": AzureOpenAIConfig.MAX_REQUESTS_PER_MINUTE,
    }


@router.post("/ai-rules/generate")
def ai_rules_generate(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Run the unified DQ analysis (Excel client rules + AI per-column rules)."""
    profiles = _ensure_profiles(sess)
    detector = DynamicValidationDetector()

    if detector.ai_engine._init_warning:
        raise HTTPException(status_code=503, detail=detector.ai_engine._init_warning)

    file_path = sess.file_path
    sheet_name = getattr(sess, "sheet_name", None)

    progress_log: List[Dict[str, Any]] = []

    def cb(payload: Dict[str, Any]) -> None:
        progress_log.append(payload)

    unified_df = detector.generate_comprehensive_dq_rules(
        scoped_dataframe(sess), profiles, file_path=file_path, sheet_name=sheet_name,
        progress_cb=cb,
    )
    sess.ai_validation_rules = unified_df

    total = len(unified_df)
    client_count = int(unified_df["Source"].str.contains("Client", na=False).sum()) if total else 0
    ai_count = int(unified_df["Source"].str.contains("AI", na=False).sum()) if total else 0

    return {
        "ok": True,
        "total_rules": total,
        "client_rules": client_count,
        "ai_rules": ai_count,
        "rules": unified_df.to_dict(orient="records"),
        "progress": progress_log,
    }


@router.get("/ai-rules")
def ai_rules_get(sess: SessionData = Depends(require_dataframe)) -> dict:
    df = sess.ai_validation_rules
    if df is None or (isinstance(df, pd.DataFrame) and df.empty):
        return {"generated": False, "rules": []}
    return {"generated": True, "rules": df.to_dict(orient="records")}


@router.post("/ai-rules/clear")
def ai_rules_clear(sess: SessionData = Depends(require_dataframe)) -> dict:
    sess.ai_validation_rules = None
    return {"ok": True}


# ---------- Exports ------------------------------------------------------

@router.post("/export/excel")
def export_excel(sess: SessionData = Depends(require_dataframe)):
    profiles = _ensure_profiles(sess)
    unified = sess.ai_validation_rules if isinstance(sess.ai_validation_rules, pd.DataFrame) else None
    data, fname = build_excel_report(scoped_dataframe(sess), profiles, sess.filename, unified)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/export/json")
def export_json(sess: SessionData = Depends(require_dataframe)):
    profiles = _ensure_profiles(sess)
    data, fname = build_json_report(scoped_dataframe(sess), profiles, sess.filename)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/json",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


# ---------- Drift --------------------------------------------------------

class SaveBaselineBody(BaseModel):
    name: str


class DetectDriftBody(BaseModel):
    baseline_name: str
    null_threshold: float = 5.0
    unique_threshold: float = 10.0
    mean_std_threshold: float = 2.0


@router.post("/drift/save-baseline")
def drift_save(body: SaveBaselineBody, sess: SessionData = Depends(require_dataframe)) -> dict:
    profiles = _ensure_profiles(sess)
    if not body.name.strip():
        raise HTTPException(status_code=400, detail="Baseline name required")
    _save_baseline(body.name, scoped_dataframe(sess), profiles)
    return {"ok": True, "name": body.name}


@router.get("/drift/baselines")
def drift_list() -> List[Dict[str, str]]:
    return _list_baselines()


@router.delete("/drift/baselines/{name}")
def drift_delete(name: str) -> dict:
    ok = _delete_baseline(name)
    return {"ok": bool(ok)}


@router.post("/drift/detect")
def drift_detect(body: DetectDriftBody,
                 sess: SessionData = Depends(require_dataframe)) -> List[Dict[str, Any]]:
    profiles = _ensure_profiles(sess)
    baseline = _load_baseline(body.baseline_name)
    if not baseline:
        raise HTTPException(status_code=404, detail="Baseline not found")
    return _detect_drift(sess.df, profiles, baseline,
                          body.null_threshold, body.unique_threshold, body.mean_std_threshold)


# ---------- Semantic glossary --------------------------------------------


class GlossaryOverrideBody(BaseModel):
    semantic_type: Optional[str] = None
    display_name: Optional[str] = None
    description: Optional[str] = None
    format_hint: Optional[str] = None


def _build_glossary_client():
    from openai import AzureOpenAI
    return AzureOpenAI(
        api_version=AzureOpenAIConfig.AZURE_OPENAI_API_VERSION,
        azure_endpoint=AzureOpenAIConfig.AZURE_OPENAI_ENDPOINT,
        api_key=AzureOpenAIConfig.AZURE_OPENAI_KEY,
    )


@router.post("/semantic-glossary/generate")
def semantic_glossary_generate(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Run one batched LLM call to infer a semantic type for every in-scope column."""
    missing = AzureOpenAIConfig.validate()
    if missing:
        raise HTTPException(
            status_code=503,
            detail=f"Azure OpenAI not configured. Missing: {', '.join(missing)}",
        )

    df = scoped_dataframe(sess)
    if df is None or df.shape[1] == 0:
        raise HTTPException(
            status_code=400,
            detail="No columns are in scope. Select at least one Critical Data Element on Load Data.",
        )

    try:
        client = _build_glossary_client()
        glossary = generate_semantic_glossary(
            df, client, AzureOpenAIConfig.AZURE_OPENAI_DEPLOYMENT,
        )
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Glossary generation failed: {exc}")

    sess.semantic_glossary = glossary
    if sess.active_project_id:
        save_glossary(sess.active_project_id, glossary)
    return {
        "ok": True,
        "columns_in_scope": int(df.shape[1]),
        "entries": [glossary[c] for c in df.columns if c in glossary],
    }


@router.get("/semantic-glossary")
def semantic_glossary_get(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Return the stored glossary (or an empty one if not yet generated)."""
    if not sess.semantic_glossary:
        return {"generated": False, "entries": []}
    df = sess.df
    cols_in_df = [str(c) for c in df.columns] if df is not None else []
    ordered = [
        sess.semantic_glossary[c]
        for c in cols_in_df
        if c in sess.semantic_glossary
    ]
    return {"generated": True, "entries": ordered}


@router.put("/semantic-glossary/{column}")
def semantic_glossary_override(
    column: str,
    body: GlossaryOverrideBody,
    sess: SessionData = Depends(require_dataframe),
) -> dict:
    """Apply a manual override for a single column's glossary entry."""
    if sess.df is None or column not in [str(c) for c in sess.df.columns]:
        raise HTTPException(status_code=404, detail=f"Unknown column: {column}")

    glossary = sess.semantic_glossary or {}
    entry = dict(glossary.get(column, {
        "column": column,
        "semantic_type": "unknown",
        "display_name": column,
        "description": "",
        "format_hint": "",
        "confidence": 0.0,
        "source": "ai",
    }))

    for field_name, value in body.dict(exclude_none=True).items():
        entry[field_name] = value.strip() if isinstance(value, str) else value
    entry["source"] = "manual"
    entry["confidence"] = 1.0  # explicit user override

    glossary[column] = entry
    sess.semantic_glossary = glossary
    # Manual override invalidates dependent caches that may have used the
    # previous semantic type when generating rules.
    sess.ai_validation_rules = None
    if sess.active_project_id:
        save_glossary(sess.active_project_id, glossary)
    return {"ok": True, "entry": entry}


@router.post("/semantic-glossary/clear")
def semantic_glossary_clear(sess: SessionData = Depends(require_dataframe)) -> dict:
    sess.semantic_glossary = None
    if sess.active_project_id:
        save_glossary(sess.active_project_id, None)
    return {"ok": True}
