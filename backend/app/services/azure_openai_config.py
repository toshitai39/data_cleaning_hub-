"""Azure OpenAI configuration.

Loads credentials from (in priority order):
  1. Real environment variables (e.g. set in CI/CD or shell)
  2. .env file in the project root (gitignored — safe for local dev)
  3. Legacy .streamlit/secrets.toml (backward compat)

Never hardcode credentials here.  Put them in .env (see .env.example).
"""
from __future__ import annotations

import os
import re
from functools import lru_cache
from pathlib import Path
from typing import Dict, List, Optional

from dotenv import load_dotenv

_PROJECT_ROOT = Path(__file__).resolve().parents[3]

# Load .env once at import time (no-op if file is absent)
load_dotenv(_PROJECT_ROOT / ".env", override=False)

_SECRETS_PATH = _PROJECT_ROOT / ".streamlit" / "secrets.toml"


@lru_cache(maxsize=1)
def _read_secrets() -> Dict[str, str]:
    """Legacy: read .streamlit/secrets.toml as a flat key=value file."""
    if not _SECRETS_PATH.exists():
        return {}
    out: Dict[str, str] = {}
    try:
        text = _SECRETS_PATH.read_text(encoding="utf-8")
    except Exception:
        return {}
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#") or line.startswith("["):
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
    # os.environ already has .env values merged by load_dotenv above
    return os.environ.get(key) or _read_secrets().get(key) or default


class AzureOpenAIConfig:
    AZURE_OPENAI_ENDPOINT   = _get("AZURE_OPENAI_ENDPOINT")
    AZURE_OPENAI_KEY        = _get("AZURE_OPENAI_KEY")
    AZURE_OPENAI_DEPLOYMENT = _get("AZURE_OPENAI_DEPLOYMENT")
    AZURE_OPENAI_API_VERSION = _get("AZURE_OPENAI_API_VERSION", "2024-12-01-preview")

    MAX_REQUESTS_PER_MINUTE = int(_get("AZURE_OPENAI_MAX_RPM", "60") or 60)
    MAX_TOKENS_PER_MINUTE   = int(_get("AZURE_OPENAI_MAX_TPM", "40000") or 40000)

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
