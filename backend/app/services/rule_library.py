"""Read-only access to the shipped JSON rule library.

For v0 the library is one file (backend/library/dedup_rules.json). When
the library outgrows a single file, swap this for a DB-backed lookup —
the public functions (``list_dedup_rules`` etc.) stay the same.
"""
from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)

_LIBRARY_DIR = Path(__file__).resolve().parents[3] / "backend" / "library"


def _load_json(path: Path) -> Dict[str, Any]:
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        logger.error("Could not load library file %s: %s", path, exc)
        return {}


def list_dedup_rules(stream: Optional[str] = None) -> List[Dict[str, Any]]:
    data = _load_json(_LIBRARY_DIR / "dedup_rules.json")
    rules: List[Dict[str, Any]] = data.get("rules", [])
    if stream:
        rules = [r for r in rules if r.get("stream") == stream]
    return rules


def get_dedup_rule(rule_id: str) -> Optional[Dict[str, Any]]:
    for r in list_dedup_rules():
        if r.get("id") == rule_id:
            return r
    return None
