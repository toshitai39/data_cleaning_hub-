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


def get_preview(df: pd.DataFrame, column: str, config: Dict[str, Any]) -> Optional[List[Dict[str, str]]]:
    """Verbatim port of _get_preview_dataframe → list of {Before, After, Status}."""
    try:
        mode = config["mode"]
        pattern = config.get("pattern", "")
        replace = config.get("replace", "")
        case = config.get("case", "UPPERCASE")
        sample = df[column].dropna().astype(str).head(10)
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

    backup_df = sess.df.copy()
    backup_reject = sess.reject_df.copy() if isinstance(sess.reject_df, pd.DataFrame) else pd.DataFrame()

    rejected_rows: List[pd.DataFrame] = []
    for rule in rules:
        try:
            col_data = sess.df[column].astype(str)
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
                    sess.df = sess.df[~invalid_mask].reset_index(drop=True)
            elif mode == "Validate":
                invalid_mask = ~col_data.str.match(rule["pattern"], na=False)
                if invalid_mask.any():
                    rejected = sess.df[invalid_mask].copy()
                    rejected["Rejection_Reason"] = f"{rule['name']} - Does not match"
                    rejected["Rejected_Column"] = column
                    rejected["Rejected_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    rejected_rows.append(rejected)
                    sess.df = sess.df[~invalid_mask].reset_index(drop=True)
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
                    sess.df = sess.df[~invalid_mask].reset_index(drop=True)
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

    config["applied_rules"] = []
    sess.validation_history.append({
        "description": f"Applied {len(rules)} rules to {column}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rejected_count": rejected_count,
        "backup_df": backup_df,
        "backup_reject_df": backup_reject,
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
    """Verbatim port of _undo_last."""
    if not sess.validation_history:
        return False
    last = sess.validation_history.pop()
    sess.df = last["backup_df"].copy()
    sess.reject_df = last["backup_reject_df"].copy() if last.get("backup_reject_df") is not None else pd.DataFrame()
    return True
