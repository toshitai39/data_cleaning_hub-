"""Cross-field rule classifier and executor.

Cross-field rules involve two or more columns from a single row. The Rule
Generator emits them as English sentences ("vat_no must start with the
2-letter ISO code stored in country"). This module classifies each rule
into one of four mechanical families by pattern-matching the rule text,
then evaluates the family against a DataFrame.

Rules that match no family fall through to a caller-supplied LLM
translator (see ``llm_translator``) which is responsible for producing a
safe pandas expression. A rule that fails both classification and LLM
translation is left flagged for manual review.

The module is intentionally column-agnostic: family parsers identify
columns by reading the rule text and intersecting candidate names with
``df.columns``. No hardcoded column names anywhere.
"""
from __future__ import annotations

import ast
import json
import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Tuple

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)


@dataclass
class CrossFieldResult:
    """Outcome of evaluating one cross-field rule.

    Attributes:
        family: identifier of the rule family that matched, or
            ``"unparsed"`` / ``"llm"`` / ``"manual"``.
        count: number of failing rows in the dataset (0 if compliant).
        example: short human-readable description of the failures.
        expression: structured representation of the check that ran. This
            is what we put in the ``Validation Expression`` column so the
            frontend and downstream consumers can see what actually
            executed (rather than the original English).
        columns: the columns the rule actually evaluated against.
        failing_mask: boolean Series aligned with the dataframe index
            marking rows that violate the rule. Set by every parser when
            ``count > 0``. ``None`` for ``family == "manual"`` because the
            rule was not actually evaluated. The caller uses this mask to
            extract failing rows or apply automated fixes — it must NEVER
            be re-derived in client code, which is why we store it here.
    """
    family: str
    count: int
    example: str
    expression: str
    columns: List[str] = field(default_factory=list)
    failing_mask: Optional[pd.Series] = field(default=None, repr=False)


# ─────────────────────────────────────────────────────────────────────────
# Helpers shared by family parsers
# ─────────────────────────────────────────────────────────────────────────

def _detect_columns_in_text(rule_text: str, all_columns: List[str]) -> List[str]:
    """Find every column name that appears as a token in the rule text.

    Match is whole-word, case-insensitive. The return order is the order
    in which the names appear in ``rule_text`` (left to right) — useful
    when the family cares which column is the "subject" vs. "context".
    """
    if not all_columns:
        return []
    # Sort by length desc so longer names win when names share a prefix
    # (avoids matching "name" when "company_name" is intended).
    cols_by_priority = sorted(all_columns, key=len, reverse=True)
    found_with_pos: List[Tuple[int, str]] = []
    seen: set = set()
    for col in cols_by_priority:
        if col in seen:
            continue
        # Word-boundary match using a regex escape; column names can
        # legally contain underscores and digits, both of which \b allows.
        pattern = r"\b" + re.escape(col) + r"\b"
        m = re.search(pattern, rule_text, flags=re.IGNORECASE)
        if m:
            found_with_pos.append((m.start(), col))
            seen.add(col)
    found_with_pos.sort()
    return [c for _, c in found_with_pos]


def _extract_value_list(rule_text: str) -> Optional[List[str]]:
    """Pull a literal value list out of the rule text.

    Handles:
      - is in [A, B, C]
      - is one of [A, B, C]
      - in (A, B, C)
      - is in 'A', 'B', 'C'
    Returns None if no list is present.
    """
    # Bracketed list: in [A, B, C]
    m = re.search(r"(?:in|one of)\s*[\[\(]([^\]\)]+)[\]\)]", rule_text, re.IGNORECASE)
    if m:
        raw = m.group(1)
        return [v.strip().strip("'\"") for v in re.split(r"[,;]", raw) if v.strip()]
    return None


def _extract_tolerance(rule_text: str) -> float:
    """Extract a numeric tolerance from text like 'within 0.01'.

    Defaults to 0 (exact match) when no tolerance is mentioned.
    """
    m = re.search(r"within\s+([0-9]*\.?[0-9]+)", rule_text, re.IGNORECASE)
    return float(m.group(1)) if m else 0.0


def _format_examples(values: pd.Series, n: int = 3) -> str:
    """Render up to ``n`` example values for the example string."""
    samples = values.head(n).astype(str).tolist()
    return ", ".join(samples)


# ─────────────────────────────────────────────────────────────────────────
# Family parsers
#
# Each parser returns ``CrossFieldResult`` on a successful match, ``None``
# if the rule does not belong to that family. Parsers run in a fixed
# priority order; the first non-None result wins.
# ─────────────────────────────────────────────────────────────────────────

def _try_composite_unique(
    rule_text: str, df: pd.DataFrame, candidate_columns: List[str],
) -> Optional[CrossFieldResult]:
    """Composite uniqueness — exact or fuzzy.

    Triggers on phrases like:
      "<a> + <b> + <c> must be unique together"
      "<a> and <b> must be unique together"
      "Flag duplicate when <a> and <b> match exactly"
    """
    rl = rule_text.lower()
    triggers = (
        "unique together",
        "must be unique",
        "duplicate",
        "match exactly",
        "must match",
    )
    if not any(t in rl for t in triggers):
        return None
    if len(candidate_columns) < 2:
        return None

    # Use the first 2-4 candidate columns as the tuple. Capping at 4 keeps
    # the check meaningful — a 10-column tuple is almost guaranteed to be
    # unique by accident.
    cols = candidate_columns[:4]
    sub = df[cols]
    dup_mask = sub.duplicated(keep=False)
    count = int(dup_mask.sum())
    if count == 0:
        example = "All tuples unique - No issues found"
    else:
        # Show the first few duplicate tuples as examples.
        offending = sub[dup_mask].drop_duplicates().head(3)
        as_str = offending.astype(str).agg(" | ".join, axis=1).tolist()
        example = f"{count} duplicate tuples, e.g. {'; '.join(as_str)}"
    return CrossFieldResult(
        family="composite_unique",
        count=count,
        example=example,
        expression=f"composite_unique({', '.join(cols)})",
        columns=cols,
        failing_mask=dup_mask if count > 0 else None,
    )


def _try_conditional_presence(
    rule_text: str, df: pd.DataFrame, candidate_columns: List[str],
) -> Optional[CrossFieldResult]:
    """Target column must be present when context column is in [list].

    Triggers on:
      "<target> must be present when <context> is in [A, B, C]"
      "<target> must not be blank when <context> in (A, B)"
    """
    rl = rule_text.lower()
    if "must be present" not in rl and "must not be blank when" not in rl \
            and "required when" not in rl:
        return None
    if len(candidate_columns) < 2:
        return None

    values = _extract_value_list(rule_text)
    if not values:
        return None

    target, context = candidate_columns[0], candidate_columns[1]
    target_col = df[target]
    context_col = df[context].astype(str)

    # Mask for rows where context is in the value list (case-insensitive,
    # whitespace-stripped — most rule lists were written by humans).
    values_norm = {v.strip().lower() for v in values}
    in_scope = context_col.str.strip().str.lower().isin(values_norm)

    blank = target_col.isnull() | target_col.astype(str).str.strip().eq("")
    bad_mask = in_scope & blank
    count = int(bad_mask.sum())
    if count == 0:
        example = f"All {target} present when required - No issues found"
    else:
        sample_ctx = df.loc[bad_mask, context].astype(str).head(3).tolist()
        example = f"{count} rows missing {target} when {context} in {values}, e.g. {context}={sample_ctx}"
    expr = f"conditional_presence({target} not blank when {context} in {values})"
    return CrossFieldResult(
        family="conditional_presence",
        count=count,
        example=example,
        expression=expr,
        columns=[target, context],
        failing_mask=bad_mask if count > 0 else None,
    )


def _try_prefix_from_sibling(
    rule_text: str, df: pd.DataFrame, candidate_columns: List[str],
) -> Optional[CrossFieldResult]:
    """Target must start with / contain the value stored in another column.

    Triggers on:
      "<target> must start with the <something> stored in <sibling>"
      "<target> must begin with <sibling>"
      "<target> must contain <sibling>"
    """
    rl = rule_text.lower()
    if not (
        "start with" in rl or "starts with" in rl
        or "begin with" in rl or "begins with" in rl
        or "must contain" in rl
    ):
        return None
    if len(candidate_columns) < 2:
        return None

    target, sibling = candidate_columns[0], candidate_columns[1]
    target_str = df[target].astype(str).str.upper().str.strip()
    sibling_str = df[sibling].astype(str).str.upper().str.strip()

    if "contain" in rl:
        # Element-wise contains check; both sides as strings.
        bad_mask = ~target_str.combine(sibling_str, lambda t, s: bool(s) and (s in t))
        op = "contains"
    else:
        bad_mask = ~target_str.combine(sibling_str, lambda t, s: bool(s) and t.startswith(s))
        op = "starts_with"

    # Don't count rows where either side is null/blank — those are
    # completeness issues for the per-column rule, not cross-field.
    either_blank = (
        df[target].isnull() | df[target].astype(str).str.strip().eq("")
        | df[sibling].isnull() | df[sibling].astype(str).str.strip().eq("")
    )
    bad_mask = bad_mask & ~either_blank
    count = int(bad_mask.sum())
    if count == 0:
        example = f"All {target} {op} {sibling} - No issues found"
    else:
        examples = df.loc[bad_mask, [target, sibling]].head(3)
        rendered = "; ".join(
            f"{target}={r[target]!r} vs {sibling}={r[sibling]!r}"
            for _, r in examples.iterrows()
        )
        example = f"{count} rows where {target} does not {op} {sibling}, e.g. {rendered}"
    return CrossFieldResult(
        family="prefix_from_sibling",
        count=count,
        example=example,
        expression=f"{op}({target}, {sibling})",
        columns=[target, sibling],
        failing_mask=bad_mask if count > 0 else None,
    )


def _try_arithmetic(
    rule_text: str, df: pd.DataFrame, candidate_columns: List[str],
) -> Optional[CrossFieldResult]:
    """Target = sum of two or more siblings (within a tolerance).

    Triggers on:
      "<target> must equal <a> + <b>"
      "<target> = <a> + <b> within 0.01"
      "<target> must be the sum of <a> and <b>"
    """
    rl = rule_text.lower()
    has_sum_phrase = (
        ("must equal" in rl and "+" in rule_text)
        or "sum of" in rl
        or re.search(r"=\s*[a-zA-Z_]", rule_text) is not None
    )
    if not has_sum_phrase:
        return None
    if len(candidate_columns) < 3:
        return None

    target = candidate_columns[0]
    addends = candidate_columns[1:]

    target_num = pd.to_numeric(df[target], errors="coerce")
    addend_nums = [pd.to_numeric(df[c], errors="coerce") for c in addends]
    if any(s.isnull().all() for s in [target_num, *addend_nums]):
        return None  # at least one column isn't numeric — bail to LLM fallback
    expected = sum(addend_nums)
    tolerance = _extract_tolerance(rule_text)
    diff = (target_num - expected).abs()
    bad_mask = diff > tolerance
    bad_mask = bad_mask & target_num.notna() & expected.notna()
    count = int(bad_mask.sum())
    if count == 0:
        example = f"{target} matches {' + '.join(addends)} (tol {tolerance}) - No issues found"
    else:
        bad_rows = df.loc[bad_mask, [target, *addends]].head(3)
        rendered = "; ".join(
            f"{target}={r[target]} vs {' + '.join(str(r[c]) for c in addends)}"
            for _, r in bad_rows.iterrows()
        )
        example = f"{count} rows where {target} ≠ {' + '.join(addends)} (tol {tolerance}), e.g. {rendered}"
    return CrossFieldResult(
        family="arithmetic",
        count=count,
        example=example,
        expression=f"{target} == {' + '.join(addends)} ± {tolerance}",
        columns=[target, *addends],
        failing_mask=bad_mask if count > 0 else None,
    )


# Order matters: arithmetic before composite_unique because some
# arithmetic phrasings ("a + b must equal c") look like a composite-unique
# trigger. Conditional presence before prefix because both can mention
# "is in" / "stored in".
_FAMILY_PARSERS: List[Callable[..., Optional[CrossFieldResult]]] = [
    _try_arithmetic,
    _try_conditional_presence,
    _try_prefix_from_sibling,
    _try_composite_unique,
]


# ─────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────

def evaluate_cross_field_rule(
    rule_text: str,
    df: pd.DataFrame,
    llm_translator: Optional[Callable[[str, List[str]], Optional[Dict[str, Any]]]] = None,
) -> CrossFieldResult:
    """Classify and evaluate a single cross-field rule against ``df``.

    Args:
        rule_text: the human-readable rule sentence.
        df: the DataFrame to evaluate against.
        llm_translator: optional callable that takes ``(rule_text,
            column_names)`` and returns a dict like
            ``{"expression": "...", "code": "df[...]..."}`` or ``None``.
            Called only if no built-in family parser matches. The returned
            ``code`` is executed in a restricted namespace; see
            ``_run_llm_expression`` for safety constraints.
    """
    all_columns = [str(c) for c in df.columns]
    candidates = _detect_columns_in_text(rule_text, all_columns)

    # Bail only when the rule mentions zero real columns — there is
    # nothing for the LLM to ground against. A single column is enough:
    # the cross-field bucket sometimes catches what are really
    # single-column rules (year validity, format check), and the LLM
    # translator can express those just fine.
    if len(candidates) < 1:
        return CrossFieldResult(
            family="manual",
            count=0,
            example="Cross-field — manual review (no recognisable columns in rule text)",
            expression="",
            columns=candidates,
        )

    # Mechanical family parsers are inherently multi-column; only run
    # them when we have 2+ candidates.
    if len(candidates) >= 2:
        for parser in _FAMILY_PARSERS:
            try:
                result = parser(rule_text, df, candidates)
            except Exception as exc:  # pragma: no cover  (defensive)
                logger.warning("Family parser %s raised on rule %r: %s",
                               parser.__name__, rule_text[:60], exc)
                continue
            if result is not None:
                return result

    # No mechanical family matched (or only one column was named). Try
    # the LLM translator — it can handle both single-column and
    # multi-column rules, regex format checks, range checks, conditional
    # value lookups, etc.
    if llm_translator is not None:
        try:
            translated = llm_translator(rule_text, all_columns)
        except Exception as exc:
            logger.warning("LLM translator raised on rule %r: %s", rule_text[:60], exc)
            translated = None
        if translated:
            executed = _run_llm_expression(translated, df, candidates)
            if executed is not None:
                return executed

    return CrossFieldResult(
        family="manual",
        count=0,
        example="Cross-field — manual review (rule shape not auto-evaluable)",
        expression="",
        columns=candidates,
    )


# ─────────────────────────────────────────────────────────────────────────
# LLM-translated expression executor
# ─────────────────────────────────────────────────────────────────────────

# Bare names allowed at the root of the LLM-emitted expression. Attribute
# access (e.g. pd.to_datetime, df['col'].str.upper()) is allowed via the
# AST walk below as long as the *root* of the chain is one of these.
#
# Type-conversion builtins (str, int, float, bool, len, abs) are included
# because pandas idioms commonly use them — e.g. ``df['x'].astype(str)``.
# They are safe in this sandbox because the AST walker still rejects any
# dunder attribute access (``str.__class__.__bases__[0].__subclasses__()``
# can't be reached because ``__class__`` is in _FORBIDDEN_ATTRS).
_SAFE_ROOT_NAMES = {
    "df", "pd", "np",
    "str", "int", "float", "bool", "len", "abs",
    "True", "False", "None",
}

# AST node types allowed anywhere in the expression. Anything else (Lambda,
# Call to __import__, list/set comprehensions with stores, etc.) is rejected.
_SAFE_AST_NODES: Tuple[type, ...] = (
    ast.Expression,
    ast.BoolOp, ast.BinOp, ast.UnaryOp, ast.Compare,
    ast.And, ast.Or, ast.Not, ast.Invert, ast.UAdd, ast.USub,
    ast.Add, ast.Sub, ast.Mult, ast.Div, ast.Mod, ast.Pow, ast.FloorDiv,
    ast.BitAnd, ast.BitOr, ast.BitXor,
    ast.Eq, ast.NotEq, ast.Lt, ast.LtE, ast.Gt, ast.GtE,
    ast.In, ast.NotIn, ast.Is, ast.IsNot,
    ast.Constant, ast.Name, ast.Load, ast.Attribute, ast.Subscript,
    ast.Call, ast.Index, ast.Slice,
    ast.List, ast.Tuple, ast.Set, ast.Dict,
    ast.IfExp,  # ternary expressions
    ast.keyword,
    ast.Starred,
)

# Attribute access patterns that are flatly forbidden no matter what.
_FORBIDDEN_ATTRS = {
    "__class__", "__bases__", "__subclasses__", "__mro__",
    "__globals__", "__builtins__", "__import__",
    "mro", "subclasses",
}


def _expression_is_safe(tree: ast.AST) -> Tuple[bool, str]:
    """Walk an AST and verify every node is on the allowlist.

    Returns ``(True, '')`` if the tree is safe to eval; ``(False, reason)``
    otherwise. The reason is logged so unsafe rules can be debugged.
    """
    for node in ast.walk(tree):
        if not isinstance(node, _SAFE_AST_NODES):
            return False, f"forbidden node type: {type(node).__name__}"
        if isinstance(node, ast.Attribute):
            if node.attr in _FORBIDDEN_ATTRS or node.attr.startswith("__"):
                return False, f"forbidden attribute: {node.attr}"
        if isinstance(node, ast.Name):
            # Bare names (not the .attr part of Attribute access) must be
            # in the safe-root set. ast.walk visits Attribute.value as
            # its own Name node, so this catches both "pd" inside
            # "pd.to_datetime" and "open" alone.
            if node.id not in _SAFE_ROOT_NAMES:
                return False, f"unknown name: {node.id}"
    return True, ""


def _run_llm_expression(
    translated: Dict[str, Any],
    df: pd.DataFrame,
    candidates: List[str],
) -> Optional[CrossFieldResult]:
    """Evaluate an LLM-emitted boolean mask expression against ``df``.

    The translator must return a dict with at least:
        {"code": "<a python expression returning a bool Series>",
         "description": "<short description of what's checked>"}

    The expression sees a sandboxed namespace of {df, pd, np}. An AST
    walk rejects any node not on the allowlist (lambdas, comprehensions,
    dunder attributes, bare names that aren't df/pd/np). Anything that
    slips past static checks and raises at runtime is logged and treated
    as unparsed.

    The expression must evaluate to a boolean ``pd.Series`` of length
    ``len(df)`` where True marks a *failing* row.
    """
    code = str(translated.get("code") or "").strip()
    description = str(translated.get("description") or "").strip()
    if not code:
        return None

    # Parse first; eval mode forbids statements.
    try:
        tree = ast.parse(code, mode="eval")
    except SyntaxError as exc:
        logger.warning("LLM expression rejected - syntax error: %s", exc)
        return None

    safe, reason = _expression_is_safe(tree)
    if not safe:
        logger.warning("LLM expression rejected - %s; code: %s", reason, code[:120])
        return None

    # Strip __builtins__ to None so eval can't reach `__import__`, `open`,
    # etc. Hand-pick the type-conversion builtins the AST walker already
    # accepted so common pandas idioms (``astype(str)``) keep working.
    sandbox = {
        "df": df, "pd": pd, "np": np,
        "str": str, "int": int, "float": float, "bool": bool,
        "len": len, "abs": abs,
        "__builtins__": {},
    }
    try:
        bad_mask = eval(compile(tree, "<llm-cross-field>", "eval"), sandbox, {})
    except Exception as exc:
        logger.warning("LLM expression raised at runtime: %s", exc)
        return None

    # Coerce to boolean Series of correct length.
    if not isinstance(bad_mask, pd.Series):
        logger.warning("LLM expression did not return a Series: %r", type(bad_mask))
        return None
    if bad_mask.dtype != bool:
        try:
            bad_mask = bad_mask.astype(bool)
        except Exception:
            return None
    if len(bad_mask) != len(df):
        logger.warning("LLM expression length mismatch: %s vs %s", len(bad_mask), len(df))
        return None

    count = int(bad_mask.sum())
    if count == 0:
        example = f"{description or 'LLM rule'} - No issues found"
    else:
        # Show a sample of failing rows over the candidate columns.
        cols_to_show = [c for c in candidates if c in df.columns][:4]
        if cols_to_show:
            sample = df.loc[bad_mask, cols_to_show].head(3)
            rendered = "; ".join(
                " | ".join(f"{c}={r[c]}" for c in cols_to_show)
                for _, r in sample.iterrows()
            )
            example = f"{count} failing rows: {rendered}"
        else:
            example = f"{count} failing rows"

    return CrossFieldResult(
        family="llm",
        count=count,
        example=example,
        expression=description or code,
        columns=candidates,
        failing_mask=bad_mask if count > 0 else None,
    )


# ─────────────────────────────────────────────────────────────────────────
# Azure OpenAI translator factory
# ─────────────────────────────────────────────────────────────────────────

_LLM_TRANSLATOR_PROMPT = """You translate one English data-quality rule
into a pandas boolean-mask expression. The expression marks the FAILING
rows (True = the row violates the rule).

CONSTRAINTS
-----------
The expression MUST:
  - Be a single Python expression (one line, no statements).
  - Reference only the names df, pd, np, and the builtins str, int,
    float, bool, len, abs.
  - Return a pandas Series of booleans with length len(df).
  - Use vectorised pandas operations. No lambdas, no imports, no IO,
    no eval, no dunder access (anything starting with __ is rejected).

USE THESE IDIOMS — they cover almost every rule
-----------------------------------------------
  Regex format:         df['c'].astype(str).str.match(r'^...$', na=False)
  Date comparison:      pd.to_datetime(df['a'], errors='coerce') > pd.to_datetime(df['b'], errors='coerce')
  Current year:         pd.Timestamp.now().year
  Numeric range:        ~pd.to_numeric(df['c'], errors='coerce').between(lo, hi)
  Inline lookup:        df['country'].astype(str).str.upper().map({'DE':'EUR','US':'USD'}) != df['currency']
  Membership:           ~df['c'].isin(['A', 'B', 'C'])
  Composite condition:  (cond_a) & ~(cond_b)        (use & | ~, NOT and/or/not)

DEFAULT TO TRANSLATING — do not bail
------------------------------------
Rules that look like they need external data USUALLY do not. For each of
these patterns, encode the rule directly:

  - "X must follow the format specific to <country>" → use the country's
    standard regex (PAN: ^[A-Z]{5}[0-9]{4}[A-Z]$, Aadhaar: ^[0-9]{12}$,
    SSN: ^[0-9]{3}-[0-9]{2}-[0-9]{4}$, US ZIP: ^[0-9]{5}(-[0-9]{4})?$).

  - "Y must match the locale of <country>" → write an inline .map() with
    the small set of values the dataset uses. Example below.

  - "X must be a valid year" → compare against
    pd.Timestamp.now().year.

  - "X must be a valid email/phone/URL" → standard regex.

  - Single-column validity rules ("X must be alphanumeric", "X must be
    positive", "X must be no longer than N chars") — translate them
    even if the rule was filed under cross-field by mistake.

ONLY return empty code when the rule references concepts truly outside
the table AND outside common standards (e.g. "this column must equal
the customer's account balance from the CRM").

OUTPUT FORMAT
-------------
Return JSON exactly:
{
  "code": "<single-line pandas expression returning a bool Series>",
  "description": "<short description of what is checked>"
}

If — and only if — the rule cannot be expressed:
{ "code": "", "description": "<short reason>" }

EXAMPLES
--------
Rule: "gross_amount must equal net_amount + tax_amount within 0.01"
Columns: [gross_amount, net_amount, tax_amount, currency]
{
  "code": "(df['gross_amount'] - df['net_amount'] - df['tax_amount']).abs() > 0.01",
  "description": "gross_amount differs from net + tax by more than 0.01"
}

Rule: "discharge_date must be on or after admission_date"
Columns: [admission_date, discharge_date, patient_id]
{
  "code": "pd.to_datetime(df['discharge_date'], errors='coerce') < pd.to_datetime(df['admission_date'], errors='coerce')",
  "description": "discharge_date is before admission_date"
}

Rule: "pan_number must follow the format specific to India when country is 'INDIA'"
Columns: [pan_number, country, name]
{
  "code": "(df['country'].astype(str).str.upper().str.strip() == 'INDIA') & ~df['pan_number'].astype(str).str.match(r'^[A-Z]{5}[0-9]{4}[A-Z]$', na=False)",
  "description": "pan_number does not match Indian PAN format when country is INDIA"
}

Rule: "year_of_establishment must be a valid year and not greater than the current year"
Columns: [year_of_establishment]
{
  "code": "(pd.to_numeric(df['year_of_establishment'], errors='coerce') < 1800) | (pd.to_numeric(df['year_of_establishment'], errors='coerce') > pd.Timestamp.now().year)",
  "description": "year_of_establishment is outside the valid range [1800, current year]"
}

Rule: "currency must match the locale implied by country"
Columns: [country, currency]
{
  "code": "df['country'].astype(str).str.upper().str.strip().map({'DE':'EUR','FR':'EUR','IT':'EUR','ES':'EUR','NL':'EUR','BE':'EUR','AT':'EUR','PT':'EUR','GR':'EUR','GB':'GBP','US':'USD','IN':'INR','CN':'CNY','JP':'JPY','CA':'CAD','AU':'AUD','CH':'CHF'}).fillna(df['currency']) != df['currency']",
  "description": "currency does not match the country's typical currency"
}

Rule: "company_type must be consistent with entity_type, e.g. entity_type='BUYER' implies company_type in ['LIMITED_LIABILITY_PARTNERSHIP','LLC','LLP']"
Columns: [company_type, entity_type]
{
  "code": "(df['entity_type'].astype(str).str.upper().str.strip() == 'BUYER') & ~df['company_type'].astype(str).str.upper().str.strip().isin(['LIMITED_LIABILITY_PARTNERSHIP','LLC','LLP'])",
  "description": "company_type not in {LLP, LLC, LIMITED_LIABILITY_PARTNERSHIP} when entity_type=BUYER"
}

NOW TRANSLATE
-------------
Rule: {rule_text}
Columns available: {column_names}

Return ONLY the JSON object."""


def make_azure_translator(client: Any, deployment: str) -> Callable[[str, List[str]], Optional[Dict[str, Any]]]:
    """Build an LLM translator bound to an Azure OpenAI client.

    Returns a callable matching the signature
    ``llm_translator(rule_text, column_names) -> dict | None`` accepted
    by :func:`evaluate_cross_field_rule`.

    The returned callable issues one chat completion per call. It is the
    caller's responsibility to memoize (rules + column list) tuples if
    repeat calls would be wasteful — the executor below makes one call
    per cross-field rule that the family parsers couldn't handle.
    """
    def _translate(rule_text: str, column_names: List[str]) -> Optional[Dict[str, Any]]:
        prompt = _LLM_TRANSLATOR_PROMPT.replace(
            "{rule_text}", rule_text,
        ).replace(
            "{column_names}", json.dumps(column_names, ensure_ascii=False),
        )
        try:
            resp = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system",
                     "content": "You are a careful pandas expression generator. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                seed=42,
                response_format={"type": "json_object"},
                max_tokens=400,
            )
            text = resp.choices[0].message.content.strip()
        except Exception as exc:
            logger.warning("LLM translator call failed: %s", exc)
            return None
        try:
            obj = json.loads(text)
        except json.JSONDecodeError:
            logger.warning("LLM translator returned non-JSON: %s", text[:200])
            return None
        # Sanity: refuse empty code, refuse code that doesn't look like an
        # expression. The executor's static safety check will then reject
        # anything dangerous that slips past these.
        code = str(obj.get("code") or "").strip()
        if not code:
            return None
        return {"code": code, "description": str(obj.get("description") or "").strip()}
    return _translate
