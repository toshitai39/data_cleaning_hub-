"""1:1 port of features/rule_generator/ui.py:_generate_rules_with_comprehensive_engine.

Imports the existing rule_generator.engine + report modules directly (they are
Streamlit-free), so the rule output is literally identical to the Streamlit app.
"""
from __future__ import annotations

import json
import logging
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

# Import from the engine module file directly to avoid features/rule_generator/__init__.py
# which imports the Streamlit UI module.
import importlib.util as _imp
import sys as _sys
from pathlib import Path as _Path

_engine_path = _Path(__file__).resolve().parents[3] / "features" / "rule_generator" / "engine.py"
_spec = _imp.spec_from_file_location("_rg_engine", str(_engine_path))
_engine = _imp.module_from_spec(_spec)
_sys.modules["_rg_engine"] = _engine
_spec.loader.exec_module(_engine)

deep_scan_rule_sheet = _engine.deep_scan_rule_sheet
enrich_dataframe_regex_patterns = _engine.enrich_dataframe_regex_patterns
extract_comprehensive_metadata = _engine.extract_comprehensive_metadata
generate_comprehensive_ai_prompt = _engine.generate_comprehensive_ai_prompt
generate_cross_field_prompt = _engine.generate_cross_field_prompt
post_process_rules = _engine.post_process_rules
validate_all_rules = _engine.validate_all_rules

from .azure_openai_config import AzureOpenAIConfig

logger = logging.getLogger(__name__)


def generate_rules_with_comprehensive_engine(
    file_path: Optional[str],
    sheet_name: Optional[str],
    header_row: int,
    df: pd.DataFrame,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> pd.DataFrame:
    """Verbatim port of features/rule_generator/ui.py:_generate_rules_with_comprehensive_engine.

    Differences from Streamlit version:
      - st.progress / st.empty are replaced with an optional progress callback.
      - Errors are logged + a fallback rule appended (same behaviour).
    """
    from openai import AzureOpenAI

    client = AzureOpenAI(
        api_version=AzureOpenAIConfig.AZURE_OPENAI_API_VERSION,
        azure_endpoint=AzureOpenAIConfig.AZURE_OPENAI_ENDPOINT,
        api_key=AzureOpenAIConfig.AZURE_OPENAI_KEY,
    )

    # Step 1: Deep scan Excel sheet (only if Excel file)
    column_rules: Dict[str, str] = {}
    if file_path and sheet_name and (file_path.endswith(".xlsx") or file_path.endswith(".xls")):
        column_rules = deep_scan_rule_sheet(file_path, sheet_name, header_row)

    total_cols = len(df.columns)
    all_column_names = [str(c) for c in df.columns]

    # Pre-compute deterministic samples once. Sorting + dedup is O(n) per
    # column, so doing it in the main thread (not inside each worker) avoids
    # repeating it and keeps the per-thread work strictly LLM I/O.
    column_samples: Dict[str, List[str]] = {}
    for c in df.columns:
        column_samples[str(c)] = sorted(
            {str(v) for v in df[c].dropna().tolist()}
        )[:50]

    # A small slice of every other column's samples flows into each prompt
    # so the model can spot cross-column relationships (e.g. country values
    # are 2-letter ISO codes → propose VAT prefix rules).
    sibling_samples_by_col: Dict[str, Dict[str, List[str]]] = {}
    for c in all_column_names:
        sibling_samples_by_col[c] = {
            other: column_samples[other][:5]
            for other in all_column_names if other != c
        }

    progress_lock = threading.Lock()
    completed = {"n": 0}
    # Two passes per column (per-column rules + cross-field), so the
    # progress denominator is 2× total_cols.
    progress_total = 2 * total_cols

    def _llm_json(prompt: str) -> Dict[str, Any]:
        """Single deterministic LLM call returning a parsed JSON object."""
        response = client.chat.completions.create(
            model=AzureOpenAIConfig.AZURE_OPENAI_DEPLOYMENT,
            messages=[
                {"role": "system", "content": "You are a data quality expert. Return only valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            seed=42,
            response_format={"type": "json_object"},
            max_tokens=1500,
        )
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()
        return json.loads(text)

    def _bump_progress(column_name: str) -> None:
        with progress_lock:
            completed["n"] += 1
            if progress_cb:
                progress_cb({
                    "stage": "analyzing",
                    "index": completed["n"],
                    "total": progress_total,
                    "column": str(column_name),
                })

    # ───── Pass 1: per-column rules (Accuracy → Uniqueness, six rules) ──
    def _run_per_column(column_name: str) -> Dict[str, Any]:
        rule_text = column_rules.get(column_name, None)
        rule_source = "Rules from Existing Sheet" if rule_text else "Generated by AI"
        metadata = extract_comprehensive_metadata(column_name, rule_text)
        sample_data = column_samples[str(column_name)]
        data_type = str(df[column_name].dtype)
        null_pct = (df[column_name].isnull().sum() / len(df)) * 100 if len(df) > 0 else 0
        unique_pct = (df[column_name].nunique() / len(df)) * 100 if len(df) > 0 else 0

        prompt = generate_comprehensive_ai_prompt(
            column_name=column_name,
            sample_data=sample_data,
            data_type=data_type,
            null_pct=null_pct,
            unique_pct=unique_pct,
            metadata=metadata,
            rule_source=rule_source,
        )
        try:
            result = _llm_json(prompt)
            rules = post_process_rules(result.get("rules", []), metadata) if "rules" in result else []
            return {"column": column_name, "rule_source": rule_source, "rules": rules, "error": None}
        except Exception as exc:
            logger.error("Per-column LLM error for '%s': %s", column_name, exc)
            return {"column": column_name, "rule_source": rule_source, "rules": [], "error": str(exc)}
        finally:
            _bump_progress(column_name)

    # ───── Pass 2: cross-field rules (one focused call per column) ──────
    valid_column_set = set(all_column_names)

    def _run_cross_field(column_name: str) -> Dict[str, Any]:
        siblings = sibling_samples_by_col[str(column_name)]
        if not siblings:
            _bump_progress(column_name)
            return {"column": column_name, "rules": [], "error": None}

        prompt = generate_cross_field_prompt(
            target_column=str(column_name),
            target_samples=column_samples[str(column_name)],
            target_dtype=str(df[column_name].dtype),
            sibling_samples=siblings,
        )
        try:
            result = _llm_json(prompt)
            raw_rules = result.get("rules", []) if isinstance(result, dict) else []
            cleaned: List[Dict[str, Any]] = []
            for r in raw_rules:
                refs = r.get("siblings_referenced") or []
                rule_text = str(r.get("data_quality_rule", "")).strip()
                if not rule_text:
                    continue
                # Drop hallucinated siblings: every referenced sibling must
                # exist in the dataset. If any reference is invalid, drop
                # the rule rather than emit a half-truth.
                if not refs or not all(s in valid_column_set for s in refs):
                    # Fallback: try to recover by finding which real columns
                    # the rule text actually mentions. If at least one is
                    # found, keep the rule; otherwise drop it.
                    mentioned = [c for c in valid_column_set
                                 if c != column_name and c in rule_text]
                    if not mentioned:
                        continue
                cleaned.append({
                    "dimension": "Cross-field Validation",
                    "data_quality_rule": rule_text,
                })
            return {"column": column_name, "rules": cleaned, "error": None}
        except Exception as exc:
            logger.error("Cross-field LLM error for '%s': %s", column_name, exc)
            return {"column": column_name, "rules": [], "error": str(exc)}
        finally:
            _bump_progress(column_name)

    # Bound the worker count: enough to amortize LLM latency, not so many
    # that we breach the Azure RPM cap. 8 workers × ~3s/call ≈ 22 calls
    # per minute — well under the 60 RPM default.
    max_workers = min(8, max(1, total_cols))
    per_column_results: Dict[str, Dict[str, Any]] = {}
    cross_field_results: Dict[str, Dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        per_futs = {pool.submit(_run_per_column, c): c for c in df.columns}
        cross_futs = {pool.submit(_run_cross_field, c): c for c in df.columns}
        for fut in as_completed(per_futs):
            r = fut.result()
            per_column_results[r["column"]] = r
        for fut in as_completed(cross_futs):
            r = fut.result()
            cross_field_results[r["column"]] = r

    # Re-emit rules in df.columns order so S.No is deterministic and not
    # dependent on which thread happened to finish first. For each column
    # the per-column rules come first, then any cross-field rules.
    all_rules: List[Dict[str, Any]] = []
    for column_name in df.columns:
        res = per_column_results.get(column_name)
        if not res:
            continue
        if res["error"] and not res["rules"]:
            all_rules.append({
                "S.No": len(all_rules) + 1,
                "Column": column_name,
                "Business Field": column_name,
                "Rule Source": "Generated by AI",
                "Dimension": "Validity",
                "Data Quality Rule": f"{column_name} should be validated",
                "Regex Pattern": "",
                "Issues Found": 0,
                "Issues Found Example": f"Error: {res['error']}",
            })
            continue
        for rule in res["rules"]:
            all_rules.append({
                "S.No": len(all_rules) + 1,
                "Column": column_name,
                "Business Field": column_name,
                "Rule Source": res["rule_source"],
                "Dimension": rule.get("dimension", "Validity"),
                "Data Quality Rule": rule.get("data_quality_rule", rule.get("rule_statement", "")),
                "Regex Pattern": (rule.get("regex_pattern") or ""),
                "Issues Found": rule.get("issues_found", 0),
                "Issues Found Example": rule.get("issues_found_example", "All values valid - No issues found"),
            })
        cf = cross_field_results.get(column_name)
        if cf:
            for rule in cf["rules"]:
                all_rules.append({
                    "S.No": len(all_rules) + 1,
                    "Column": column_name,
                    "Business Field": column_name,
                    "Rule Source": "Generated by AI",
                    "Dimension": "Cross-field Validation",
                    "Data Quality Rule": rule["data_quality_rule"],
                    "Regex Pattern": "",
                    "Issues Found": 0,
                    "Issues Found Example": "All values valid - No issues found",
                })

    return pd.DataFrame(all_rules)


def generate_complete(
    file_path: Optional[str],
    sheet_name: Optional[str],
    header_row: int,
    df: pd.DataFrame,
    progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
) -> pd.DataFrame:
    """Full end-to-end pipeline matching the Streamlit button click:
    1) generate rules via comprehensive engine
    2) validate against actual data
    3) enrich regex patterns
    """
    df_rules = generate_rules_with_comprehensive_engine(
        file_path, sheet_name, header_row, df, progress_cb,
    )
    df_rules = validate_all_rules(df, df_rules)
    df_rules = enrich_dataframe_regex_patterns(df_rules)
    return df_rules
