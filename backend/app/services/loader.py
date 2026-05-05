"""File loading helpers (CSV, Excel, Parquet, JSON, JSONL, Feather)."""
from __future__ import annotations

from pathlib import Path
from typing import List, Optional, Tuple

import pandas as pd


def load_dataframe(path: str, suffix: str, sheet_name: Optional[str] = None,
                   header_row: int = 0) -> Tuple[pd.DataFrame, Optional[List[str]], Optional[str]]:
    """Read a file into a DataFrame. Returns (df, sheet_names_or_None, selected_sheet_or_None)."""
    suffix = suffix.lower()
    if suffix in (".csv", ".txt"):
        return pd.read_csv(path, low_memory=False, header=header_row), None, None
    if suffix == ".tsv":
        return pd.read_csv(path, sep="\t", low_memory=False, header=header_row), None, None
    if suffix in (".xlsx", ".xls"):
        xls = pd.ExcelFile(path)
        sheets = xls.sheet_names
        target = sheet_name if sheet_name and sheet_name in sheets else sheets[0]
        return pd.read_excel(xls, sheet_name=target, header=header_row), sheets, target
    if suffix in (".parquet", ".pq"):
        return pd.read_parquet(path), None, None
    if suffix == ".json":
        return pd.read_json(path), None, None
    if suffix == ".jsonl":
        return pd.read_json(path, lines=True), None, None
    if suffix in (".feather", ".ftr"):
        return pd.read_feather(path), None, None
    raise ValueError(f"Unsupported file type: {suffix}")


def safe_records(df: pd.DataFrame, limit: int = 50) -> list:
    """Return JSON-safe records: NaN -> None, numpy scalars unwrapped."""
    head = df.head(limit).copy()
    head = head.where(pd.notnull(head), None)
    return head.astype(object).where(pd.notnull(head), None).to_dict(orient="records")
