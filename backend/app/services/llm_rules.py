"""LLM-backed validation-rule generator.

Mirrors the prompt and parsing strategy from features/profiling/ui.py so the
rules produced by the new FastAPI backend are equivalent to the Streamlit app.
Reads Azure OpenAI credentials from environment variables OR from
.streamlit/secrets.toml so existing configuration keeps working.

Falls back to a deterministic rule set when the LLM call fails or no
credentials are configured.
"""
from __future__ import annotations

import json
import logging
import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Any, Dict, List, Optional

import pandas as pd

logger = logging.getLogger(__name__)

ALLOWED_DIMENSIONS = ("Accuracy", "Completeness", "Standardisation", "Validation", "Uniqueness", "Timeliness")


def _normalize_dimension(value: Any) -> str:
    """Coerce any LLM-returned dimension into one of the six allowed dimensions."""
    raw = str(value or "").strip()
    if not raw:
        return "Validation"
    for d in ALLOWED_DIMENSIONS:
        if raw.lower() == d.lower():
            return d
    legacy = {
        "conformity": "Validation",
        "character length": "Validation",
        "integrity": "Standardisation",
        "reliability": "Accuracy",
        "relevance": "Accuracy",
        "precision": "Accuracy",
        "accessibility": "Validation",
        # Pre-rename display names — keep on-disk rules readable.
        "validity": "Validation",
        "consistency": "Standardisation",
    }
    return legacy.get(raw.lower(), "Validation")

_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SECRETS_PATH = _PROJECT_ROOT / ".streamlit" / "secrets.toml"
_DOTENV_PATH = _PROJECT_ROOT / ".env"


def _parse_kv_file(path: Path) -> Dict[str, str]:
    """Read a flat ``KEY=value`` config file (.env or secrets.toml style).

    Accepts optional surrounding double or single quotes on the value, ignores
    blank lines and ``#`` comments, and stops at the first ``#`` outside of a
    quoted value so inline comments don't get swallowed. Returns ``{}`` when
    the file is missing or unreadable — callers must tolerate empty configs.
    """
    if not path.exists():
        return {}
    out: Dict[str, str] = {}
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        # Allow `KEY=value`, `KEY="value"`, `KEY='value'`, `export KEY=value`.
        m = re.match(
            r'(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:"([^"]*)"|\'([^\']*)\'|([^#\n]*))',
            line,
        )
        if not m:
            continue
        key = m.group(1)
        value = next((g for g in m.groups()[1:] if g is not None), "")
        out[key] = value.strip()
    return out


def _read_secrets_file() -> Dict[str, str]:
    return _parse_kv_file(_SECRETS_PATH)


def _read_dotenv_file() -> Dict[str, str]:
    return _parse_kv_file(_DOTENV_PATH)


@lru_cache(maxsize=1)
def _config() -> Dict[str, Optional[str]]:
    """Resolve Azure OpenAI config — env first, then ``.env`` at project root,
    then ``.streamlit/secrets.toml``. The ``.env`` fallback is what makes the
    Render / local-dev workflow Just Work without sourcing the file by hand.
    """
    dotenv = _read_dotenv_file()
    secrets = _read_secrets_file()

    def pick(key: str) -> Optional[str]:
        return os.environ.get(key) or dotenv.get(key) or secrets.get(key) or None

    return {
        "endpoint": pick("AZURE_OPENAI_ENDPOINT"),
        "key": pick("AZURE_OPENAI_KEY"),
        "deployment": pick("AZURE_OPENAI_DEPLOYMENT"),
        "api_version": pick("AZURE_OPENAI_API_VERSION") or "2024-12-01-preview",
    }


def llm_available() -> bool:
    cfg = _config()
    return bool(cfg["endpoint"] and cfg["key"] and cfg["deployment"])


def _client():
    """Lazily build an AzureOpenAI client. None if not configured."""
    cfg = _config()
    if not llm_available():
        return None
    try:
        from openai import AzureOpenAI
    except ImportError:
        logger.warning("openai package not installed — falling back to heuristic rules.")
        return None
    return AzureOpenAI(
        azure_endpoint=cfg["endpoint"],
        api_key=cfg["key"],
        api_version=cfg["api_version"],
    )


# Prompt mirrors features/profiling/ui.py so output shape is identical.
_SYSTEM = (
    "You are a Business Data Analyst who writes clear, human-readable data "
    "quality rules for enterprise systems. Return only JSON."
)


def _column_metadata(name: str) -> Dict[str, Any]:
    """Tiny re-implementation of features/profiling/ui.py extract_column_metadata."""
    out: Dict[str, Any] = {"max_length": None, "data_type_hint": None}
    m = re.search(
        r"(VARCHAR2?|CHAR(?:ACTERS)?|STRING|TEXT)\s*\(?\s*(\d+)\s*(?:CHAR|BYTE)?\s*\)?",
        name, re.IGNORECASE,
    )
    if m:
        out["data_type_hint"] = m.group(1).upper()
        out["max_length"] = int(m.group(2))
        return out
    m = re.search(r"(NUMBER|DECIMAL|NUMERIC|FLOAT)\s*\(?\s*(\d+)", name, re.IGNORECASE)
    if m:
        out["data_type_hint"] = m.group(1).upper()
        out["max_length"] = int(m.group(2))
        return out
    m = re.search(r"\((\d+)\)", name)
    if m:
        out["max_length"] = int(m.group(1))
    return out


def _build_prompt(column_name: str, samples: List[Any], dtype: str,
                  null_pct: float, unique_pct: float,
                  is_unique_candidate: bool, has_duplicates: bool,
                  meta: Dict[str, Any]) -> str:
    sample_str = json.dumps([str(s) for s in samples[:50]], default=str)
    md_section = ""
    if meta.get("max_length"):
        md_section += f"- Maximum Length: {meta['max_length']} characters\n"
    if meta.get("data_type_hint"):
        md_section += f"- Data Type Hint: {meta['data_type_hint']}\n"

    duplicate_hint = ""
    if is_unique_candidate or has_duplicates:
        duplicate_hint = (
            "\nCOLUMN BEHAVIOUR\n================\n"
            f"- Has duplicate values in current data: {has_duplicates}\n"
            f"- Looks like a unique identifier candidate: {is_unique_candidate}\n"
            "If this looks like an ID/UID/Key column, ALWAYS include a Uniqueness "
            "rule stating values must be unique, even if duplicates already exist.\n"
        )

    return f"""Analyze this data column and generate human-readable validation rules.

COLUMN INFORMATION
==================
Column Name: {column_name}
Data Type: {dtype}
Sample Values: {sample_str}
Null Percentage: {null_pct:.1f}%
Unique Percentage: {unique_pct:.1f}%
{md_section}{duplicate_hint}

REQUIRED OUTPUT FORMAT
======================
Return ONLY valid JSON, no markdown, with this exact structure:

{{
  "business_field_name": "Human-friendly field name",
  "rules": [
    {{
      "dimension": "MUST be exactly one of these six values (case-sensitive): Accuracy, Completeness, Standardisation, Validation, Uniqueness, Timeliness. Do NOT use any other dimension name.",
      "rule_statement": "Human readable rule in format: [Field Name] + Must/Should + Business Condition",
      "regex": "Optional regex pattern that values must match, or null"
    }}
  ]
}}

REQUIREMENTS
============
1. Generate 2-4 rules per column.
2. ALWAYS include a Completeness rule if null_percentage > 0.
3. ALWAYS include a Uniqueness rule if the column looks like an ID/UID/key.
4. If sample values look like emails, phones, dates, IDs — include a Validation rule with a regex.
5. Use exact format: [Field Name] + Must/Should + Business Condition.
6. The "dimension" field MUST be one of exactly these six values: Accuracy, Completeness, Standardisation, Validation, Uniqueness, Timeliness. Format/length/case rules belong under Validation. Reject any output that uses a different dimension name.
7. No markdown. No commentary. JSON only.
"""


def _parse_response(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    cleaned = re.sub(r"```json\s*|\s*```", "", text).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError:
        # Try to recover the first {...} block
        m = re.search(r"\{.*\}", cleaned, re.DOTALL)
        if m:
            try:
                return json.loads(m.group(0))
            except json.JSONDecodeError:
                return None
    return None


def _heuristic_rules(name: str, series: pd.Series) -> List[Dict[str, Any]]:
    """Deterministic fallback that still produces useful, multi-rule output."""
    s = series.dropna().astype(str)
    null_pct = float(series.isna().mean() * 100)
    total = len(series)
    unique_pct = float(series.nunique(dropna=True) / max(total, 1) * 100)
    looks_like_id = bool(re.search(r"\b(id|uid|code|key|number|no\.?)\b", name, re.IGNORECASE))
    rules: List[Dict[str, Any]] = []

    if null_pct > 0 or looks_like_id:
        rules.append({
            "column": name,
            "dimension": "Completeness",
            "rule": f"{name} should not be blank or null",
            "regex": None,
            "examples": s.head(3).tolist(),
        })

    if looks_like_id or unique_pct > 95:
        rules.append({
            "column": name,
            "dimension": "Uniqueness",
            "rule": f"{name} must be unique across all records",
            "regex": None,
            "examples": s.head(3).tolist(),
        })

    if not s.empty:
        sample = s.iloc[0]
        if "@" in sample:
            rules.append({
                "column": name, "dimension": "Validation",
                "rule": f"{name} must follow standard email format",
                "regex": r"^[^@\s]+@[^@\s]+\.[^@\s]+$",
                "examples": s.head(3).tolist(),
            })
        elif re.match(r"^-?\d+(\.\d+)?$", sample):
            rules.append({
                "column": name, "dimension": "Validation",
                "rule": f"{name} must be numeric",
                "regex": r"^-?\d+(\.\d+)?$",
                "examples": s.head(3).tolist(),
            })
        else:
            max_len = int(s.str.len().max())
            rules.append({
                "column": name, "dimension": "Validation",
                "rule": f"{name} must not exceed {max_len} characters",
                "regex": None,
                "examples": s.head(3).tolist(),
            })

    if not rules:
        rules.append({
            "column": name, "dimension": "Validation",
            "rule": f"{name} should follow expected business format",
            "regex": None, "examples": [],
        })
    return rules


def generate_rules_for_dataframe(df: pd.DataFrame, columns: Optional[List[str]] = None,
                                 use_llm: bool = True) -> List[Dict[str, Any]]:
    """Generate validation rules for each column.

    Returns flat list of rule dicts: {column, dimension, rule, regex, examples}.
    Each column may produce multiple rules.
    """
    target_cols = columns or list(df.columns.astype(str))
    client = _client() if use_llm else None
    deployment = _config()["deployment"]

    all_rules: List[Dict[str, Any]] = []

    for col in target_cols:
        if col not in df.columns:
            continue
        series = df[col]
        s_clean = series.dropna()
        samples = s_clean.astype(str).head(20).tolist()
        null_pct = float(series.isna().mean() * 100)
        total = len(series)
        unique_count = int(series.nunique(dropna=True))
        unique_pct = float(unique_count / max(total, 1) * 100)
        non_null = total - int(series.isna().sum())
        has_duplicates = bool(non_null > 0 and unique_count < non_null)
        is_unique_candidate = bool(
            re.search(r"\b(id|uid|code|key|number|no\.?)\b", col, re.IGNORECASE)
            or unique_pct > 95
        )

        col_rules: List[Dict[str, Any]] = []

        if client is not None:
            try:
                meta = _column_metadata(col)
                prompt = _build_prompt(
                    col, samples, str(series.dtype), null_pct, unique_pct,
                    is_unique_candidate, has_duplicates, meta,
                )
                resp = client.chat.completions.create(
                    model=deployment,
                    messages=[
                        {"role": "system", "content": _SYSTEM},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.1,
                    max_completion_tokens=1500,
                )
                content = resp.choices[0].message.content
                parsed = _parse_response(content)
                if parsed and isinstance(parsed.get("rules"), list):
                    for r in parsed["rules"]:
                        col_rules.append({
                            "column": col,
                            "dimension": _normalize_dimension(r.get("dimension")),
                            "rule": r.get("rule_statement") or r.get("rule") or "",
                            "regex": r.get("regex") or None,
                            "examples": samples[:3],
                        })
            except Exception as exc:
                logger.warning("LLM call failed for %s: %s", col, exc)

        if not col_rules:
            col_rules = _heuristic_rules(col, series)

        # Always tack on a uniqueness rule if the heuristic detected a key,
        # even when the LLM returned rules — this ensures duplicate-UID checks.
        if is_unique_candidate and not any(r["dimension"] == "Uniqueness" for r in col_rules):
            col_rules.append({
                "column": col,
                "dimension": "Uniqueness",
                "rule": f"{col} must be unique across all records",
                "regex": None,
                "examples": samples[:3],
            })
        # Same idea for Completeness when there are nulls.
        if null_pct > 0 and not any(r["dimension"] == "Completeness" for r in col_rules):
            col_rules.append({
                "column": col,
                "dimension": "Completeness",
                "rule": f"{col} should not be blank or null",
                "regex": None,
                "examples": samples[:3],
            })

        all_rules.extend(col_rules)

    return all_rules
