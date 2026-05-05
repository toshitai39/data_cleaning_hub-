"""1:1 port of match-rule + duplicate helpers from features/profiling/ui.py.

Verbatim ports:
- generate_match_rules           (lines 1190-1362)
- find_duplicate_groups          (lines 1365-1383)
- get_duplicate_count_values     (lines 1386-1424)
- safe_get_special_chars         (lines 1427-1433)
"""
from __future__ import annotations

from typing import Any, Dict, List

import pandas as pd


def generate_match_rules(df: pd.DataFrame, profiles: Dict[str, Any]) -> List[Dict[str, Any]]:
    rules: List[Dict[str, Any]] = []
    counter = 1

    analysis: Dict[str, Dict[str, Any]] = {}
    for col, prof in profiles.items():
        total_rows = int(getattr(prof, "total_rows", 0) or 0)
        unique_count = int(getattr(prof, "unique_count", 0) or 0)
        dup_count = max(0, total_rows - unique_count)
        dup_pct = (dup_count / total_rows * 100) if total_rows > 0 else 0
        dtype = getattr(prof, "dtype", "") or ""
        analysis[col] = {
            "null_pct": getattr(prof, "null_percentage", 0),
            "unique_pct": getattr(prof, "unique_percentage", 0),
            "dup_pct": dup_pct,
            "dup_count": dup_count,
            "is_text": dtype == "object",
            "is_num": any(t in dtype for t in ["int", "float"]),
            "avg_len": getattr(prof, "avg_length", 0),
            "max_len": getattr(prof, "max_length", 0),
            "min_len": getattr(prof, "min_length", 0),
            "total_rows": total_rows,
        }

    # EXACT MATCH CANDIDATES
    exact_candidates = []
    for col, a in analysis.items():
        if a["unique_pct"] == 100 or a["dup_count"] == 0:
            continue
        score = 0
        reasons: List[str] = []
        if 95 <= a["unique_pct"] < 100:
            score += 35; reasons.append(f"Near-unique ({a['unique_pct']:.1f}%)")
        elif 80 <= a["unique_pct"] < 95:
            score += 25; reasons.append(f"High uniqueness ({a['unique_pct']:.1f}%)")
        if a["null_pct"] < 1:
            score += 20; reasons.append("Complete data (no nulls)")
        elif a["null_pct"] < 5:
            score += 15; reasons.append("Low null rate")
        if a["is_text"] and a["max_len"] == a["min_len"] and 4 <= a["avg_len"] <= 20:
            score += 25; reasons.append(f"Fixed length ({int(a['avg_len'])} chars)")
        if 0 < a["dup_pct"] < 5:
            score += 15; reasons.append(f"Low duplicates ({a['dup_pct']:.1f}%)")
        if score >= 50 and a["dup_count"] > 0:
            exact_candidates.append({
                "column": col, "score": score, "reasons": reasons,
                "dup_count": a["dup_count"], "unique_pct": a["unique_pct"],
            })

    exact_candidates.sort(key=lambda x: x["score"], reverse=True)
    for cand in exact_candidates[:4]:
        prob = ("Strongest" if cand["score"] >= 85
                else "Very Strong" if cand["score"] >= 75
                else "Strong" if cand["score"] >= 65
                else "Good")
        rules.append({
            "Rule No": f"R{counter:02d}", "Rule Type": "Exact",
            "Columns": cand["column"], "Match Probability": prob,
            "Rationale": f"{'; '.join(cand['reasons'][:2])} | Duplicates: {cand['dup_count']}",
            "Confidence": cand["score"],
        })
        counter += 1

    # FUZZY MATCH CANDIDATES
    fuzzy_candidates = []
    for col, a in analysis.items():
        if not a["is_text"]:
            continue
        score = 0
        reasons = []
        if 30 <= a["unique_pct"] <= 90:
            score += 35; reasons.append(f"Medium uniqueness ({a['unique_pct']:.1f}%)")
        elif 10 <= a["unique_pct"] < 30:
            score += 20; reasons.append(f"Low-medium uniqueness ({a['unique_pct']:.1f}%)")
        if 10 <= a["avg_len"] <= 100:
            score += 25; reasons.append(f"Name/description length ({a['avg_len']:.0f} chars)")
        elif a["avg_len"] > 100:
            score += 15; reasons.append("Long text field")
        name_indicators = ["name", "desc", "title", "product", "customer",
                           "company", "vendor", "supplier", "brand", "item"]
        if any(ind in str(col).lower() for ind in name_indicators):
            score += 25; reasons.append("Name/description column")
        if a["dup_count"] > 1:
            score += 15; reasons.append(f"Has duplicates to match ({a['dup_count']})")
        if score >= 45:
            fuzzy_candidates.append({
                "column": col, "score": score, "reasons": reasons,
                "unique_pct": a["unique_pct"],
            })

    fuzzy_candidates.sort(key=lambda x: x["score"], reverse=True)
    for cand in fuzzy_candidates[:4]:
        prob = ("Strong" if cand["score"] >= 70
                else "Good" if cand["score"] >= 60 else "Medium")
        rules.append({
            "Rule No": f"R{counter:02d}", "Rule Type": "Fuzzy",
            "Columns": cand["column"], "Match Probability": prob,
            "Rationale": "; ".join(cand["reasons"][:3]),
            "Confidence": cand["score"],
        })
        counter += 1

    # COMBINED RULES
    if exact_candidates and fuzzy_candidates:
        for e in exact_candidates[:2]:
            for f in fuzzy_candidates[:3]:
                if e["column"] != f["column"] and len(rules) < 10:
                    score = (e["score"] + f["score"]) / 2
                    prob = ("Enterprise" if score >= 75
                            else "Strong" if score >= 65 else "Good")
                    rules.append({
                        "Rule No": f"R{counter:02d}", "Rule Type": "Combined",
                        "Columns": f"{e['column']} (Exact) + {f['column']} (Fuzzy)",
                        "Match Probability": prob,
                        "Rationale": f"Exact on {e['column']}; Fuzzy match on {f['column']}",
                        "Confidence": score,
                    })
                    counter += 1
                    if len(rules) >= 10:
                        break
            if len(rules) >= 10:
                break

    if not rules and analysis:
        first = list(analysis.keys())[0]
        rules.append({
            "Rule No": "R01", "Rule Type": "Exact", "Columns": first,
            "Match Probability": "Medium", "Rationale": "Default fallback rule",
            "Confidence": 50,
        })

    rules.sort(key=lambda x: x["Confidence"], reverse=True)
    for i, r in enumerate(rules[:10], 1):
        r["Rule No"] = f"R{i:02d}"
    return rules[:10]


def find_duplicate_groups(df: pd.DataFrame, col: str) -> List[Dict[str, Any]]:
    if col not in df.columns:
        return []
    value_counts = df[col].value_counts()
    duplicates = value_counts[value_counts > 1]
    groups: List[Dict[str, Any]] = []
    for val, count in duplicates.head(10).items():
        matching_rows = df[df[col] == val]
        groups.append({
            "value": str(val)[:50],
            "count": int(count),
            "percentage": round((count / len(df)) * 100, 2) if len(df) > 0 else 0,
            "row_indices": matching_rows.index.tolist()[:5],
        })
    return groups


def get_duplicate_count_values(df: pd.DataFrame, col: str, max_items: int | None = 5) -> str:
    if col not in df.columns:
        return "N/A"
    try:
        value_counts = df[col].value_counts(dropna=False)
        duplicates = value_counts[value_counts > 1]
        if len(duplicates) == 0:
            return "No duplicates"
        dup_strings: List[str] = []
        for val, count in duplicates.items():
            if pd.isna(val) or (isinstance(val, str) and val.strip() == ""):
                dup_strings.append(f"Missing Values({count})")
            else:
                val_str = str(val).strip()
                dup_strings.append(f"{val_str}({count})")
        return ", ".join(dup_strings)
    except Exception:
        return "Error"


def safe_get_special_chars(prof: Any) -> List[Dict]:
    try:
        if hasattr(prof, "special_chars") and prof.special_chars:
            return [c for c in prof.special_chars if isinstance(c, dict) and "count" in c]
    except Exception:
        pass
    return []
