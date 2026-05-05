"""Convert engine dataclasses (ColumnProfile, DuplicateGroup, DataQualityReport)
into JSON-friendly dicts for the API responses.
"""
from __future__ import annotations

import math
from dataclasses import asdict
from typing import Any, Dict, List

import numpy as np
import pandas as pd


def _scrub(value: Any) -> Any:
    """Make a value JSON-safe: handle NaN/Inf, numpy scalars, Timestamps."""
    if isinstance(value, float):
        if math.isnan(value) or math.isinf(value):
            return None
        return value
    if isinstance(value, (np.integer,)):
        return int(value)
    if isinstance(value, (np.floating,)):
        v = float(value)
        if math.isnan(v) or math.isinf(v):
            return None
        return v
    if isinstance(value, np.bool_):
        return bool(value)
    if isinstance(value, (pd.Timestamp,)):
        return value.isoformat()
    if isinstance(value, (np.ndarray,)):
        return [_scrub(v) for v in value.tolist()]
    if isinstance(value, dict):
        return {k: _scrub(v) for k, v in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_scrub(v) for v in value]
    if value is pd.NaT:
        return None
    return value


def column_profile_to_dict(profile: Any) -> Dict[str, Any]:
    if hasattr(profile, "__dict__"):
        d = asdict(profile) if hasattr(profile, "__dataclass_fields__") else dict(profile.__dict__)
    else:
        d = dict(profile)
    return _scrub(d)


def quality_report_to_dict(qr: Any) -> Dict[str, Any]:
    if qr is None:
        return {}
    if hasattr(qr, "__dataclass_fields__"):
        return _scrub(asdict(qr))
    return _scrub(dict(qr.__dict__))


def duplicate_group_to_dict(group: Any) -> Dict[str, Any]:
    if hasattr(group, "__dataclass_fields__"):
        return _scrub(asdict(group))
    return _scrub(dict(group.__dict__))
