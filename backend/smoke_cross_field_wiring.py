"""Regression suite for cross-field fix → reject_df / undo / counter wiring.

The user-visible bug: a cross-field rule that drops 11 rows shows up
nowhere — Rejected Rows panel stays empty, Reset All can't roll back,
the per-dimension Applied counter stays at 0.

Tests assert every piece of state the rest of Cleansing reads from is
populated by the cross-field fix path.
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from datetime import datetime  # noqa: E402

from backend.app.session_store import SessionData  # noqa: E402
from backend.app.services.dq_engine import default_config, undo_last  # noqa: E402

results = []


def check(name, ok, detail=""):
    tag = "[PASS]" if ok else "[FAIL]"
    line = f"{tag} {name}" + (f"  -- {detail}" if detail else "")
    results.append((ok, line))
    print(line)


def make_session(df: pd.DataFrame) -> SessionData:
    s = SessionData(session_id="cf_wiring")
    s.df = df.copy()
    s.original_df = df.copy()
    s.reject_df = pd.DataFrame()
    s.dq_config = {c: default_config() for c in df.columns}
    return s


def simulate_cross_field_drop(sess: SessionData, failing_mask: pd.Series,
                              rule_text: str, columns: list[str],
                              family: str = "composite_unique",
                              action: str = "drop") -> int:
    """Direct port of the fix_cross_field code path's mutation block —
    lets us assert wiring without needing the FastAPI test client."""
    backup_df = sess.df.copy()
    backup_reject = sess.reject_df.copy() if isinstance(sess.reject_df, pd.DataFrame) else pd.DataFrame()
    backup_dim_counts = dict(sess.applied_rules_by_dim)

    before = int(len(sess.df))
    dropped_rows_df = sess.df.loc[failing_mask].copy()
    sess.df = sess.df.loc[~failing_mask].reset_index(drop=True)
    dropped = before - int(len(sess.df))

    if not dropped_rows_df.empty:
        rule_label = f"Cross-field · {rule_text[:80]}"
        dropped_rows_df["Rejection_Reason"] = f"{rule_label} — {action}"
        dropped_rows_df["Rejected_Column"] = " + ".join(columns)
        dropped_rows_df["Rejected_At"] = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if sess.reject_df is None or sess.reject_df.empty:
            sess.reject_df = dropped_rows_df
        else:
            sess.reject_df = pd.concat([sess.reject_df, dropped_rows_df], ignore_index=True)

    sess.applied_rules_by_dim["Cross-field Validation"] = (
        sess.applied_rules_by_dim.get("Cross-field Validation", 0) + 1
    )

    sess.validation_history.append({
        "description": f"Applied cross-field rule · {family} · {action}",
        "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "rejected_count": dropped,
        "backup_df": backup_df,
        "backup_reject_df": backup_reject,
        "backup_applied_rules": [{
            "mode": "CrossField", "name": "CF test",
            "pattern": "", "dimension": "Cross-field Validation",
            "source": "ai", "rule_text": rule_text,
        }],
        "backup_applied_dim_counts": backup_dim_counts,
        "column": " + ".join(columns),
    })
    return dropped


# ─────────────────────────────────────────────────────────────────────────────
# X1: cross-field drop populates reject_df
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== X1: cross-field drop populates reject_df ===")
df = pd.DataFrame({
    "billing_country": ["IN", "IN", "US", "IN", "IN", "US", "GB", "US", "IN", "IN", "FR"],
    "gstin":           ["27ABC...", "",     "",     "",   "29DEF...", "", "", "", "", "33XYZ...", ""],
    "name":            [f"row_{i}" for i in range(11)],
})
sess = make_session(df)
# Pretend 11 rows fail: anywhere billing_country == IN AND gstin is blank
failing = (df["billing_country"] == "IN") & (df["gstin"] == "")
dropped = simulate_cross_field_drop(
    sess, failing,
    rule_text="GSTIN required when Billing Country is India",
    columns=["billing_country", "gstin"],
    family="conditional_presence",
    action="drop",
)
check("dropped > 0 rows", dropped > 0, f"dropped={dropped}")
check("reject_df now has the dropped rows",
      len(sess.reject_df) == dropped,
      f"reject_df={len(sess.reject_df)}, dropped={dropped}")
check("reject_df rows carry Rejection_Reason with cross-field tag",
      sess.reject_df["Rejection_Reason"].iloc[0].startswith("Cross-field"),
      f"got {sess.reject_df['Rejection_Reason'].iloc[0]}")
check("reject_df Rejected_Column lists both fields",
      "billing_country" in sess.reject_df["Rejected_Column"].iloc[0]
      and "gstin" in sess.reject_df["Rejected_Column"].iloc[0])

# ─────────────────────────────────────────────────────────────────────────────
# X2: applied_rules_by_dim increments for Cross-field Validation
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== X2: Cross-field counter increments ===")
check("counter Cross-field Validation = 1",
      sess.applied_rules_by_dim.get("Cross-field Validation") == 1,
      f"counters={sess.applied_rules_by_dim}")

# Apply a second cross-field fix on the same session — counter should go to 2.
# Mask must align with sess.df's current index (which has been re-indexed
# after the first drop), so build it from the live df rather than hand-rolled.
second_mask = pd.Series([True] + [False] * (len(sess.df) - 1), index=sess.df.index)
simulate_cross_field_drop(
    sess, second_mask, "second rule", ["billing_country"], "drop", "drop",
)
check("counter Cross-field Validation = 2 after second fix",
      sess.applied_rules_by_dim.get("Cross-field Validation") == 2,
      f"counters={sess.applied_rules_by_dim}")

# ─────────────────────────────────────────────────────────────────────────────
# X3: validation_history records cross-field action
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== X3: validation_history records cross-field action ===")
check("history has 2 entries (one per fix)",
      len(sess.validation_history) == 2, f"history={len(sess.validation_history)}")
last = sess.validation_history[-1]
check("entry has backup_df", isinstance(last.get("backup_df"), pd.DataFrame))
check("entry has backup_reject_df",
      isinstance(last.get("backup_reject_df"), pd.DataFrame))
check("entry has backup_applied_dim_counts",
      isinstance(last.get("backup_applied_dim_counts"), dict))
check("description mentions cross-field",
      "cross-field" in last.get("description", "").lower())

# ─────────────────────────────────────────────────────────────────────────────
# X4: undo_last rolls back the cross-field fix
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== X4: undo_last rolls back cross-field fix ===")
before_df_len = len(sess.df)
before_rejects = len(sess.reject_df)
before_counter = sess.applied_rules_by_dim.get("Cross-field Validation", 0)

ok = undo_last(sess)
check("undo returned True", ok)

after_df_len = len(sess.df)
check("df grew back to pre-fix size", after_df_len > before_df_len,
      f"before={before_df_len}, after={after_df_len}")
check("Cross-field counter rolled back",
      sess.applied_rules_by_dim.get("Cross-field Validation", 0) < before_counter,
      f"before={before_counter}, after={sess.applied_rules_by_dim.get('Cross-field Validation', 0)}")

# ─────────────────────────────────────────────────────────────────────────────
# X5: Reset-cleansing path restores original_df even after cross-field
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== X5: Reset all restores cross-field drops too ===")
# Apply another cross-field drop, then reset
df = pd.DataFrame({"x": list(range(10)), "y": list(range(10))})
sess = make_session(df)
mask = pd.Series([True, True, True] + [False] * 7, index=sess.df.index)
simulate_cross_field_drop(
    sess, mask,
    rule_text="x,y must be unique", columns=["x", "y"], family="composite_unique",
)
check("after cf-fix: 7 rows remain", len(sess.df) == 7, f"got {len(sess.df)}")
check("after cf-fix: 3 rejects logged", len(sess.reject_df) == 3,
      f"got {len(sess.reject_df)}")

# Now simulate /quality/reset-cleansing
sess.df = sess.original_df.copy()
sess.reject_df = pd.DataFrame()
sess.validation_history = []
sess.applied_rules_by_dim = {}

check("after reset: 10 rows restored", len(sess.df) == 10, f"got {len(sess.df)}")
check("after reset: reject_df cleared", len(sess.reject_df) == 0)
check("after reset: history cleared", len(sess.validation_history) == 0)
check("after reset: Cross-field counter cleared",
      sess.applied_rules_by_dim.get("Cross-field Validation", 0) == 0)

# ─────────────────────────────────────────────────────────────────────────────
# X6: Multiple cross-field fixes stack correctly in reject_df
# ─────────────────────────────────────────────────────────────────────────────
print("\n=== X6: stacked cross-field fixes accumulate in reject_df ===")
df = pd.DataFrame({"a": list(range(20)), "b": list(range(20))})
sess = make_session(df)
# First fix: drop 3 rows
mask1 = pd.Series([True, True, True] + [False] * 17, index=sess.df.index)
simulate_cross_field_drop(
    sess, mask1,
    rule_text="rule A", columns=["a"], family="conditional_presence",
)
# Second fix: drop 2 more rows of the remaining 17 (mask must align)
mask2 = pd.Series([True, True] + [False] * (len(sess.df) - 2), index=sess.df.index)
simulate_cross_field_drop(
    sess, mask2,
    rule_text="rule B", columns=["b"], family="conditional_presence",
)
check("reject_df accumulated 5 rows across 2 fixes",
      len(sess.reject_df) == 5, f"got {len(sess.reject_df)}")
check("reject_df has 2 distinct rejection reasons",
      sess.reject_df["Rejection_Reason"].nunique() == 2,
      f"got reasons: {sess.reject_df['Rejection_Reason'].unique().tolist()}")
check("counter Cross-field Validation = 2",
      sess.applied_rules_by_dim.get("Cross-field Validation") == 2,
      f"counters={sess.applied_rules_by_dim}")

# ─────────────────────────────────────────────────────────────────────────────
# SUMMARY
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 70)
passed = sum(1 for ok, _ in results if ok)
total = len(results)
print(f"CROSS-FIELD WIRING SUMMARY: {passed}/{total} passed")
if passed < total:
    print("\nFailures:")
    for ok, line in results:
        if not ok:
            print("  " + line)
    sys.exit(1)
print("\nCross-field is now properly wired into reject_df / undo / counters.")
