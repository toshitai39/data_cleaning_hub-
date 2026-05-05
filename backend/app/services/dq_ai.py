"""1:1 port of features/quality/ui.py AI Regex suggestion (lines 704-803)."""
from __future__ import annotations

import json
import re
from typing import Dict, List, Optional

import pandas as pd

from .azure_openai_config import AzureOpenAIConfig


def _try_llm_suggestion(column: str, sample: List[str], user_question: str) -> Optional[Dict]:
    """Verbatim port of _try_llm_suggestion."""
    try:
        from openai import AzureOpenAI

        endpoint = AzureOpenAIConfig.AZURE_OPENAI_ENDPOINT
        key = AzureOpenAIConfig.AZURE_OPENAI_KEY
        deployment = AzureOpenAIConfig.AZURE_OPENAI_DEPLOYMENT
        api_version = AzureOpenAIConfig.AZURE_OPENAI_API_VERSION or "2024-02-01"
        if not (endpoint and key and deployment):
            return None
        client = AzureOpenAI(azure_endpoint=endpoint, api_key=key, api_version=api_version)
        prompt = (
            f"Column name: {column}\n"
            f"Sample values: {sample[:10]}\n"
            f"User request: {user_question}\n\n"
            "Return ONLY a JSON object with these keys:\n"
            "  mode (one of: Clean, Replace, Extract, Validate, Case, Length)\n"
            "  pattern (regex string, if applicable)\n"
            "  replace (replacement string, if mode is Replace)\n"
            "  case (UPPERCASE / lowercase / Title Case, if mode is Case)\n"
            "  explanation (one-line human description)\n"
        )
        response = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": "You are a data quality expert. Respond only with valid JSON."},
                {"role": "user", "content": prompt},
            ],
            temperature=0,
            max_tokens=300,
        )
        text = response.choices[0].message.content.strip()
        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
        result = json.loads(text)
        if "mode" in result:
            return result
    except Exception:
        pass
    return None


def _heuristic_suggestion(sample: List[str], user_question: str) -> Dict:
    """Verbatim port of _heuristic_suggestion."""
    has_special = any(re.search(r"[^a-zA-Z0-9\s]", v) for v in sample)
    has_underscore = any("_" in v for v in sample)
    if user_question:
        q = user_question.lower()
        if "special" in q and "remove" in q:
            return {"mode": "Clean", "pattern": r"[^a-zA-Z0-9\s]", "explanation": "Remove special characters"}
        if "underscore" in q and "space" in q:
            return {"mode": "Replace", "pattern": "_", "replace": " ", "explanation": "Replace underscores with spaces"}
        if "uppercase" in q or "upper" in q:
            return {"mode": "Case", "case": "UPPERCASE", "explanation": "Convert to UPPERCASE"}
        if "lowercase" in q or "lower" in q:
            return {"mode": "Case", "case": "lowercase", "explanation": "Convert to lowercase"}
        if "title" in q:
            return {"mode": "Case", "case": "Title Case", "explanation": "Convert to Title Case"}
        if ("number" in q or "digit" in q) and ("extract" in q or "only" in q):
            return {"mode": "Extract", "pattern": "[0-9]", "explanation": "Extract only digits"}
        if "email" in q:
            return {
                "mode": "Validate",
                "pattern": r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$",
                "explanation": "Validate email format",
            }
    if has_underscore:
        return {"mode": "Replace", "pattern": "_", "replace": " ", "explanation": "Replace underscores with spaces"}
    if has_special:
        return {"mode": "Clean", "pattern": r"[^a-zA-Z0-9\s]", "explanation": "Remove special characters"}
    return {"mode": "Clean", "pattern": r"[^a-zA-Z0-9\s]", "explanation": "Remove special characters"}


def get_ai_suggestion(df: pd.DataFrame, column: str, user_question: str = "") -> Optional[Dict]:
    sample = df[column].dropna().astype(str).head(20).tolist()
    if not sample:
        return None
    llm = _try_llm_suggestion(column, sample, user_question)
    if llm is not None:
        return llm
    return _heuristic_suggestion(sample, user_question)
