"""Per-stream behavioural context for downstream analytics.

Every project — whether sourced from SAP, Oracle Fusion, Workday, Snowflake,
or a plain file upload — picks a ``stream_id`` at creation time (customer,
vendor, material, gl_account, employee, cost_center). The flags below are
keyed on **stream_id only**, so the same master-data semantics apply
regardless of source system.

Why this matters: a "customer master" loaded from a CSV behaves
identically to one extracted from SAP for the purpose of identifier
uniqueness — one row per customer, full stop. A "material master" from
either source is typically a join of multiple physical tables (plant /
description / valuation), so the same material number is expected to
repeat across rows.

This module is the single source of truth for those semantic flags so
every consumer (DAMA scorer, rule generator prompts, future dimension
tabs) shares the same understanding. Add a new stream in one place.
"""

from __future__ import annotations

from typing import Any, Dict, Optional

from ..models import Project


# Streams where the primary identifier is expected to repeat across rows
# because the working DataFrame is a join / denormalised view.
# Examples (system-agnostic):
#   material   — same material number per plant and per language line
#   gl_account — same GL account per company code
#   cost_center — same cost centre per controlling area / period
# For these streams, identifier-only duplicates are NOT a quality problem;
# only full-row duplicates count toward the Uniqueness score.
IDENTIFIER_REPEATS_OK_STREAMS = {
    "material",
    "gl_account",
    "cost_center",
}

# Streams where the primary identifier is a strict entity key — one row
# per identifier in the canonical view, full stop. Duplicates of the
# identifier are a hard quality finding regardless of source system.
IDENTIFIER_UNIQUE_STREAMS = {
    "customer",
    "vendor",
    "employee",
}


def build_project_context(project: Optional[Project]) -> Dict[str, Any]:
    """Compact descriptor of the project's master-data context.

    Returns a dict shaped for safe JSON serialisation that downstream
    services (DAMA scorer, rule generator, CDE recommender) can pass to
    the LLM or use to gate logic. Missing project → empty descriptor;
    callers default to the most permissive behaviour.
    """
    if project is None:
        return {
            "system_id": None,
            "system_label": None,
            "stream_id": None,
            "stream_label": None,
            "identifier_repeats_expected": False,
            "is_entity_master": False,
        }
    stream_id = (project.stream_id or "").lower()
    return {
        "system_id": project.system_id,
        "system_label": project.system_label,
        "stream_id": project.stream_id,
        "stream_label": project.stream_label,
        "identifier_repeats_expected": stream_id in IDENTIFIER_REPEATS_OK_STREAMS,
        "is_entity_master": stream_id in IDENTIFIER_UNIQUE_STREAMS,
    }
