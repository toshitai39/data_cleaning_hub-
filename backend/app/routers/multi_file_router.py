"""Multi-File comparison endpoint — 1:1 parity with features/multi_file/ui.py.

Reads multiple uploaded files, computes:
  - schema_rows: union-of-columns × file matrix with dtype or "MISSING"
  - stats_rows: per-file Rows / Columns / Missing Cells / Missing %
  - common_columns: intersection of column names across all files
  - null_chart_data: long-form Null % by (Column, File) for the grouped bar chart
"""
from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any, Dict, List

import pandas as pd
from fastapi import APIRouter, File, HTTPException, UploadFile

router = APIRouter(prefix="/multi-file", tags=["multi-file"])


def _read_upload(file_path: str, filename: str) -> pd.DataFrame:
    """1:1 port of _read_upload(uploaded_file)."""
    name = filename.lower()
    if name.endswith((".csv", ".txt")):
        return pd.read_csv(file_path, low_memory=False)
    if name.endswith(".tsv"):
        return pd.read_csv(file_path, sep="\t", low_memory=False)
    if name.endswith((".xlsx", ".xls")):
        return pd.read_excel(file_path)
    if name.endswith((".parquet", ".pq")):
        return pd.read_parquet(file_path)
    if name.endswith(".json"):
        return pd.read_json(file_path)
    raise ValueError(f"Unsupported file type: {filename}")


@router.post("/compare")
async def compare(files: List[UploadFile] = File(...)) -> Dict[str, Any]:
    if len(files) < 2:
        raise HTTPException(status_code=400, detail="Upload at least 2 files to compare.")

    parsed: Dict[str, pd.DataFrame] = {}
    errors: List[Dict[str, str]] = []

    for f in files:
        suffix = Path(f.filename or "data").suffix.lower()
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            content = await f.read()
            tmp.write(content)
            tmp_path = tmp.name
        try:
            df = _read_upload(tmp_path, f.filename or "")
            parsed[f.filename] = df
        except Exception as exc:
            errors.append({"file": f.filename, "error": str(exc)})

    if len(parsed) < 2:
        raise HTTPException(
            status_code=400,
            detail=f"Need at least 2 readable files. Errors: {errors}",
        )

    # --- schema_rows: union of columns × files ---------------------------
    all_cols_set: set = set()
    for df in parsed.values():
        all_cols_set.update(df.columns.tolist())

    schema_rows: List[Dict[str, Any]] = []
    for col in sorted(all_cols_set):
        row: Dict[str, Any] = {"Column": str(col)}
        for fname, df in parsed.items():
            row[fname] = str(df[col].dtype) if col in df.columns else "MISSING"
        schema_rows.append(row)

    # --- stats_rows: per-file metrics ------------------------------------
    stats_rows: List[Dict[str, Any]] = []
    for fname, df in parsed.items():
        total_cells = len(df) * len(df.columns)
        missing = int(df.isnull().sum().sum())
        stats_rows.append({
            "File": fname,
            "Rows": int(len(df)),
            "Columns": int(len(df.columns)),
            "Missing Cells": missing,
            "Missing %": round((missing / total_cells * 100), 2) if total_cells else 0,
        })

    # --- common columns + null chart data --------------------------------
    common_columns = sorted(all_cols_set.intersection(*[set(df.columns) for df in parsed.values()]))
    null_chart_data: List[Dict[str, Any]] = []
    for col in common_columns:
        for fname, df in parsed.items():
            null_pct = round(df[col].isnull().sum() / max(len(df), 1) * 100, 2)
            null_chart_data.append({"Column": str(col), "File": fname, "Null %": float(null_pct)})

    return {
        "files": list(parsed.keys()),
        "schema_rows": schema_rows,
        "stats_rows": stats_rows,
        "common_columns": [str(c) for c in common_columns],
        "null_chart_data": null_chart_data,
        "errors": errors,
    }
