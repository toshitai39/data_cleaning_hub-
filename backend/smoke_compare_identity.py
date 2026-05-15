"""Regression suite for the misleading "Backfilled" / "Modified" bug.

User scenario: applied Completeness "must not be blank" rules that
dropped rows from the middle of the dataset. The Compare page showed
surviving rows as "Modified" or "Backfilled" instead of correctly
showing the gone rows as "Removed".

Root cause: apply_column_rules used reset_index(drop=True) after
filtering, destroying row identity. compare_engine then aligned the
two views POSITIONALLY (.iloc[i] vs .iloc[i]), so surviving row 0
got compared against original row 0 even when that original row had
been DROPPED — and the new row 0 in current was actually originally
row 5. Every comparison was nonsense.

These tests assert:
  - apply_column_rules preserves index labels (no reset)
  - compare_engine aligns by INDEX label, not by position
  - per_column_changes counts only TRUE cell modifications,
    not rows-that-got-dropped-and-shifted
  - cell_diff correctly tags removed rows as "removed", not "modified"
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from backend.app.session_store import SessionData  # noqa: E402
from backend.app.services.dq_engine import (  # noqa: E402
    apply_column_rules, default_config,
)
from backend.app.services.compare_engine import (  # noqa: E402
    stats, count_modified_cells, per_column_changes, cell_diff,
)

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


def make_session(df: pd.DataFrame) -> SessionData:
    s = SessionData(session_id="cmp-identity")
    s.df = df.copy()
    s.original_df = df.copy()
    s.reject_df = pd.DataFrame()
    s.dq_config = {c: default_config() for c in df.columns}
    return s


# ─────────────────────────────────────────────────────────────────────────────
# THE USER'S BUG REPRODUCED
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== Reproducing the user's bug scenario ===")
# 12 rows of customer data, where Phone is blank for some rows in the
# middle. Apply a Completeness "must not be blank" rule on Phone →
# rows 3, 5, 8, 11 get DROPPED. The remaining 8 rows are UNCHANGED.
df = pd.DataFrame({
    "name":  ["Acme", "Globex", "Wayne", "Stark", "Umbrella",
              "Cyber", "Initech", "Soylent", "Tyrell", "OmniCorp",
              "Massive", "Vandelay"],
    "phone": ["111", "222", "333", "",   "444",
              "",    "555", "666", "",   "777",
              "888", ""],
    "city":  ["NYC", "Berlin", "Gotham", "NYC", "Raccoon",
              "LA",  "Scranton", "NYC", "LA", "Detroit",
              "Manhattan", "NYC"],
})

sess = make_session(df)
sess.dq_config["phone"]["applied_rules"] = [{
    "name": "Phone not blank", "mode": "Validate",
    "pattern": r"^(?=.*\S).*$",
    "dimension": "Completeness", "source": "ai",
}]
applied, rejected = apply_column_rules(sess, "phone")

check("4 rows dropped (rows 3, 5, 8, 11)", rejected == 4, f"rejected={rejected}")
check("8 rows remain", len(sess.df) == 8, f"len={len(sess.df)}")

# ─────────────────────────────────────────────────────────────────────────────
# T1: index labels preserved (THE root cause fix)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T1: apply_column_rules preserves pandas index labels ===")
expected_kept_labels = {0, 1, 2, 4, 6, 7, 9, 10}  # everything except 3, 5, 8, 11
actual_labels = set(sess.df.index.tolist())
check("surviving rows keep their original labels (no reset_index)",
      actual_labels == expected_kept_labels,
      f"got {actual_labels}, expected {expected_kept_labels}")

# ─────────────────────────────────────────────────────────────────────────────
# T2: count_modified_cells reports ZERO (no cells were modified — rows dropped)
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T2: count_modified_cells correctly returns 0 (no cell edits) ===")
modified = count_modified_cells(sess.original_df, sess.df)
check("zero cells modified (only row drops)", modified == 0,
      f"got {modified} modified cells")

# ─────────────────────────────────────────────────────────────────────────────
# T3: per_column_changes returns NO change ledger entries
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T3: per_column_changes ledger is empty for pure drops ===")
ledger = per_column_changes(sess.original_df, sess.df)
check("no CDEs touched (rows dropped, not modified)",
      ledger["cdes_touched"] == 0, f"got {ledger['cdes_touched']}")
check("total_modified_cells = 0", ledger["total_modified_cells"] == 0,
      f"got {ledger['total_modified_cells']}")
check("rows_removed = 4", ledger["rows_removed"] == 4,
      f"got {ledger['rows_removed']}")
check("ledger.columns is empty list",
      ledger["columns"] == [], f"got {ledger['columns']}")

# ─────────────────────────────────────────────────────────────────────────────
# T4: cell_diff correctly tags dropped rows as "removed", not "modified"
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T4: cell_diff tags dropped rows as 'removed' ===")
diff = cell_diff(sess.original_df, sess.df, ["name", "phone", "city"],
                 start_row=0, num_rows=12)
removed_in_diff = [r for r in diff["rows"] if r["row_status"] == "removed"]
modified_in_diff = [r for r in diff["rows"] if r["row_status"] != "removed"
                    and any(f == "modified" for f in r["cell_flags"].values())]
check("4 rows tagged as 'removed' in diff",
      len(removed_in_diff) == 4, f"got {len(removed_in_diff)}")
check("0 cells tagged as 'modified' (all surviving rows are unchanged)",
      len(modified_in_diff) == 0,
      f"got {len(modified_in_diff)} modified rows: {[r['row_index'] for r in modified_in_diff]}")
removed_labels = sorted(r["row_index"] for r in removed_in_diff)
check("removed labels are 3, 5, 8, 11", removed_labels == [3, 5, 8, 11],
      f"got {removed_labels}")

# ─────────────────────────────────────────────────────────────────────────────
# T5: stats: row_change reflects drop, modified_cells = 0
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T5: stats top-line numbers are correct ===")
s = stats(sess.original_df, sess.df)
check("original_rows = 12", s["original_rows"] == 12)
check("modified_rows = 8", s["modified_rows"] == 8)
check("row_change = -4", s["row_change"] == -4)
check("modified_cells = 0 (drops, not edits)",
      s["modified_cells"] == 0, f"got {s['modified_cells']}")

# ─────────────────────────────────────────────────────────────────────────────
# T6: mixed scenario — drops AND genuine cell edits
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T6: drop + transform scenario detects each correctly ===")
df2 = pd.DataFrame({
    "code":    ["A1", "B2", "C3", "D4", "E5"],
    "country": ["india", "USA", "uk", "INDIA", "germany"],
})
sess2 = make_session(df2)
# First, drop rows where code is "C3"
sess2.dq_config["code"]["applied_rules"] = [{
    "name": "Code must not be C3", "mode": "Validate",
    "pattern": r"^[^C].*$", "dimension": "Validation", "source": "ai",
}]
apply_column_rules(sess2, "code")
check("after drop: 4 rows remain", len(sess2.df) == 4, f"got {len(sess2.df)}")

# Now uppercase country on the remaining rows
sess2.dq_config["country"]["applied_rules"] = [{
    "name": "uppercase country", "mode": "Case",
    "case": "UPPERCASE", "dimension": "Standardisation", "source": "ai",
}]
apply_column_rules(sess2, "country")

# Verify: 1 row dropped (C3), and country cells got uppercased.
# Survivors after drop (indices 0, 1, 3, 4): A1, B2, D4, E5
# country values:  india,  USA,  INDIA,  germany
# after uppercase: INDIA,  USA,  INDIA,  GERMANY
# Diff: only india→INDIA and germany→GERMANY changed.  USA and INDIA
# were already uppercase. So exactly 2 cells changed.
ledger = per_column_changes(sess2.original_df, sess2.df)
check("ledger reports 1 row removed", ledger["rows_removed"] == 1,
      f"got {ledger['rows_removed']}")
country_entry = next((c for c in ledger["columns"] if c["column"] == "country"), None)
check("country entry exists in ledger",
      country_entry is not None,
      f"columns: {[c['column'] for c in ledger['columns']]}")
if country_entry:
    check("2 country cells changed (USA + INDIA were already upper)",
          country_entry["changed"] == 2, f"got {country_entry['changed']}")
    check("classified as Standardised",
          "Standardised" in country_entry["change_type"],
          f"got {country_entry['change_type']}")

# code column should NOT appear in ledger (it had drops but no cell edits)
code_entry = next((c for c in ledger["columns"] if c["column"] == "code"), None)
check("code (only drops, no edits) NOT in ledger", code_entry is None,
      f"got {code_entry}")

# ─────────────────────────────────────────────────────────────────────────────
# T7: cell_diff windowing still works with non-contiguous indices
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T7: cell_diff windowing on non-contiguous indices ===")
diff_window = cell_diff(sess.original_df, sess.df, ["name", "phone"],
                        start_row=0, num_rows=6)
check("window 0..6 returns 6 rows", len(diff_window["rows"]) == 6,
      f"got {len(diff_window['rows'])}")
# Window should contain labels 0..5 (union of orig + curr indices, sorted)
labels = [r["row_index"] for r in diff_window["rows"]]
check("window labels are 0..5", labels == [0, 1, 2, 3, 4, 5],
      f"got {labels}")
# Of these, rows 3 and 5 should be 'removed'
removed_in_window = [r for r in diff_window["rows"] if r["row_status"] == "removed"]
check("rows 3 and 5 are 'removed' in this window",
      sorted(r["row_index"] for r in removed_in_window) == [3, 5],
      f"got {[r['row_index'] for r in removed_in_window]}")

# ─────────────────────────────────────────────────────────────────────────────
# T8: duplicates engine also preserves index
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T8: duplicates remove_exact preserves index ===")
from backend.app.services.duplicates_engine import remove_exact

df3 = pd.DataFrame({"a": [1, 1, 2, 2, 3], "b": ["x", "x", "y", "y", "z"]})
sess3 = make_session(df3)
removed = remove_exact(sess3, subset=["a", "b"], keep="first")
check("removed 2 duplicate rows", removed == 2, f"got {removed}")
expected_kept = {0, 2, 4}  # first occurrences
actual_kept = set(sess3.df.index.tolist())
check("dedupe preserves index labels of kept rows",
      actual_kept == expected_kept, f"got {actual_kept}")

ledger3 = per_column_changes(sess3.original_df, sess3.df)
check("dedupe scenario: no cell modifications reported",
      ledger3["total_modified_cells"] == 0,
      f"got {ledger3['total_modified_cells']}")
check("dedupe scenario: 2 rows_removed reported",
      ledger3["rows_removed"] == 2, f"got {ledger3['rows_removed']}")

# ─────────────────────────────────────────────────────────────────────────────
# T9: stale-state detector catches pre-fix sessions
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== T9: detect_stale_state flags reset-index sessions ===")
from backend.app.services.compare_engine import _detect_stale_state

# Simulate a pre-fix session: original has indices 0..11, current has
# indices 0..7 (contiguous after reset_index — broken alignment)
orig = pd.DataFrame({"x": list(range(12))})
curr_broken = pd.DataFrame({"x": list(range(8))})  # contiguous 0..7
curr_broken.index = range(8)  # explicit RangeIndex
check("detects broken state (contiguous curr indices, smaller than orig)",
      _detect_stale_state(orig, curr_broken), "should be True")

# Healthy state: current has non-contiguous indices (rows dropped from middle)
curr_healthy = pd.DataFrame({"x": [0, 1, 4, 5, 7]}, index=[0, 1, 4, 5, 7])
check("healthy state (non-contiguous indices) is NOT flagged",
      not _detect_stale_state(orig, curr_healthy), "should be False")

# Same size: not stale
check("same-size frames are NOT flagged",
      not _detect_stale_state(orig, orig.copy()), "should be False")

# stats() exposes the flag
s_stale = stats(orig, curr_broken)
check("stats() exposes stale_state=True for broken session",
      s_stale.get("stale_state") is True, f"got {s_stale.get('stale_state')}")

s_clean = stats(orig, curr_healthy)
check("stats() exposes stale_state=False for healthy session",
      s_clean.get("stale_state") is False, f"got {s_clean.get('stale_state')}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"COMPARE-IDENTITY SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nCompare engine now correctly uses row identity, not position.")
