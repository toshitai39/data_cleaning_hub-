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

from core.drift_detector import (
    delete_baseline as _delete_baseline,
    detect_drift as _detect_drift,
    list_baselines as _list_baselines,
    load_baseline as _load_baseline,
    save_baseline as _save_baseline,
)
from core.profiler import DataProfilerEngine

from ..deps import require_dataframe
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
from ..session_store import SessionData

router = APIRouter(prefix="/profile", tags=["profile"])


# ---------- helpers ------------------------------------------------------

def _ensure_profiles(sess: SessionData) -> Dict[str, Any]:
    if not sess.column_profiles:
        engine = DataProfilerEngine(sess.df, sess.filename)
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
def run_profile(sess: SessionData = Depends(require_dataframe)) -> dict:
    """Run profiler and persist column_profiles + quality_report on session."""
    df = sess.df
    engine = DataProfilerEngine(df, sess.filename)
    try:
        engine.profile(fast_mode=True)
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Profiling failed: {exc}")
    sess.column_profiles = dict(engine.column_profiles)
    sess.quality_report = engine.quality_report
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
    df = sess.df
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
    df = sess.df
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


# ---------- Overview chart data -----------------------------------------

@router.get("/overview")
def overview(sess: SessionData = Depends(require_dataframe)) -> dict:
    df = sess.df
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
    df = sess.df
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
    df = sess.df
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
    return generate_match_rules(sess.df, profiles)


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
        sess.df, profiles, file_path=file_path, sheet_name=sheet_name,
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
    data, fname = build_excel_report(sess.df, profiles, sess.filename, unified)
    return StreamingResponse(
        io.BytesIO(data),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": f'attachment; filename="{fname}"'},
    )


@router.post("/export/json")
def export_json(sess: SessionData = Depends(require_dataframe)):
    profiles = _ensure_profiles(sess)
    data, fname = build_json_report(sess.df, profiles, sess.filename)
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
    _save_baseline(body.name, sess.df, profiles)
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
