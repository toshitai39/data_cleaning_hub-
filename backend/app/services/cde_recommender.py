"""LLM-driven Critical Data Element descriptions and recommendations.

A single batched chat-completion call per dataset asks the model to produce,
for every column: a one-sentence plain-English description and a boolean
``recommended`` flag indicating whether the field is a high-signal CDE worth
including in scope for data-quality work.

No hardcoded column allowlists. The judgment comes from the model based on
the column name, sample values, dtype, and (when known) the source-system /
stream context.

The output is cached on disk by ``project_storage.save_cde_meta`` keyed on a
fingerprint of the dataset's column set, so re-opening a project doesn't
re-bill the LLM.
"""

from __future__ import annotations

import hashlib
import json
import logging
import re
from typing import Any, Dict, List, Optional

import pandas as pd

from .llm_rules import _client, _config, llm_available, _parse_response

logger = logging.getLogger(__name__)


# Cap batch size — single call should stay well under the model's output
# window even for chatty datasets. Each column entry takes ~60–90 output
# tokens (name + description + recommended + reason), so 20 columns/batch
# at ~4000 max_completion_tokens leaves a comfortable safety margin.
_MAX_COLUMNS_PER_CALL = 20
_MAX_OUTPUT_TOKENS = 4000
_MAX_SAMPLES_PER_COL = 3
_MAX_SAMPLE_LEN = 60


def column_set_fingerprint(columns: List[str]) -> str:
    """Stable hash of the column-name set — used as the cache key.

    Order-independent so re-ordering doesn't bust the cache, but composition
    changes (added / removed columns) will.
    """
    payload = "".join(sorted(str(c) for c in columns))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def _column_payload(name: str, series: pd.Series) -> Dict[str, Any]:
    """One column's worth of evidence sent to the LLM."""
    try:
        dtype = str(series.dtype)
    except Exception:
        dtype = "object"
    samples: List[str] = []
    try:
        for v in series.dropna().head(_MAX_SAMPLES_PER_COL).tolist():
            text = str(v).strip()
            if len(text) > _MAX_SAMPLE_LEN:
                text = text[: _MAX_SAMPLE_LEN - 1] + "…"
            samples.append(text)
    except Exception:
        samples = []
    try:
        non_null = int(series.notna().sum())
        total = int(len(series))
        unique = int(series.nunique(dropna=True))
    except Exception:
        non_null = total = unique = 0
    return {
        "name": name,
        "dtype": dtype,
        "samples": samples,
        "non_null": non_null,
        "total": total,
        "unique": unique,
    }


_SYSTEM_PROMPT = (
    "You are a senior master-data analyst. For each column in a tabular "
    "dataset you receive, produce three things:\n\n"
    "  1. A clear one-sentence description of what the column represents.\n"
    "  2. A boolean `recommended` flag — true iff the column is a Critical "
    "Data Element (CDE), i.e. a field important enough that the business "
    "would want data-quality rules running against it. CDEs are typically "
    "primary identifiers, tax / regulatory identifiers, legal or trade "
    "names, country / currency / company codes, or account numbers. "
    "Audit timestamps, soft-delete flags, free-text comments, and purely "
    "descriptive attributes (city, fax, search-term) are typically NOT CDEs.\n"
    "  3. A `semantic_type` — exactly one short snake_case tag from the "
    "controlled list below that best classifies the column's value format. "
    "This drives downstream format-validation scoring. BIAS STRONGLY toward "
    "the specific identifier tag when either the column name OR the sample "
    "values match — never fall back to `alphanumeric_id`, `numeric_id`, "
    "`enum_code`, or `other` when a specific tag applies.\n\n"
    "Controlled tag list:\n"
    "       pan, gstin, tan, cin, vat, ein, ssn, aadhaar, iban, swift, ifsc, "
    "iso_country, iso_currency, email, phone, url, postal_code, indian_pin, "
    "numeric_id, alphanumeric_id, account_number, date, datetime, year, "
    "boolean, amount, quantity, percentage, free_text_name, free_text_address, "
    "free_text_description, enum_code, other.\n\n"
    "Examples of correct classification (memorise these — they cover the "
    "most common mistakes):\n"
    "  • column `pan_number` with values like ABCDE1234F → `pan` (NOT alphanumeric_id)\n"
    "  • column `STCD1` with samples ABCDE1234F → `pan` (NOT tan, NOT alphanumeric_id)\n"
    "  • column `gstin` with values like 27ABCDE1234F1Z5 → `gstin` (NOT alphanumeric_id)\n"
    "  • column `STCD2` with samples 27ABCDE1234F1Z5 → `gstin`\n"
    "  • column `email` with values like a@b.com → `email` (NOT free_text_description)\n"
    "  • column `LAND1` with 2-letter values like IN, US → `iso_country` (NOT enum_code)\n"
    "  • column `WAERS` with values INR, USD → `iso_currency`\n"
    "  • column `pincode` with values like 400001 → `indian_pin`\n"
    "  • column `ifsc_code` with values HDFC0000001 → `ifsc`\n"
    "  • column `mobile` with values +91-9876543210 → `phone`\n"
    "  • column `customer_name` with values like 'Acme Pvt Ltd' → `free_text_name`\n"
    "  • column `created_at` with timestamps → `datetime`\n\n"
    "Use `other` ONLY when no tag from the controlled list could plausibly "
    "apply. Free-text fields that are clearly names go to `free_text_name`, "
    "addresses to `free_text_address`, longer descriptions to "
    "`free_text_description` — not `other`.\n\n"
    "Always return strict JSON. No markdown."
)


def _build_user_prompt(columns: List[Dict[str, Any]], schema_hint: Optional[Dict[str, Any]]) -> str:
    context_lines = []
    if schema_hint:
        sys_label = schema_hint.get("system_label") or schema_hint.get("system_id")
        stream_label = schema_hint.get("stream_label") or schema_hint.get("stream_id")
        if sys_label or stream_label:
            context_lines.append(
                f"Dataset context: {sys_label or 'unknown system'} · {stream_label or 'unknown stream'}."
            )
    if not context_lines:
        context_lines.append("Dataset context: not specified — judge each column on its name and samples alone.")

    columns_block = json.dumps(columns, ensure_ascii=False, default=str, indent=2)

    return (
        "\n".join(context_lines)
        + "\n\nCOLUMNS\n=======\n"
        + columns_block
        + "\n\nRETURN THIS EXACT JSON SHAPE:\n"
        + "{\n"
          '  "columns": [\n'
          '    {\n'
          '      "name": "<original column name, copied verbatim>",\n'
          '      "description": "<one sentence, plain English, no jargon dump>",\n'
          '      "recommended": true | false,\n'
          '      "reason": "<≤12 words explaining the recommendation>",\n'
          '      "semantic_type": "<one tag from the controlled list>"\n'
          '    }\n'
          '  ]\n'
          "}\n\n"
          "Rules:\n"
          "1. The output array must include every column from the input in the same order.\n"
          "2. Copy each column name verbatim into the `name` field — do not rename, case-fold, or translate.\n"
          "3. `description` must be a single sentence describing the field's meaning. If the column is clearly an "
          "ERP technical code (e.g. SAP table.field), expand the acronym. Mention the format when obvious from samples.\n"
          "4. `recommended` is true only if the field is a CDE per the system rules.\n"
          "5. `reason` is short — it answers \"why recommended\" or \"why not\".\n"
          "6. `semantic_type` is exactly one tag from the controlled list in the system message. "
          "When unsure between two tags, pick the more specific one. Default to 'other' only when no tag applies.\n"
          "7. JSON only. No markdown fences, no commentary."
    )


def _recover_partial_columns(text: str) -> List[Dict[str, Any]]:
    """Salvage complete ``{...}`` objects from a truncated JSON payload.

    If the model hit ``max_completion_tokens`` mid-response, the outer
    ``{"columns": [...]}`` won't parse. But the columns array up to the cut
    point is usually a sequence of well-formed objects — we walk the text
    matching braces and try ``json.loads`` on each candidate. Returns the
    list of successfully parsed objects (may be empty).
    """
    objects: List[Dict[str, Any]] = []
    depth = 0
    start: Optional[int] = None
    in_string = False
    escape = False
    for i, ch in enumerate(text):
        if in_string:
            if escape:
                escape = False
            elif ch == "\\":
                escape = True
            elif ch == '"':
                in_string = False
            continue
        if ch == '"':
            in_string = True
        elif ch == "{":
            if depth == 0:
                start = i
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0 and start is not None:
                candidate = text[start : i + 1]
                start = None
                try:
                    obj = json.loads(candidate)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and "name" in obj:
                    objects.append(obj)
    return objects


class CDERecommenderError(RuntimeError):
    """Raised when the LLM call genuinely fails (after retries / parsing).

    The router surfaces this to the frontend as a 502 so the user sees the
    actual reason instead of a silent fallback. ``cause`` carries the
    underlying SDK / parse exception for the log line.
    """

    def __init__(self, message: str, *, cause: Optional[BaseException] = None) -> None:
        super().__init__(message)
        self.cause = cause


def _call_llm_batch(payload: List[Dict[str, Any]], schema_hint: Optional[Dict[str, Any]]) -> Dict[str, Dict[str, Any]]:
    """Single chat-completion round-trip → {column_name: meta}.

    Mirrors the call signature used by ``llm_rules.generate_rules_for_dataframe``
    deliberately — no ``response_format`` (older Azure deployments reject it),
    temperature 0.1, modest token cap — so anything that works for rule
    generation works here too.
    """
    client = _client()
    if client is None:
        raise CDERecommenderError("LLM client not configured (Azure OpenAI endpoint / key / deployment missing).")
    deployment = _config()["deployment"]
    if not deployment:
        raise CDERecommenderError("Azure OpenAI deployment name missing.")

    prompt = _build_user_prompt(payload, schema_hint)
    try:
        resp = client.chat.completions.create(
            model=deployment,
            messages=[
                {"role": "system", "content": _SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            temperature=0.1,
            max_completion_tokens=_MAX_OUTPUT_TOKENS,
        )
    except Exception as exc:  # openai.APIError / BadRequestError / etc.
        raise CDERecommenderError(f"Azure OpenAI request failed: {exc}", cause=exc)

    choice = resp.choices[0] if resp.choices else None
    content = (choice.message.content or "").strip() if choice else ""
    finish_reason = getattr(choice, "finish_reason", None) if choice else None
    if not content:
        raise CDERecommenderError("LLM returned an empty response.")

    parsed = _parse_response(content)
    if not parsed or not isinstance(parsed.get("columns"), list):
        # Try to recover whatever complete column entries the model managed
        # to emit before truncation, so a too-long response still partially
        # works instead of being a hard failure.
        recovered = _recover_partial_columns(content)
        if recovered:
            parsed = {"columns": recovered}
        else:
            snippet = content[:300].replace("\n", " ")
            hint = " (truncated — try reducing batch size)" if finish_reason == "length" else ""
            raise CDERecommenderError(
                f"LLM returned no usable JSON{hint}. First 300 chars: {snippet!r}"
            )

    out: Dict[str, Dict[str, Any]] = {}
    for entry in parsed["columns"]:
        if not isinstance(entry, dict):
            continue
        name = str(entry.get("name", "")).strip()
        if not name:
            continue
        description = str(entry.get("description", "")).strip()
        reason = str(entry.get("reason", "")).strip()
        recommended = bool(entry.get("recommended", False))
        semantic_type = str(entry.get("semantic_type", "")).strip().lower() or "other"
        out[name] = {
            "description": description,
            "recommended": recommended,
            "reason": reason,
            "semantic_type": semantic_type,
            "source": "ai",
        }
    if not out:
        raise CDERecommenderError("LLM returned a JSON object but no usable column entries.")
    return out


def dtype_fallback_meta(df: pd.DataFrame) -> Dict[str, Dict[str, Any]]:
    """Per-column dtype-only meta. Used when the LLM is unconfigured.

    Every entry includes ``semantic_type='other'`` so downstream consumers
    (Validation / Uniqueness scorers, cache-staleness check) never see an
    entry that's missing the field — that field's presence is the schema
    contract for cached cde_meta.
    """
    if df is None:
        return {}
    out: Dict[str, Dict[str, Any]] = {}
    for col in [str(c) for c in df.columns]:
        payload = _column_payload(col, df[col])
        samples_str = ", ".join(payload["samples"]) if payload["samples"] else ""
        desc = f"{payload['dtype']} · e.g. {samples_str}" if samples_str else (payload["dtype"] or "")
        out[col] = {
            "description": desc,
            "recommended": False,
            "reason": "AI not configured — no automatic recommendation.",
            "semantic_type": "other",
            "source": "fallback",
        }
    return out


def generate_cde_meta(
    df: pd.DataFrame,
    schema_hint: Optional[Dict[str, Any]] = None,
) -> Dict[str, Dict[str, Any]]:
    """Produce per-column ``{description, recommended, reason, source}``.

    Raises ``CDERecommenderError`` if the LLM is configured but the call
    fails (so the router can surface a real error to the frontend instead
    of caching a silent fallback). When the LLM is not configured at all,
    returns dtype-only meta without raising — that case is expected and
    the router treats it as "AI unavailable, picker still works".
    """
    if df is None or len(df.columns) == 0:
        return {}

    all_cols = [str(c) for c in df.columns]

    if not llm_available():
        logger.info("CDE recommender: LLM not configured — returning dtype fallback for %d cols", len(all_cols))
        return dtype_fallback_meta(df)

    payload = [_column_payload(col, df[col]) for col in all_cols]
    merged: Dict[str, Dict[str, Any]] = {}
    for start in range(0, len(payload), _MAX_COLUMNS_PER_CALL):
        chunk = payload[start : start + _MAX_COLUMNS_PER_CALL]
        logger.info("CDE recommender: calling LLM for %d columns (batch %d)", len(chunk), start // _MAX_COLUMNS_PER_CALL + 1)
        chunk_out = _call_llm_batch(chunk, schema_hint)
        merged.update(chunk_out)

    # If the model dropped any columns from the response, fill them from the
    # dtype fallback so the UI still has a row for every input column.
    # Every gap-filler must include `semantic_type` so the cache stays
    # uniform — Validation / Uniqueness scorers depend on that field.
    fallback = dtype_fallback_meta(df) if any(c not in merged for c in all_cols) else {}
    for col in all_cols:
        if col not in merged or not merged[col].get("description"):
            merged[col] = fallback.get(col, {
                "description": "", "recommended": False, "reason": "",
                "semantic_type": "other", "source": "fallback",
            })

    return merged
