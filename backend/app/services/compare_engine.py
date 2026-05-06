"""1:1 port of features/compare/ui.py helpers.

Functions ported (verbatim semantics):
- _count_modified_cells       (lines 247-271)
- _prepare_comparison_data    (lines 274-309)
- _style_changes              (lines 312-345)  → returns flag arrays instead of CSS

The React page renders the cell colours; the backend just emits the flags.
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional

import numpy as np
import pandas as pd


def count_modified_cells(orig_df: pd.DataFrame, curr_df: pd.DataFrame) -> int:
    """Verbatim port of _count_modified_cells.

    NaN == NaN is treated as equal. Compares only common columns and overlapping rows.
    """
    common_cols = list(set(orig_df.columns) & set(curr_df.columns))
    if not common_cols:
        return 0
    min_rows = min(len(orig_df), len(curr_df))
    if min_rows == 0:
        return 0
    orig_slice = orig_df[common_cols].iloc[:min_rows]
    curr_slice = curr_df[common_cols].iloc[:min_rows]
    neq = orig_slice.ne(curr_slice)
    both_nan = orig_slice.isna() & curr_slice.isna()
    modified = neq & ~both_nan
    return int(modified.sum().sum())


def stats(orig_df: pd.DataFrame, curr_df: pd.DataFrame) -> Dict[str, Any]:
    """Top stat row used by the Streamlit page header."""
    return {
        "original_rows": int(len(orig_df)),
        "modified_rows": int(len(curr_df)),
        "row_change": int(len(curr_df) - len(orig_df)),
        "original_columns": int(len(orig_df.columns)),
        "modified_columns": int(len(curr_df.columns)),
        "column_change": int(len(curr_df.columns) - len(orig_df.columns)),
        "modified_cells": count_modified_cells(orig_df, curr_df),
        "common_columns": sorted(set(orig_df.columns) & set(curr_df.columns)),
        "columns_added": [c for c in curr_df.columns if c not in orig_df.columns],
        "columns_removed": [c for c in orig_df.columns if c not in curr_df.columns],
    }


def _safe(v: Any) -> Any:
    """JSON-safe scalar.

    Handles three classes of value that FastAPI's default encoder rejects:
      - NaN / NaT / None (any nullable kind) → ``None``.
      - numpy scalars (np.int64, np.float64, np.bool_, etc.) → Python scalars.
      - pandas Timestamp / Timedelta → ISO 8601 string.
    Everything else passes through.
    """
    if v is None:
        return None
    # pd.isna handles float('nan'), np.nan, pd.NA, pd.NaT — but only for
    # scalar-shaped values, so guard against arrays/lists.
    try:
        if pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, (pd.Timestamp, pd.Timedelta)):
        return v.isoformat()
    if isinstance(v, np.generic):
        return v.item()
    return v


def cell_diff(
    orig_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    columns: List[str],
    start_row: int,
    num_rows: int,
) -> Dict[str, Any]:
    """Windowed cell-level diff matching _prepare_comparison_data + _style_changes.

    Returns:
      {
        rows: [
          {
            row_index: int,
            original: {col: value, ...} | null,
            modified: {col: value, ...} | null,
            cell_flags: {col: 'modified'|'added'|'removed'|None},
            row_status: 'normal'|'added'|'removed',
          },
          ...
        ],
        modified_cells: int,
        added_rows: int,
        removed_rows: int,
        changes_found: bool,
      }
    """
    end_row = start_row + num_rows
    orig_n = len(orig_df)
    curr_n = len(curr_df)
    end_orig = min(end_row, orig_n)
    end_curr = min(end_row, curr_n)

    rows: List[Dict[str, Any]] = []
    modified_cells = 0

    # iterate over the union of indices in [start_row, end_row)
    last_idx = max(end_orig, end_curr)
    for idx in range(start_row, last_idx):
        orig_row: Optional[Dict[str, Any]] = None
        curr_row: Optional[Dict[str, Any]] = None
        if idx < orig_n:
            orig_row = {c: _safe(orig_df.iloc[idx][c]) for c in columns if c in orig_df.columns}
        if idx < curr_n:
            curr_row = {c: _safe(curr_df.iloc[idx][c]) for c in columns if c in curr_df.columns}

        # Row status
        if orig_row is None and curr_row is not None:
            row_status = "added"
        elif orig_row is not None and curr_row is None:
            row_status = "removed"
        else:
            row_status = "normal"

        # Per-cell flags
        cell_flags: Dict[str, Optional[str]] = {}
        if row_status == "added":
            for c in columns:
                cell_flags[c] = "added"
        elif row_status == "removed":
            for c in columns:
                cell_flags[c] = "removed"
        else:
            for c in columns:
                ov = orig_row.get(c) if orig_row else None
                cv = curr_row.get(c) if curr_row else None
                if ov is None and cv is None:
                    cell_flags[c] = None
                elif ov != cv:
                    cell_flags[c] = "modified"
                    modified_cells += 1
                else:
                    cell_flags[c] = None

        rows.append({
            "row_index": idx,
            "original": orig_row,
            "modified": curr_row,
            "cell_flags": cell_flags,
            "row_status": row_status,
        })

    added_rows = max(0, end_curr - orig_n) if end_row > orig_n else 0
    removed_rows = max(0, end_orig - curr_n) if end_row > curr_n else 0
    changes_found = modified_cells > 0 or added_rows > 0 or removed_rows > 0

    return {
        "rows": rows,
        "modified_cells": int(modified_cells),
        "added_rows": int(added_rows),
        "removed_rows": int(removed_rows),
        "changes_found": bool(changes_found),
    }
