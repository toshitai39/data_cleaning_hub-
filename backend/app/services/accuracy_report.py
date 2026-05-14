"""DAMA Accuracy deep-dive — Phase 6 of the Data Profiling rebuild.

Maps cross-field validation rules from ``sess.ai_validation_rules`` into
the per-rule violation report stewards expect:

  Summary block:
     Total rules · Total violations · Rules that pass · Rules that fail · Pass rate

  Per-rule table:
     # · Rule statement · Columns involved · Issues found · Status

  Sample failing rows: drill-down with the rule's example output.

The numbers here aren't recomputed from scratch — the cross-field engine
already evaluated each rule when ``Generate AI Rules`` ran, so we just
surface those results in a steward-friendly layout. If no cross-field
rules exist yet, returns a ``needs_rules`` flag so the frontend can show
a one-click "Run Rule Generator" CTA.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd


def _parse_columns(value: Any) -> List[str]:
    """Rule rows store the involved columns as a comma-separated string."""
    if value is None:
        return []
    if isinstance(value, list):
        return [str(c).strip() for c in value if str(c).strip()]
    text = str(value).strip()
    if not text or text.lower() == "nan":
        return []
    return [c.strip() for c in text.split(",") if c.strip()]


def compute_accuracy_report(
    df: pd.DataFrame,
    ai_validation_rules: Optional[pd.DataFrame],
    glossary: Optional[Dict[str, Any]] = None,
    project_context: Optional[Dict[str, Any]] = None,
) -> Dict[str, Any]:
    """Build the Accuracy deep-dive from the cross-field rules cache.

    Shape:

        {
          "needs_rules": bool,         # true when no cross-field rules exist
          "summary": {
              "total_rules":   N,
              "rules_passing": N,
              "rules_failing": N,
              "total_violations": N,
              "pass_rate":     0.0–1.0,
              "rows_evaluated": N,
          },
          "rules": [
              {
                "id":           1,
                "rule_text":    "Effective date must precede expiry date",
                "columns":      ["effective_date", "expiry_date"],
                "issues_found": 17,
                "validity_rate": 0.985,
                "status":       "Failing" | "Passing",
                "example":      "Row 241: 2024-09-30 > 2024-08-15",
                "validation_expression": "...",
              },
              ...
          ],
          "project_context": {...},
        }
    """
    rows = int(len(df)) if df is not None else 0
    ctx = project_context or {}

    if not isinstance(ai_validation_rules, pd.DataFrame) or ai_validation_rules.empty:
        return {
            "needs_rules": True,
            "summary": {
                "total_rules": 0, "rules_passing": 0, "rules_failing": 0,
                "total_violations": 0, "pass_rate": 0.0, "rows_evaluated": rows,
            },
            "rules": [],
            "project_context": ctx,
        }

    # Cross-field rules only — single-column rules are policed by Validation
    # and Completeness; we don't want them double-counted here.
    dim_col = "Dimension"
    if dim_col not in ai_validation_rules.columns:
        return {
            "needs_rules": True,
            "summary": {
                "total_rules": 0, "rules_passing": 0, "rules_failing": 0,
                "total_violations": 0, "pass_rate": 0.0, "rows_evaluated": rows,
            },
            "rules": [],
            "project_context": ctx,
        }
    cf_mask = ai_validation_rules[dim_col].astype(str).str.lower().str.contains("cross", na=False)
    cf_rules = ai_validation_rules[cf_mask]
    if cf_rules.empty:
        return {
            "needs_rules": True,
            "summary": {
                "total_rules": 0, "rules_passing": 0, "rules_failing": 0,
                "total_violations": 0, "pass_rate": 0.0, "rows_evaluated": rows,
            },
            "rules": [],
            "project_context": ctx,
        }

    rules_out: List[Dict[str, Any]] = []
    total_violations = 0
    rules_failing = 0
    rules_passing = 0

    for idx, (_, row) in enumerate(cf_rules.iterrows(), start=1):
        rule_text = str(
            row.get("Data Quality Rule") or row.get("Rule") or ""
        ).strip()
        cols = _parse_columns(
            row.get("Columns") or row.get("Cross-field Columns") or row.get("Column")
        )
        issues = int(row.get("Issues Found", 0) or 0)
        example = str(row.get("Issues Found Example", "") or "").strip()
        expr = str(row.get("Validation Expression", "") or "").strip()
        rate = (rows - issues) / rows if rows else 0.0
        status = "Passing" if issues == 0 else "Failing"
        if issues == 0:
            rules_passing += 1
        else:
            rules_failing += 1
            total_violations += issues

        rules_out.append({
            "id": idx,
            "rule_text": rule_text,
            "columns": cols,
            "issues_found": issues,
            "validity_rate": round(rate, 4),
            "status": status,
            "example": example,
            "validation_expression": expr,
        })

    # Failing rules first so the steward sees the actionable items at top.
    rules_out.sort(key=lambda r: (r["status"] == "Passing", -r["issues_found"]))

    total = len(rules_out)
    pass_rate = (rules_passing / total) if total else 0.0
    return {
        "needs_rules": False,
        "summary": {
            "total_rules": total,
            "rules_passing": rules_passing,
            "rules_failing": rules_failing,
            "total_violations": total_violations,
            "pass_rate": round(pass_rate, 4),
            "rows_evaluated": rows,
        },
        "rules": rules_out,
        "project_context": ctx,
    }
