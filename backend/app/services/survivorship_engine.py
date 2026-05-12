"""Survivorship — pick the golden record out of a duplicate group.

Given a DataFrame slice for a duplicate group and a survivorship config,
return:

  • the index of the surviving row (the "leader")
  • a per-field merged record (the "golden record" — best value per column
    across the group, not necessarily any one source row)
  • an explanation per column describing which source row contributed
    the value and why

Strategies supported:

  most_complete       record with the most non-null fields wins
  most_recent         record with the latest ``recency_column`` value wins
  field_level_merge   for each column independently, pick the non-null
                      value from the row that survives a per-column tie-
                      breaker (most_complete → most_recent → first row)

All strategies fall back to ``df.iloc[0]`` if their primary signal is
tied or missing.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

import pandas as pd


@dataclass
class GoldenRecord:
    survivor_index: int                              # row index of the leader
    record: Dict[str, Any] = field(default_factory=dict)  # merged values per column
    provenance: Dict[str, Dict[str, Any]] = field(default_factory=dict)  # column → {source_index, reason}


def _non_null_count(row: pd.Series) -> int:
    return int(row.notna().sum())


def _pick_most_complete(df: pd.DataFrame) -> int:
    """Return the integer position (0..len(df)-1) of the most-complete row."""
    counts = df.apply(_non_null_count, axis=1)
    best = counts.idxmax()
    return int(df.index.get_loc(best))


def _pick_most_recent(df: pd.DataFrame, column: Optional[str]) -> int:
    if not column or column not in df.columns:
        return 0
    parsed = pd.to_datetime(df[column], errors="coerce")
    if parsed.notna().sum() == 0:
        return 0
    best = parsed.idxmax()
    return int(df.index.get_loc(best))


def compute_golden_record(
    group_df: pd.DataFrame,
    config: Optional[Dict[str, Any]] = None,
) -> GoldenRecord:
    """Apply a survivorship config to one duplicate group.

    ``group_df`` is a slice of the working DataFrame containing the rows
    that match a single duplicate-group key. ``config`` is a dict shaped
    like the JSON in dedup_rules.json's ``survivorship`` field; missing /
    None falls back to ``most_complete``.
    """
    if group_df is None or len(group_df) == 0:
        return GoldenRecord(survivor_index=-1)

    config = config or {"strategy": "most_complete"}
    strategy = (config.get("strategy") or "most_complete").lower()
    recency_column = config.get("recency_column")

    df = group_df.reset_index(drop=False)
    # ``df.index`` is now 0..N-1; ``df['index']`` is the original index.

    if strategy == "most_recent":
        leader_pos = _pick_most_recent(df, recency_column)
        leader_row = df.iloc[leader_pos]
        return GoldenRecord(
            survivor_index=int(leader_row["index"]),
            record={c: leader_row[c] for c in group_df.columns},
            provenance={
                c: {"source_index": int(leader_row["index"]), "reason": "most_recent"}
                for c in group_df.columns
            },
        )

    if strategy == "most_complete":
        leader_pos = _pick_most_complete(df)
        leader_row = df.iloc[leader_pos]
        return GoldenRecord(
            survivor_index=int(leader_row["index"]),
            record={c: leader_row[c] for c in group_df.columns},
            provenance={
                c: {"source_index": int(leader_row["index"]), "reason": "most_complete"}
                for c in group_df.columns
            },
        )

    # ── field_level_merge ───────────────────────────────────────────
    # Per-column: take the first non-null value from the row that wins
    # the configured priority chain. Default chain: most_complete → most
    # recent. The same "leader row" is computed once to act as the row
    # whose identity becomes the survivor (so we don't accidentally
    # introduce a Frankenstein primary key).
    priority: List[str] = list(config.get("priority", ["most_complete", "most_recent"]))
    leader_pos = 0
    for p in priority:
        if p == "most_complete":
            leader_pos = _pick_most_complete(df)
            break
        if p == "most_recent":
            leader_pos = _pick_most_recent(df, recency_column)
            break
    leader_row = df.iloc[leader_pos]
    leader_idx = int(leader_row["index"])

    record: Dict[str, Any] = {}
    provenance: Dict[str, Dict[str, Any]] = {}
    for col in group_df.columns:
        # Prefer leader's value if it's non-null.
        leader_val = leader_row[col]
        if pd.notna(leader_val):
            record[col] = leader_val
            provenance[col] = {"source_index": leader_idx, "reason": "leader_non_null"}
            continue
        # Otherwise scan the group for the first non-null contributor.
        col_values = group_df[col]
        non_null = col_values.dropna()
        if len(non_null) == 0:
            record[col] = None
            provenance[col] = {"source_index": None, "reason": "all_null"}
            continue
        first_idx = non_null.index[0]
        record[col] = non_null.iloc[0]
        provenance[col] = {
            "source_index": int(first_idx),
            "reason": "first_non_null_in_group",
        }

    return GoldenRecord(
        survivor_index=leader_idx,
        record=record,
        provenance=provenance,
    )


def apply_survivor(
    df: pd.DataFrame,
    member_indices: List[int],
    golden: GoldenRecord,
) -> pd.DataFrame:
    """Apply the golden record to ``df``:

      • the survivor row is updated in-place with merged field values
      • all other members of the duplicate group are dropped

    Returns a NEW DataFrame (caller can ``sess.df = ...``).
    """
    if golden.survivor_index < 0 or len(member_indices) == 0:
        return df

    new_df = df.copy()
    # Write merged values onto the survivor row.
    for col, val in golden.record.items():
        if col not in new_df.columns:
            continue
        new_df.at[golden.survivor_index, col] = val

    # Drop every other member of this group.
    drop_indices = [i for i in member_indices if i != golden.survivor_index]
    if drop_indices:
        new_df = new_df.drop(index=drop_indices)

    return new_df.reset_index(drop=True)
