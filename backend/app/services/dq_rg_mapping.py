"""1:1 port of features/quality/ui.py:_get_enriched_rg_rules + _rg_row_to_applied_rule."""
from __future__ import annotations

import importlib.util as _imp
import sys as _sys
from datetime import datetime
from pathlib import Path as _Path
from typing import Any, Dict, List, Optional

import pandas as pd

# Direct-import engine to bypass features.rule_generator/__init__.py (Streamlit)
_root = _Path(__file__).resolve().parents[3]
_spec = _imp.spec_from_file_location("_rg_engine_q", str(_root / "features/rule_generator/engine.py"))
_engine = _imp.module_from_spec(_spec)
_sys.modules["_rg_engine_q"] = _engine
_spec.loader.exec_module(_engine)

enrich_dataframe_regex_patterns = _engine.enrich_dataframe_regex_patterns
_extract_max_chars = _engine._extract_max_chars


def get_enriched_rg_rules(df: Optional[pd.DataFrame]) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    return enrich_dataframe_regex_patterns(df.copy())


def rg_row_to_applied_rule(row: pd.Series) -> Optional[Dict[str, Any]]:
    """Verbatim port of _rg_row_to_applied_rule."""
    pat = str(row.get("Regex Pattern", "") or "").strip()
    dim = str(row.get("Dimension", "") or "")
    dq = str(row.get("Data Quality Rule", "") or "")
    dl = dq.lower()
    ts = datetime.now().strftime("%H:%M:%S")

    def _base(**overrides):
        base = {
            "replace": "", "case": "UPPERCASE", "length_mode": "Exact",
            "min_length": 0, "max_length": 50, "exact_length": 10,
            "timestamp": ts,
        }
        base.update(overrides)
        return base

    if pat:
        return _base(name=f"RG · {dim}: {dq[:48]}", mode="Validate", pattern=pat)
    if "uppercase" in dl or "upper case" in dl:
        return _base(name=f"RG · Case: {dq[:48]}", mode="Case", pattern="", case="UPPERCASE")
    if "lowercase" in dl or "lower case" in dl:
        return _base(name=f"RG · Case: {dq[:48]}", mode="Case", pattern="", case="lowercase")
    mc = _extract_max_chars(dq)
    if mc is not None:
        return _base(
            name=f"RG · Length ≤ {mc}", mode="Length", pattern="",
            length_mode="Maximum", max_length=int(mc),
        )
    return None


def get_rg_options_for_column(rules_df: Optional[pd.DataFrame], column: str) -> List[Dict[str, Any]]:
    """Return list of RG options for a column, each {label, rule}."""
    if rules_df is None or rules_df.empty:
        return []
    sub = rules_df[rules_df["Column"] == column]
    if sub.empty:
        return []
    options = []
    for _, r in sub.iterrows():
        applied = rg_row_to_applied_rule(r)
        if applied is None:
            continue
        full_rule = str(r.get("Data Quality Rule", ""))
        short = full_rule[:40] + "…" if len(full_rule) > 40 else full_rule
        label = f"{int(r['S.No'])} · {r['Dimension']} · {short}"
        options.append({"label": label, "rule": applied})
    return options
