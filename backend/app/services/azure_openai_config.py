"""Azure OpenAI configuration ported 1:1 from features/profiling/ui.py.

Streamlit's `st.secrets` is replaced with .streamlit/secrets.toml file parsing
and environment variable fallback. Same field names, same defaults.
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional


_PROJECT_ROOT = Path(__file__).resolve().parents[3]
_SECRETS_PATH = _PROJECT_ROOT / ".streamlit" / "secrets.toml"


@lru_cache(maxsize=1)
def _read_secrets() -> Dict[str, str]:
    if not _SECRETS_PATH.exists():
        return {}
    out: Dict[str, str] = {}
    try:
        text = _SECRETS_PATH.read_text(encoding="utf-8")
    except Exception:
        return {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        m = re.match(r'([A-Za-z0-9_]+)\s*=\s*"([^"]*)"', line)
        if m:
            out[m.group(1)] = m.group(2)
        else:
            m2 = re.match(r"([A-Za-z0-9_]+)\s*=\s*(\d+)", line)
            if m2:
                out[m2.group(1)] = m2.group(2)
    return out


def _get(key: str, default: Optional[str] = None) -> Optional[str]:
    return os.environ.get(key) or _read_secrets().get(key) or default


class AzureOpenAIConfig:
    """Mirror of features/profiling/ui.py AzureOpenAIConfig (lines 45-67)."""

    AZURE_OPENAI_ENDPOINT = _get("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_KEY = _get("AZURE_OPENAI_KEY")
    AZURE_OPENAI_DEPLOYMENT = _get("AZURE_OPENAI_DEPLOYMENT")
    AZURE_OPENAI_API_VERSION = _get("AZURE_OPENAI_API_VERSION")

    MAX_REQUESTS_PER_MINUTE = int(_get("AZURE_OPENAI_MAX_RPM", "60") or 60)
    MAX_TOKENS_PER_MINUTE = int(_get("AZURE_OPENAI_MAX_TPM", "40000") or 40000)

    @classmethod
    def validate(cls) -> List[str]:
        missing: List[str] = []
        if not cls.AZURE_OPENAI_ENDPOINT:
            missing.append("AZURE_OPENAI_ENDPOINT")
        if not cls.AZURE_OPENAI_KEY:
            missing.append("AZURE_OPENAI_KEY")
        if not cls.AZURE_OPENAI_DEPLOYMENT:
            missing.append("AZURE_OPENAI_DEPLOYMENT")
        return missing
