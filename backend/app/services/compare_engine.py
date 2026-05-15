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


def _aligned_common(orig_df: pd.DataFrame, curr_df: pd.DataFrame
                    ) -> tuple[pd.DataFrame, pd.DataFrame, list[str]]:
    """Return (orig_aligned, curr_aligned, common_cols) restricted to the
    rows that exist in BOTH frames by pandas index label.

    This is the core correctness fix: identity-based alignment instead
    of positional alignment. When cleansing drops rows from the middle
    of the dataset, the surviving rows in curr_df keep their original
    index labels (apply_column_rules no longer resets the index), so
    intersecting indices gives us a clean "matched rows" view.

    Rows that exist only in orig_df → REMOVED.
    Rows that exist only in curr_df → ADDED (rare in cleansing flow).
    Rows in both index sets → candidates for cell-level diff.
    """
    common_cols = sorted(set(orig_df.columns) & set(curr_df.columns))
    if not common_cols:
        return orig_df.iloc[0:0], curr_df.iloc[0:0], []
    common_idx = orig_df.index.intersection(curr_df.index)
    orig_aligned = orig_df.loc[common_idx, common_cols]
    curr_aligned = curr_df.loc[common_idx, common_cols]
    return orig_aligned, curr_aligned, common_cols


def count_modified_cells(orig_df: pd.DataFrame, curr_df: pd.DataFrame) -> int:
    """Count cells that differ between orig and curr — aligned by INDEX
    (row identity), not by position.

    NaN == NaN is treated as equal. Removed rows don't contribute to the
    "modified" count — they're tracked separately as ``row_change``.
    """
    orig_aligned, curr_aligned, common_cols = _aligned_common(orig_df, curr_df)
    if orig_aligned.empty or not common_cols:
        return 0
    neq = orig_aligned.ne(curr_aligned)
    both_nan = orig_aligned.isna() & curr_aligned.isna()
    modified = neq & ~both_nan
    return int(modified.sum().sum())


def _detect_stale_state(orig_df: pd.DataFrame, curr_df: pd.DataFrame) -> bool:
    """Detect a pre-fix session where row identity has been destroyed.

    Symptom: curr_df is smaller than orig_df, BUT curr_df.index is a
    contiguous range starting at 0 (i.e., reset_index was applied at
    some point). When that's true, we can no longer tell which original
    rows survived — the diff becomes meaningless and would mislead the
    steward into thinking surviving rows were "Modified" when really
    different original rows had been dropped. We surface this as a
    warning flag so the UI can prompt the user to Reset to Original.
    """
    if curr_df is None or orig_df is None or curr_df.empty:
        return False
    if len(curr_df) >= len(orig_df):
        return False
    try:
        idx = curr_df.index
        # Contiguous 0..M-1 → reset_index was applied somewhere upstream.
        is_contiguous_reset = (
            isinstance(idx, pd.RangeIndex)
            or (idx.is_monotonic_increasing
                and idx[0] == 0
                and idx[-1] == len(curr_df) - 1
                and len(idx) == len(set(idx.tolist())))
        )
        return bool(is_contiguous_reset)
    except Exception:
        return False


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
        "stale_state": _detect_stale_state(orig_df, curr_df),
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


def per_column_changes(
    orig_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    sample_size: int = 3,
) -> Dict[str, Any]:
    """Per-CDE change ledger using INDEX-based row identity.

    Rows that exist only in orig (i.e. dropped by cleansing) are NOT
    counted as cell modifications — they're separately surfaced as
    ``rows_removed``. This was the bug: positional alignment compared
    surviving rows against unrelated original rows, making every
    surviving row look "Modified" or "Backfilled". Identity alignment
    fixes it: a row only contributes to per-column changes if it
    survived into the current view.
    """
    orig_aligned, curr_aligned, common_cols = _aligned_common(orig_df, curr_df)
    rows_removed = int(len(orig_df) - len(orig_df.index.intersection(curr_df.index)))
    rows_added = int(len(curr_df) - len(orig_df.index.intersection(curr_df.index)))
    stale = _detect_stale_state(orig_df, curr_df)

    if not common_cols or orig_aligned.empty:
        return {
            "columns": [],
            "rows_added":   max(0, rows_added),
            "rows_removed": max(0, rows_removed),
            "total_modified_cells": 0,
            "cdes_touched": 0,
            "stale_state": stale,
        }

    per_col: List[Dict[str, Any]] = []
    total_modified = 0

    for col in common_cols:
        os = orig_aligned[col]
        cs = curr_aligned[col]
        # True-difference mask: NaN == NaN treated as equal.
        diff_mask = os.ne(cs) & ~(os.isna() & cs.isna())
        changed = int(diff_mask.sum())
        if changed == 0:
            continue
        total_modified += changed

        # Sub-classify the dominant change type for this column.
        nulled = int((cs.isna() & ~os.isna()).sum())
        filled = int((os.isna() & ~cs.isna()).sum())
        try:
            same_when_folded = (os.astype(str).str.lower() == cs.astype(str).str.lower())
            different_raw = (os.astype(str) != cs.astype(str))
            std = int((diff_mask & same_when_folded & different_raw).sum())
        except Exception:
            std = 0

        if nulled == changed and changed > 0:
            change_type = "Cleared"
        elif filled == changed and changed > 0:
            change_type = "Backfilled"
        elif std == changed and changed > 0:
            change_type = "Standardised"
        elif std > changed / 2:
            change_type = "Standardised (mostly)"
        else:
            change_type = "Modified"

        # Sample up to N representative before→after pairs.
        sample_labels = diff_mask[diff_mask].index[:sample_size]
        samples = []
        for label in sample_labels:
            samples.append({
                "row": int(label) if isinstance(label, (int, np.integer)) else str(label),
                "before": _safe(os.loc[label]),
                "after":  _safe(cs.loc[label]),
            })

        per_col.append({
            "column": col,
            "changed": changed,
            "nulled": nulled,
            "filled": filled,
            "standardised": std,
            "change_type": change_type,
            "samples": samples,
        })

    per_col.sort(key=lambda x: -x["changed"])

    return {
        "columns": per_col,
        "rows_added":   max(0, rows_added),
        "rows_removed": max(0, rows_removed),
        "total_modified_cells": int(total_modified),
        "cdes_touched": len(per_col),
        "stale_state": stale,
    }


def cell_diff(
    orig_df: pd.DataFrame,
    curr_df: pd.DataFrame,
    columns: List[str],
    start_row: int,
    num_rows: int,
) -> Dict[str, Any]:
    """Windowed cell-level diff using INDEX-based row identity.

    Walks the **union of index labels** from both frames, in sorted
    order, over the window [start_row, start_row+num_rows). For each
    label:
      - In orig only  → row_status = "removed" (cleansing dropped it)
      - In curr only  → row_status = "added"
      - In both       → cell-level comparison, flag cells that differ

    Critical correctness fix: the old implementation used ``.iloc[i]``
    on each frame, which is positional. When the cleansing engine
    drops rows from the middle of the data and resets the index,
    position 0 in curr_df might be a totally different row from
    position 0 in orig_df. The diff then showed unrelated rows as
    "Modified" — the bug the user just reported.
    """
    orig_idx = set(orig_df.index.tolist())
    curr_idx = set(curr_df.index.tolist())
    union_idx = sorted(orig_idx | curr_idx,
                       key=lambda x: (isinstance(x, str), x))
    end = start_row + num_rows
    window = union_idx[start_row:end]

    # Restrict to columns that exist in at least one side.
    use_cols = [c for c in columns if c in orig_df.columns or c in curr_df.columns]

    rows: List[Dict[str, Any]] = []
    modified_cells = 0
    added_rows = 0
    removed_rows = 0

    for label in window:
        in_orig = label in orig_idx
        in_curr = label in curr_idx
        orig_row: Optional[Dict[str, Any]] = None
        curr_row: Optional[Dict[str, Any]] = None
        if in_orig:
            orig_row = {
                c: _safe(orig_df.at[label, c])
                for c in use_cols if c in orig_df.columns
            }
        if in_curr:
            curr_row = {
                c: _safe(curr_df.at[label, c])
                for c in use_cols if c in curr_df.columns
            }

        if in_orig and not in_curr:
            row_status = "removed"
            removed_rows += 1
        elif in_curr and not in_orig:
            row_status = "added"
            added_rows += 1
        else:
            row_status = "normal"

        cell_flags: Dict[str, Optional[str]] = {}
        if row_status == "removed":
            for c in use_cols:
                cell_flags[c] = "removed"
        elif row_status == "added":
            for c in use_cols:
                cell_flags[c] = "added"
        else:
            for c in use_cols:
                ov = orig_row.get(c) if orig_row else None
                cv = curr_row.get(c) if curr_row else None
                # NaN treated as equal to NaN.
                ov_na = ov is None or (isinstance(ov, float) and ov != ov)
                cv_na = cv is None or (isinstance(cv, float) and cv != cv)
                if ov_na and cv_na:
                    cell_flags[c] = None
                elif ov != cv:
                    cell_flags[c] = "modified"
                    modified_cells += 1
                else:
                    cell_flags[c] = None

        rows.append({
            "row_index": int(label) if isinstance(label, (int, np.integer)) else str(label),
            "original": orig_row,
            "modified": curr_row,
            "cell_flags": cell_flags,
            "row_status": row_status,
        })

    changes_found = modified_cells > 0 or added_rows > 0 or removed_rows > 0
    return {
        "rows": rows,
        "modified_cells": int(modified_cells),
        "added_rows":     int(added_rows),
        "removed_rows":   int(removed_rows),
        "changes_found":  bool(changes_found),
    }
