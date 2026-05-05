"""1:1 port of features/duplicates/ui.py + transform_remove_fuzzy_group.

Wraps DataProfilerEngine.find_exact_duplicates / find_fuzzy_duplicates /
find_combined_duplicates and ports the transform_remove_fuzzy_group strategies
(keep_first / keep_last / keep_selected / keep_multiple / merge) without the
Streamlit st.session_state coupling.
"""
from __future__ import annotations

import io
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from core.profiler import DataProfilerEngine

from ..session_store import SessionData


# ---------- helpers ------------------------------------------------------

def group_to_summary(group: Any) -> Dict[str, Any]:
    """Mirror the Streamlit summary_data row."""
    similarity = group.similarity_score or 100
    rep_str = str(group.representative_value) if group.representative_value is not None else ""
    if len(rep_str) > 50:
        rep_str = rep_str[:50] + "..."
    return {
        "group_id": int(group.group_id),
        "rows": int(len(group.indices)),
        "similarity": float(similarity),
        "match_type": str(group.match_type),
        "key_columns": list(group.key_columns) if group.key_columns else [],
        "representative": rep_str,
    }


def group_to_detail(group: Any) -> Dict[str, Any]:
    """Full group detail for the per-group expanded view."""
    sample = group.values[:50] if group.values else []
    cleaned = []
    for row in sample:
        clean = {}
        for k, v in row.items():
            if pd.isna(v) if not isinstance(v, (list, dict)) else False:
                clean[k] = None
            else:
                clean[k] = v
        cleaned.append(clean)
    return {
        "group_id": int(group.group_id),
        "rows": int(len(group.indices)),
        "indices": list(group.indices),
        "similarity": float(group.similarity_score or 100),
        "match_type": str(group.match_type),
        "key_columns": list(group.key_columns) if group.key_columns else [],
        "values": cleaned,
    }


# ---------- scan ---------------------------------------------------------

def scan_exact(sess: SessionData, subset: Optional[List[str]]) -> List[Any]:
    engine = DataProfilerEngine(sess.df, sess.filename)
    groups = engine.find_exact_duplicates(subset=subset if subset else None)
    sess.exact_duplicates = list(groups)
    sess.duplicates_meta["exact"] = {"subset": subset or []}
    return groups


def scan_fuzzy(sess: SessionData, columns: List[str], threshold: float, algorithm: str) -> List[Any]:
    engine = DataProfilerEngine(sess.df, sess.filename)
    groups = engine.find_fuzzy_duplicates(columns, threshold, algorithm)
    sess.fuzzy_duplicates = list(groups)
    sess.duplicates_meta["fuzzy"] = {"columns": columns, "threshold": threshold, "algorithm": algorithm}
    return groups


def scan_combined(sess: SessionData, exact_cols: List[str], fuzzy_cols: List[str],
                  threshold: float, algorithm: str) -> List[Any]:
    engine = DataProfilerEngine(sess.df, sess.filename)
    groups = engine.find_combined_duplicates(exact_cols, fuzzy_cols, threshold, algorithm)
    sess.combined_duplicates = list(groups)
    sess.duplicates_meta["combined"] = {
        "exact_cols": exact_cols, "fuzzy_cols": fuzzy_cols,
        "threshold": threshold, "algorithm": algorithm,
    }
    return groups


def get_groups(sess: SessionData, dup_type: str) -> List[Any]:
    if dup_type == "exact":
        return sess.exact_duplicates or []
    if dup_type == "fuzzy":
        return sess.fuzzy_duplicates or []
    if dup_type == "combined":
        return sess.combined_duplicates or []
    return []


def find_group(sess: SessionData, dup_type: str, group_id: int) -> Optional[Any]:
    for g in get_groups(sess, dup_type):
        if int(g.group_id) == int(group_id):
            return g
    return None


# ---------- removal strategies (port of transform_remove_fuzzy_group) ---

def remove_fuzzy_group(
    sess: SessionData,
    group_indices: List[int],
    strategy: str = "keep_first",
    selected_index: Optional[int] = None,
    selected_indices: Optional[List[int]] = None,
) -> Tuple[int, str]:
    """1:1 port — applies removal to sess.df and logs to fixes_applied.

    Returns (rows_removed, strategy_msg).
    """
    df = sess.df
    rows_removed = 0
    strategy_msg = ""

    if strategy == "keep_first":
        drop_indices = group_indices[1:]
        strategy_msg = "kept first"
    elif strategy == "keep_last":
        drop_indices = group_indices[:-1]
        strategy_msg = "kept last"
    elif strategy == "keep_selected":
        if selected_index is None or selected_index < 0 or selected_index >= len(group_indices):
            drop_indices = group_indices[1:]
            strategy_msg = "kept first (fallback)"
        else:
            drop_indices = [idx for i, idx in enumerate(group_indices) if i != selected_index]
            strategy_msg = f"kept row {selected_index + 1}"
    elif strategy == "keep_multiple":
        if not selected_indices:
            drop_indices = group_indices[1:]
            strategy_msg = "kept first (fallback)"
        else:
            keep_indices = [group_indices[i] for i in selected_indices if i < len(group_indices)]
            drop_indices = [idx for i, idx in enumerate(group_indices) if i not in selected_indices]
            if not drop_indices:
                return 0, "all rows selected — nothing to remove"
            strategy_msg = f"kept {len(keep_indices)} selected rows"
    elif strategy == "merge":
        keep_idx = group_indices[0]
        for idx in group_indices[1:]:
            for col in df.columns:
                if pd.isna(df.loc[keep_idx, col]) and not pd.isna(df.loc[idx, col]):
                    df.loc[keep_idx, col] = df.loc[idx, col]
        drop_indices = group_indices[1:]
        strategy_msg = "merged"
    else:
        drop_indices = group_indices[1:]
        strategy_msg = "kept first (default)"

    if drop_indices:
        sess.df = df.drop(drop_indices).reset_index(drop=True)
        rows_removed = len(drop_indices)
        sess.fixes_applied.append({
            "type": "remove_fuzzy_group",
            "strategy": strategy,
            "removed": rows_removed,
            "msg": strategy_msg,
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
    return rows_removed, strategy_msg


def remove_exact(sess: SessionData, subset: Optional[List[str]] = None,
                 keep: Any = "first") -> int:
    """Wraps the original transform_remove_exact_duplicates."""
    df = sess.df
    before = len(df)
    sess.df = df.drop_duplicates(subset=subset if subset else None, keep=keep).reset_index(drop=True)
    removed = before - len(sess.df)
    sess.fixes_applied.append({
        "type": "remove_exact_duplicates",
        "subset": subset, "keep": keep, "removed": removed,
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    })
    return removed


# ---------- excel export -------------------------------------------------

def export_groups_to_excel(groups: List[Any], filename_prefix: str) -> Tuple[bytes, str]:
    """1:1 port of _export_duplicates_excel."""
    output = io.BytesIO()
    with pd.ExcelWriter(output, engine="openpyxl") as writer:
        summary_data = []
        for group in groups:
            summary_data.append({
                "Group ID": int(group.group_id),
                "Rows": int(len(group.indices)),
                "Similarity": f"{(group.similarity_score or 100):.1f}%",
                "Match Type": str(group.match_type),
                "Key Columns": ", ".join(group.key_columns) if group.key_columns else "All",
            })
        pd.DataFrame(summary_data).to_excel(writer, sheet_name="Summary", index=False)
        # Up to 50 group sheets (Excel sheet name limit safeguard)
        for group in groups[:50]:
            df = pd.DataFrame(group.values)
            sheet_name = f"Group_{group.group_id}"[:31]
            df.to_excel(writer, sheet_name=sheet_name, index=False)
    output.seek(0)
    fname = f"{filename_prefix}_{datetime.now():%Y%m%d_%H%M%S}.xlsx"
    return output.getvalue(), fname
