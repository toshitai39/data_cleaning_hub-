"""Semantic-type glossary for a dataset.

Looks at column names + sample values and infers what each column REPRESENTS
(email, phone, customer_id, country_code, etc.) using a single batched LLM
call. The result is a dataset-wide glossary that downstream tools (Rule
Generator, AI Validations) can use to write sharper rules.

Determinism: ``temperature=0``, ``seed=42``, ``response_format=json_object``
just like the rule generator passes. Same input → same glossary.
"""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List

import pandas as pd

logger = logging.getLogger(__name__)


# A loose taxonomy of common semantic types. We don't force the LLM into this
# closed set — it's allowed to return any snake_case slug — but listing common
# ones in the prompt nudges it toward stable, consistent vocabulary.
_COMMON_SEMANTIC_TYPES: List[str] = [
    "identifier_uuid", "identifier_natural", "customer_id", "employee_id",
    "order_id", "product_id", "transaction_id",
    "person_name", "company_name", "brand_name",
    "email", "phone_number", "url", "ip_address",
    "address_line", "city", "state", "region", "country_code", "country_name",
    "postal_code", "coordinate_lat", "coordinate_lng",
    "date", "datetime", "year", "age", "duration",
    "currency_amount", "currency_code", "percentage", "ratio", "count",
    "quantity", "decimal", "integer",
    "pan_number", "vat_number", "gst_number", "tax_id", "registration_id",
    "license_number", "passport_number",
    "category", "status", "boolean_flag", "priority", "rating",
    "description_short", "description_long", "notes", "free_text",
    "file_path", "mime_type", "unknown",
]


def _build_prompt(column_samples: Dict[str, List[str]]) -> str:
    """Single batched prompt covering every column at once."""
    lines: List[str] = []
    for name in sorted(column_samples.keys()):
        preview = column_samples[name][:5]
        lines.append(f"- {name}: {json.dumps(preview, ensure_ascii=False)}")
    catalog_block = "\n".join(lines) if lines else "(empty dataset)"
    suggested = ", ".join(_COMMON_SEMANTIC_TYPES)

    return f"""You are a data engineer building a SEMANTIC GLOSSARY for a
dataset. For every column below, infer what the column REPRESENTS based on
its name and sample values. The output is a structured glossary that
downstream tools will use to generate validation rules — so be specific.

DATASET COLUMNS (with up to 5 sample values each)
-------------------------------------------------
{catalog_block}

INSTRUCTIONS
------------
For EACH column, return:
- semantic_type: a short ``snake_case`` slug describing the kind of value
  this column holds. Prefer one of the common types when it fits:
  {suggested}.
  If none fits, invent a clear ``snake_case`` slug. Use ``unknown`` only as
  a last resort.
- display_name: a 1-3 word human-readable name (e.g. "Email Address",
  "Customer ID", "Country Code").
- description: ONE concise sentence about what this column contains.
- format_hint: a typical format or regex if the type has one, otherwise
  an empty string. Examples: "^[A-Z]{{5}}\\d{{4}}[A-Z]$" for Indian PAN,
  "^[A-Za-z0-9._%+-]+@.+\\.[A-Za-z]{{2,}}$" for email, "ISO-3166 alpha-2"
  for country_code, "YYYY-MM-DD" for date.
- confidence: 0.0 - 1.0. 0.9+ means values clearly match the inferred type;
  0.5-0.8 means the column name is suggestive but samples are ambiguous;
  below 0.5 means you are guessing.

Use the COLUMN NAME first (it usually tells you what the field is) and the
SAMPLE VALUES second (they confirm or contradict the name). If the name is
cryptic (e.g. "cust_em"), let the samples drive the answer.

OUTPUT
------
Return ONLY a JSON object with this shape — no prose, no markdown fence:

{{
  "glossary": [
    {{
      "column": "<exact column name from the list above>",
      "semantic_type": "<snake_case slug>",
      "display_name": "<human-readable name>",
      "description": "<one sentence>",
      "format_hint": "<regex or short hint, or empty string>",
      "confidence": 0.0
    }}
  ]
}}

Include EVERY column from the list above, in the same order, even if you
are unsure (set confidence accordingly and use ``unknown`` if you cannot
infer anything).

WORKED EXAMPLE
--------------
DATASET COLUMNS:
- cust_em: ["alice@acme.com", "bob@globex.io"]
- pan_number: ["ABPFA1975Q", "AAUPQ3368B"]
- country: ["DE", "FR", "GB"]
- entity_code: ["BY000288", "BY000289"]

{{
  "glossary": [
    {{
      "column": "cust_em",
      "semantic_type": "email",
      "display_name": "Customer Email",
      "description": "Customer's email address.",
      "format_hint": "^[A-Za-z0-9._%+-]+@.+\\.[A-Za-z]{{2,}}$",
      "confidence": 0.97
    }},
    {{
      "column": "pan_number",
      "semantic_type": "pan_number",
      "display_name": "PAN Number",
      "description": "Indian Permanent Account Number — 5 letters, 4 digits, 1 letter.",
      "format_hint": "^[A-Z]{{5}}\\d{{4}}[A-Z]$",
      "confidence": 0.99
    }},
    {{
      "column": "country",
      "semantic_type": "country_code",
      "display_name": "Country",
      "description": "ISO-3166 alpha-2 country code.",
      "format_hint": "^[A-Z]{{2}}$",
      "confidence": 0.95
    }},
    {{
      "column": "entity_code",
      "semantic_type": "identifier_natural",
      "display_name": "Entity Code",
      "description": "Internal entity identifier with a 'BY' prefix and 6 digits.",
      "format_hint": "^BY\\d{{6}}$",
      "confidence": 0.9
    }}
  ]
}}
"""


def _coerce_entry(raw: Dict[str, Any], valid_columns: set) -> Dict[str, Any] | None:
    column = str(raw.get("column", "")).strip()
    if not column or column not in valid_columns:
        return None
    try:
        confidence = float(raw.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    confidence = max(0.0, min(1.0, confidence))
    return {
        "column": column,
        "semantic_type": str(raw.get("semantic_type", "unknown")).strip() or "unknown",
        "display_name": str(raw.get("display_name", "")).strip() or column,
        "description": str(raw.get("description", "")).strip(),
        "format_hint": str(raw.get("format_hint", "")).strip(),
        "confidence": confidence,
        "source": "ai",
    }


def generate_semantic_glossary(
    df: pd.DataFrame,
    client: Any,
    deployment: str,
    max_columns_per_call: int = 60,
) -> Dict[str, Dict[str, Any]]:
    """Generate a semantic-type entry for every column in ``df``.

    For tables wider than ``max_columns_per_call``, split into batches so the
    prompt stays small. Each batch is a separate LLM call; the merged result
    is keyed by column name.
    """
    if df is None or df.shape[1] == 0:
        return {}

    samples: Dict[str, List[str]] = {}
    for c in df.columns:
        samples[str(c)] = sorted({str(v) for v in df[c].dropna().tolist()})[:5]

    valid_columns = set(samples.keys())
    column_order = list(samples.keys())
    glossary: Dict[str, Dict[str, Any]] = {}

    for start in range(0, len(column_order), max_columns_per_call):
        batch_cols = column_order[start:start + max_columns_per_call]
        batch_samples = {c: samples[c] for c in batch_cols}
        prompt = _build_prompt(batch_samples)
        try:
            response = client.chat.completions.create(
                model=deployment,
                messages=[
                    {"role": "system", "content": "You are a data engineer. Return only valid JSON."},
                    {"role": "user", "content": prompt},
                ],
                temperature=0,
                seed=42,
                response_format={"type": "json_object"},
                max_tokens=2500,
            )
            text = response.choices[0].message.content.strip()
        except Exception as exc:
            logger.error("Glossary LLM call failed for batch %d: %s", start, exc)
            for c in batch_cols:
                glossary.setdefault(c, _fallback_entry(c))
            continue

        if text.startswith("```"):
            text = text.split("```")[1]
            if text.startswith("json"):
                text = text[4:]
            text = text.strip()

        try:
            parsed = json.loads(text)
        except json.JSONDecodeError as exc:
            logger.error("Glossary JSON decode failed for batch %d: %s", start, exc)
            for c in batch_cols:
                glossary.setdefault(c, _fallback_entry(c))
            continue

        raw_list = parsed.get("glossary", []) if isinstance(parsed, dict) else []
        for raw in raw_list:
            entry = _coerce_entry(raw, valid_columns)
            if entry is None:
                continue
            glossary[entry["column"]] = entry

        for c in batch_cols:
            glossary.setdefault(c, _fallback_entry(c))

    return glossary


def _fallback_entry(column: str) -> Dict[str, Any]:
    return {
        "column": column,
        "semantic_type": "unknown",
        "display_name": column,
        "description": "",
        "format_hint": "",
        "confidence": 0.0,
        "source": "ai",
    }
