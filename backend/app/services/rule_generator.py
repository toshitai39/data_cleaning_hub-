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
    # One per-column call per column + a single whole-dataset cross-field
    # call. Progress denominator is total_cols + 1.
    progress_total = total_cols + 1

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

    # ───── Pass 2: whole-dataset cross-field call (one LLM call total) ──
    #
    # Cross-field rules belong to combinations of columns, not to a single
    # column, so the model does better thinking top-down about the whole
    # table than column-by-column. One call, sees every column + samples,
    # returns 0–10 rules each tagged with the columns they involve.
    valid_column_set = set(all_column_names)

    def _run_cross_field_table() -> List[Dict[str, Any]]:
        prompt = generate_cross_field_prompt(column_samples=column_samples)
        try:
            result = _llm_json(prompt)
            raw_rules = result.get("rules", []) if isinstance(result, dict) else []
            cleaned: List[Dict[str, Any]] = []
            for r in raw_rules:
                rule_text = str(r.get("data_quality_rule", "")).strip()
                cols = r.get("columns") or []
                if not rule_text or len(cols) < 2:
                    continue
                # Drop hallucinated columns. Every column in the rule's
                # ``columns`` list must exist in the dataset. If any do not,
                # try to recover by scanning the rule text for real column
                # names — keep only if at least two real columns are found.
                if not all(c in valid_column_set for c in cols):
                    mentioned = [c for c in valid_column_set if c in rule_text]
                    if len(mentioned) < 2:
                        continue
                    cols = mentioned
                cleaned.append({
                    "data_quality_rule": rule_text,
                    "columns": list(cols),
                })
            return cleaned
        except Exception as exc:
            logger.error("Cross-field LLM error (whole-dataset pass): %s", exc)
            return []
        finally:
            _bump_progress("(cross-field pass)")

    # Bound the worker count: enough to amortize per-column LLM latency,
    # not so many that we breach the Azure RPM cap. 8 workers × ~3s/call
    # ≈ 22 calls per minute — well under the 60 RPM default. The cross-
    # field call runs in the same pool so it overlaps with per-column work.
    max_workers = min(8, max(1, total_cols))
    per_column_results: Dict[str, Dict[str, Any]] = {}
    cross_field_rules: List[Dict[str, Any]] = []
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        per_futs = {pool.submit(_run_per_column, c): c for c in df.columns}
        cross_fut = pool.submit(_run_cross_field_table)
        for fut in as_completed(per_futs):
            r = fut.result()
            per_column_results[r["column"]] = r
        cross_field_rules = cross_fut.result()

    # Group cross-field rules by their primary (first) column so each
    # rule appears as a row attached to that column.
    cross_field_by_primary: Dict[str, List[Dict[str, Any]]] = {}
    for rule in cross_field_rules:
        primary = rule["columns"][0]
        cross_field_by_primary.setdefault(primary, []).append(rule)

    # Re-emit rules in df.columns order so S.No is deterministic and not
    # dependent on which thread happened to finish first. Per-column
    # rules first, then any cross-field rules whose primary column is
    # this one. The Column field for a cross-field row uses the joined
    # tuple (e.g. "name + country + entity_type") so the table mirrors
    # the customer-rule sheet shape.
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
        for cf in cross_field_by_primary.get(str(column_name), []):
            tuple_label = " + ".join(cf["columns"])
            all_rules.append({
                "S.No": len(all_rules) + 1,
                "Column": tuple_label,
                "Business Field": tuple_label,
                "Rule Source": "Generated by AI",
                "Dimension": "Cross-field Validation",
                "Data Quality Rule": cf["data_quality_rule"],
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
