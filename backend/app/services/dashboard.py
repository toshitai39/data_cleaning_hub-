"""1:1 port of features/dashboard/ui.py helpers — _collect_top_issues."""
from __future__ import annotations

from typing import Any, Dict, List, Tuple


def collect_top_issues(
    profiles: Dict[str, Any],
    quality_report: Any,
    missing_pct: float,
    dup_rows: int,
    total_rows: int,
) -> List[Dict[str, str]]:
    """Verbatim port of features/dashboard/ui.py:_collect_top_issues.

    Returns list of {severity, message} dicts (sorted critical → warning → info).
    """
    issues: List[Tuple[str, str]] = []

    if missing_pct > 20:
        issues.append(("critical", f"High missing data rate: {missing_pct}% of cells are empty"))
    elif missing_pct > 5:
        issues.append(("warning", f"Missing data: {missing_pct}% of cells are empty"))

    if dup_rows > 0:
        dup_pct = round(dup_rows / max(total_rows, 1) * 100, 1)
        if dup_pct > 10:
            issues.append(("critical", f"{dup_rows:,} duplicate rows ({dup_pct}%)"))
        else:
            issues.append(("warning", f"{dup_rows:,} duplicate rows ({dup_pct}%)"))

    for col_name, p in profiles.items():
        if getattr(p, "risk_level", "Low") == "High":
            issues.append((
                "critical",
                f"Column '{col_name}' has HIGH risk (score {getattr(p, 'risk_score', 0)})",
            ))
        if getattr(p, "null_percentage", 0) > 50:
            issues.append(("warning", f"Column '{col_name}' is more than 50% null"))
        for violation in getattr(p, "business_rule_violations", []) or []:
            issues.append(("info", f"'{col_name}': {violation}"))

    issues.sort(key=lambda x: {"critical": 0, "warning": 1, "info": 2}.get(x[0], 3))
    return [{"severity": s, "message": m} for s, m in issues]


def collect_risk_counts(profiles: Dict[str, Any]) -> Dict[str, int]:
    counts = {"Low": 0, "Medium": 0, "High": 0}
    for p in profiles.values():
        lvl = getattr(p, "risk_level", "Low")
        counts[lvl] = counts.get(lvl, 0) + 1
    return counts
