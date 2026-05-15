"""1:1 port of features/quality/ui.py rule application + preview helpers.

Functions ported (verbatim semantics):
- _generate_rule_name        (lines 570-626)
- _get_preview_dataframe     (lines 629-701)
- _apply_column_rules        (lines 806-903)
- _apply_all_rules           (lines 906-918)
- _undo_last                 (lines 921-930)
"""
from __future__ import annotations

import re
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

from ..session_store import SessionData


def _stringify(series: pd.Series) -> pd.Series:
    """Convert a Series to clean string form for regex matching.

    Why: pandas coerces integer columns containing NaNs to float64, so a
    column like ``year_of_establishment`` (2017, 2018, ...) becomes
    ``2017.0, 2018.0, ...`` and ``.astype(str)`` yields "2017.0", which
    the AI year-validity regex (``^(19\\d{2}|20\\d{2})$``) never matches.
    For float-typed columns we strip the trailing ``.0`` on whole-number
    floats so the regex behaves like a human would expect.
    """
    if pd.api.types.is_float_dtype(series):
        def _conv(v):
            if pd.isna(v):
                return ""
            try:
                f = float(v)
                if f.is_integer():
                    return str(int(f))
                return str(v)
            except (TypeError, ValueError):
                return str(v)
        return series.map(_conv)
    return series.astype(str)


def default_config() -> Dict[str, Any]:
    return {
        "enabled": False,
        "mode": "Clean",
        "pattern": "",
        "replace": "",
        "case": "UPPERCASE",
        "length_mode": "Exact",
        "min_length": 0,
        "max_length": 50,
        "exact_length": 10,
        "applied_rules": [],
    }


def generate_rule_name(config: Dict[str, Any]) -> str:
    """Verbatim port of _generate_rule_name."""
    mode = config["mode"]
    if mode == "Clean":
        pattern = config.get("pattern", "")
        if pattern == r"[^a-zA-Z0-9\s]":
            return "Remove Special Chars"
        if pattern == r"\s":
            return "Remove Spaces"
        if pattern == "[0-9]":
            return "Remove Digits"
        return f"Clean: {pattern[:20]}"
    if mode == "Replace":
        pattern = config.get("pattern", "")
        replace = config.get("replace", "")
        if pattern == "_" and replace == " ":
            return "Replace _ with Space"
        return f"Replace: {pattern[:10]} → {replace[:10]}"
    if mode == "Extract":
        pattern = config.get("pattern", "")
        if pattern == "[0-9]":
            return "Extract Digits"
        if pattern == "[a-zA-Z]":
            return "Extract Letters"
        return f"Extract: {pattern[:20]}"
    if mode == "Validate":
        pattern = config.get("pattern", "")
        if "@" in pattern:
            return "Validate Email"
        if r"\d{10}" in pattern:
            return "Validate Phone"
        return "Validate Pattern"
    if mode == "Case":
        case = config.get("case", "UPPERCASE")
        return f"To {case}"
    if mode == "Length":
        length_mode = config.get("length_mode", "Exact")
        if length_mode == "Exact":
            return f"Length = {config.get('exact_length', 10)}"
        if length_mode == "Minimum":
            return f"Length ≥ {config.get('min_length', 0)}"
        if length_mode == "Maximum":
            return f"Length ≤ {config.get('max_length', 50)}"
        if length_mode == "Range":
            return f"Length {config.get('min_length', 0)}-{config.get('max_length', 50)}"
    return f"{mode} Rule"


def get_preview_failing(
    df: pd.DataFrame,
    column: str,
    config: Dict[str, Any],
    limit: int = 20,
) -> Optional[Dict[str, Any]]:
    """Preview rows that the rule would REJECT, with the full row context.

    Used by the per-row Preview button on the Cleansing tab: stewards need
    to see the whole record (vendor_name, country, etc.) — not just the
    isolated cell — to judge whether the rule is right. We also return
    only failing rows, since seeing 9 valid rows + 1 reject buries the
    signal.

    Returns ``{"column", "rows", "total_failing", "after_examples"}`` where
    each row dict is the full original row PLUS ``_before``, ``_after``,
    ``_status`` for the target column. Returns ``None`` on error.
    """
    try:
        mode = config["mode"]
        pattern = config.get("pattern", "")
        replace = config.get("replace", "")
        case = config.get("case", "UPPERCASE")

        # Build a failing-row mask that EXACTLY MIRRORS apply_column_rules.
        # The engine's apply path runs str.match / str.findall / str.len on
        # _stringify(col) — which turns NaN into "" — and rejects any row
        # the regex doesn't accept. That means null/blank rows ARE rejected
        # by a Completeness regex (^(?=.*\S).*$). Preview must show the
        # same set, otherwise the steward sees "0 failing" then watches
        # Apply reject N rows — exactly the bug just reported.
        col_series = _stringify(df[column])
        failing_mask = pd.Series(False, index=df.index)

        if mode == "Validate" and pattern:
            failing_mask = ~col_series.str.match(pattern, na=False)
        elif mode == "Extract" and pattern:
            failing_mask = col_series.str.findall(pattern).apply(
                lambda x: not (isinstance(x, list) and len(x) > 0)
            )
        elif mode == "Length":
            length_mode = config.get("length_mode", "Exact")
            lens = col_series.str.len()
            if length_mode == "Exact":
                failing_mask = lens != int(config.get("exact_length", 10))
            elif length_mode == "Minimum":
                failing_mask = lens < int(config.get("min_length", 0))
            elif length_mode == "Maximum":
                failing_mask = lens > int(config.get("max_length", 50))
            elif length_mode == "Range":
                lo, hi = int(config.get("min_length", 0)), int(config.get("max_length", 50))
                failing_mask = (lens < lo) | (lens > hi)
        # Clean / Replace / Case never reject — they're transforms. Show a
        # small Before/After sample for those modes so the steward sees the
        # effect (different code path below).

        total_failing = int(failing_mask.sum())
        if total_failing > 0:
            failing_df = df[failing_mask].head(limit).copy()
            failing_str = _stringify(failing_df[column])
            rows: List[Dict[str, Any]] = []
            for orig_idx, row in failing_df.iterrows():
                row_dict: Dict[str, Any] = {}
                for c in df.columns:
                    v = row[c]
                    row_dict[c] = "" if pd.isna(v) else str(v) if not isinstance(v, str) else v
                row_dict["_before"] = failing_str.loc[orig_idx]
                row_dict["_after"] = "[REJECT]"
                row_dict["_status"] = "Rejected"
                rows.append(row_dict)
            return {
                "column": column,
                "rows": rows,
                "total_failing": total_failing,
                "is_transform": False,
                "total_rows": int(len(df)),
            }

        # Pure-transform modes (Clean / Replace / Case) never reject —
        # they transform every value. Show a Before/After sample so the
        # steward can see what the rule does to real records.
        is_transform = mode in ("Clean", "Replace", "Case")
        if is_transform:
            sample = _stringify(df[column].dropna()).head(limit)
            sample_rows: List[Dict[str, Any]] = []
            for orig_idx, val in sample.items():
                full_row = df.loc[orig_idx]
                row_dict = {}
                for c in df.columns:
                    v = full_row[c]
                    row_dict[c] = "" if pd.isna(v) else str(v) if not isinstance(v, str) else v
                after = val
                if mode == "Clean" and pattern:
                    after = re.sub(pattern, "", val)
                elif mode == "Replace" and pattern:
                    after = re.sub(pattern, replace, val)
                elif mode == "Case":
                    if case == "UPPERCASE":
                        after = val.upper()
                    elif case == "lowercase":
                        after = val.lower()
                    elif case == "Title Case":
                        after = val.title()
                row_dict["_before"] = val
                row_dict["_after"] = str(after)
                row_dict["_status"] = "Transform"
                sample_rows.append(row_dict)
            return {
                "column": column,
                "rows": sample_rows,
                "total_failing": 0,
                "is_transform": True,
                "total_rows": int(len(df)),
            }

        # Validate / Extract / Length with zero failures — DON'T pad with
        # valid sample rows (that buries the real answer). Just report
        # 0 failures and let the UI show a success message.
        return {
            "column": column,
            "rows": [],
            "total_failing": 0,
            "is_transform": False,
            "total_rows": int(len(df)),
        }
    except Exception:
        return None


def get_preview(df: pd.DataFrame, column: str, config: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
    """Verbatim port of _get_preview_dataframe → list of {Before, After, Status}."""
    try:
        mode = config["mode"]
        pattern = config.get("pattern", "")
        replace = config.get("replace", "")
        case = config.get("case", "UPPERCASE")
        # Normalize float-stored ints ("2017.0" → "2017") so AI regexes
        # built for clean integer years actually match.
        sample = _stringify(df[column].dropna()).head(10)
        if sample.empty:
            return None
        rows: List[Dict[str, str]] = []
        for val in sample:
            result = val
            status = "Valid"
            if mode == "Clean":
                if pattern:
                    result = re.sub(pattern, "", val)
            elif mode == "Replace":
                if pattern:
                    result = re.sub(pattern, replace, val)
            elif mode == "Extract":
                if pattern:
                    matches = re.findall(pattern, val)
                    result = "".join(matches) if matches else "[REJECT]"
                    if result == "[REJECT]":
                        status = "Rejected"
            elif mode == "Validate":
                if pattern:
                    result = val if re.match(pattern, val) else "[REJECT]"
                    if result == "[REJECT]":
                        status = "Rejected"
            elif mode == "Case":
                if case == "UPPERCASE":
                    result = val.upper()
                elif case == "lowercase":
                    result = val.lower()
                elif case == "Title Case":
                    result = val.title()
            elif mode == "Length":
                length_mode = config["length_mode"]
                val_len = len(val)
                if length_mode == "Exact" and val_len != config["exact_length"]:
                    result = "[REJECT]"; status = "Rejected"
                elif length_mode == "Minimum" and val_len < config["min_length"]:
                    result = "[REJECT]"; status = "Rejected"
                elif length_mode == "Maximum" and val_len > config["max_length"]:
                    result = "[REJECT]"; status = "Rejected"
                elif length_mode == "Range" and (val_len < config["min_length"] or val_len > config["max_length"]):
                    result = "[REJECT]"; status = "Rejected"
            rows.append({"Before": val, "After": str(result), "Status": status})
        return rows
    except Exception:
        return None


def apply_column_rules(sess: SessionData, column: str) -> Tuple[int, int]:
    """Verbatim port of _apply_column_rules.

    Mutates sess.df, sess.reject_df, sess.validation_history.
    Returns (applied_count, rejected_count).
    """
    config = sess.dq_config.get(column)
    if not config:
        return 0, 0
    rules = config.get("applied_rules", [])
    if not rules:
        return 0, 0

    # Manual-review rules (Accuracy narratives, Uniqueness checks, etc.)
    # can't be auto-executed — keep them in applied_rules untouched so the
    # UI still shows them, but skip them in the transform loop.
    keep_after = [r for r in rules if r.get("mode") == "ManualReview"]
    rules = [r for r in rules if r.get("mode") != "ManualReview"]
    if not rules:
        return 0, 0

    backup_df = sess.df.copy()
    backup_reject = sess.reject_df.copy() if isinstance(sess.reject_df, pd.DataFrame) else pd.DataFrame()

    rejected_rows: List[pd.DataFrame] = []
    for rule in rules:
        try:
            col_data = _stringify(sess.df[column])
            mode = rule["mode"]
            if mode == "Clean":
                sess.df[column] = col_data.str.replace(rule["pattern"], "", regex=True)
            elif mode == "Replace":
                sess.df[column] = col_data.str.replace(rule["pattern"], rule["replace"], regex=True)
            elif mode == "Extract":
                extracted = col_data.str.findall(rule["pattern"])
                sess.df[column] = extracted.apply(lambda x: "".join(x) if isinstance(x, list) else "")
                invalid_mask = sess.df[column] == ""
                if invalid_mask.any():
                    rejected = sess.df[invalid_mask].copy()
                    rejected["Rejection_Reason"] = f"{rule['name']} - No matches"
                    rejected["Rejected_Column"] = column
                    rejected["Rejected_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    rejected_rows.append(rejected)
                    # IMPORTANT: do NOT reset_index. The pandas index is
                    # the row identity Compare uses to align before/after
                    # views. Reset-index loses that — every surviving row
                    # would line up against a different original row and
                    # appear "Modified" instead of "the row that came
                    # before was Removed".
                    sess.df = sess.df[~invalid_mask]
            elif mode == "Validate":
                invalid_mask = ~col_data.str.match(rule["pattern"], na=False)
                if invalid_mask.any():
                    rejected = sess.df[invalid_mask].copy()
                    rejected["Rejection_Reason"] = f"{rule['name']} - Does not match"
                    rejected["Rejected_Column"] = column
                    rejected["Rejected_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    rejected_rows.append(rejected)
                    # IMPORTANT: do NOT reset_index. The pandas index is
                    # the row identity Compare uses to align before/after
                    # views. Reset-index loses that — every surviving row
                    # would line up against a different original row and
                    # appear "Modified" instead of "the row that came
                    # before was Removed".
                    sess.df = sess.df[~invalid_mask]
            elif mode == "Case":
                if rule["case"] == "UPPERCASE":
                    sess.df[column] = col_data.str.upper()
                elif rule["case"] == "lowercase":
                    sess.df[column] = col_data.str.lower()
                elif rule["case"] == "Title Case":
                    sess.df[column] = col_data.str.title()
            elif mode == "Length":
                lengths = col_data.str.len()
                length_mode = rule["length_mode"]
                if length_mode == "Exact":
                    invalid_mask = lengths != rule["exact_length"]
                elif length_mode == "Minimum":
                    invalid_mask = lengths < rule["min_length"]
                elif length_mode == "Maximum":
                    invalid_mask = lengths > rule["max_length"]
                elif length_mode == "Range":
                    invalid_mask = (lengths < rule["min_length"]) | (lengths > rule["max_length"])
                else:
                    continue
                if invalid_mask.any():
                    rejected = sess.df[invalid_mask].copy()
                    rejected["Rejection_Reason"] = f"{rule['name']} - Length check failed"
                    rejected["Rejected_Column"] = column
                    rejected["Rejected_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    rejected_rows.append(rejected)
                    # IMPORTANT: do NOT reset_index. The pandas index is
                    # the row identity Compare uses to align before/after
                    # views. Reset-index loses that — every surviving row
                    # would line up against a different original row and
                    # appear "Modified" instead of "the row that came
                    # before was Removed".
                    sess.df = sess.df[~invalid_mask]
        except Exception:
            continue

    rejected_count = 0
    if rejected_rows:
        all_rejected = pd.concat(rejected_rows, ignore_index=True)
        rejected_count = len(all_rejected)
        if sess.reject_df is None or sess.reject_df.empty:
            sess.reject_df = all_rejected
        else:
            sess.reject_df = pd.concat([sess.reject_df, all_rejected], ignore_index=True)

    # Snapshot the rules we just applied so undo can restore them, and
    # tally each one against its DAMA dimension for the progress meter.
    applied_snapshot = list(rules)
    backup_dim_counts = dict(sess.applied_rules_by_dim)
    for rule in applied_snapshot:
        dim = rule.get("dimension") or "Other"
        sess.applied_rules_by_dim[dim] = sess.applied_rules_by_dim.get(dim, 0) + 1
    # Preserve manual-review rules — they sit until a steward clears them.
    config["applied_rules"] = list(keep_after)
    sess.validation_history.append({
        "description": f"Applied {len(rules)} rules to {column}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rejected_count": rejected_count,
        "backup_df": backup_df,
        "backup_reject_df": backup_reject,
        "backup_applied_rules": applied_snapshot,
        "backup_applied_dim_counts": backup_dim_counts,
        "column": column,
    })
    return len(rules), rejected_count


def apply_all_rules(sess: SessionData) -> Dict[str, Any]:
    """Verbatim port of _apply_all_rules."""
    enabled_cols = [
        c for c, cfg in sess.dq_config.items()
        if cfg.get("enabled") and cfg.get("applied_rules")
    ]
    if not enabled_cols:
        return {"applied": 0, "columns": []}
    total_applied = 0
    total_rejected = 0
    for col in enabled_cols:
        a, r = apply_column_rules(sess, col)
        total_applied += a
        total_rejected += r
    return {"applied": total_applied, "rejected": total_rejected, "columns": enabled_cols}


def undo_last(sess: SessionData) -> bool:
    """Verbatim port of _undo_last, augmented to also restore applied
    rules and roll back the per-dimension counter so the progress meter
    on the new Cleansing UI moves in lockstep with the data."""
    if not sess.validation_history:
        return False
    last = sess.validation_history.pop()
    sess.df = last["backup_df"].copy()
    sess.reject_df = last["backup_reject_df"].copy() if last.get("backup_reject_df") is not None else pd.DataFrame()
    snapshot = last.get("backup_applied_rules") or []
    col = last.get("column")
    if col and col in sess.dq_config and snapshot:
        sess.dq_config[col]["applied_rules"] = list(snapshot) + list(sess.dq_config[col].get("applied_rules", []))
    backup_counts = last.get("backup_applied_dim_counts")
    if isinstance(backup_counts, dict):
        sess.applied_rules_by_dim = dict(backup_counts)
    return True
