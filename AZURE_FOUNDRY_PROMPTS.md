# Data Quality Engine — Azure AI Foundry Prompt Pack

This document contains every LLM prompt used by the Master Data Profiler, packaged for Azure AI Foundry prompt flows. Each prompt is a separate flow step.

**Model used:** `gpt-4o-mini` (Azure OpenAI), `temperature=0`, `seed=42`, `response_format={"type":"json_object"}` for deterministic JSON output.

---

## 1. Master-Data Context Preamble (prepended to every Rule Generator call)

**Role:** `system` continuation — appended before the per-column or cross-field prompt to bias Uniqueness logic to the stream type.

```
MASTER-DATA CONTEXT
===================
Source system: {system_label}
Master-data stream: {stream_label}
Uniqueness expectation: {uniqueness_note}
```

Where `{uniqueness_note}` is one of three variants:

**Entity master (Customer, Vendor, Employee, GL, Cost Centre):**
```
The primary identifier MUST be globally unique in this dataset (it is a
canonical entity master — one row per business entity). Generate a Uniqueness
rule on the primary identifier directly. Composite keys are not required.
```

**Joined / denormalised view (Material × plant, GL × company code):**
```
Identifier columns are expected to REPEAT across rows in this dataset because
it is a joined / denormalised master-data view. Generate Uniqueness rules on the
COMPOSITE KEY (the primary identifier PLUS the column that drives the join —
e.g. plant, company code, language, controlling area), NOT on the identifier
alone. Do NOT propose a rule that says the primary identifier must be unique.
```

**Unspecified:**
```
Uniqueness expectations are not pre-declared. Infer them from the data shape:
if a column's values are 100% unique in the samples, propose a Uniqueness rule;
otherwise be conservative.
```

---

## 2. Per-Column Rule Generator (six-dimension rules per CDE)

**System prompt:**
```
You are a data quality expert. Return only valid JSON.
```

**User prompt:**
```
You are a data-quality rule engine. For the column described
below, output exactly six data-quality rules as JSON — one rule per
dimension — covering the standard six DQ dimensions. Cross-field rules
are handled by a separate pass and must NOT appear here.

COLUMN UNDER REVIEW
-------------------
Name: {column_name}
Pandas dtype: {data_type}
Null %: {null_pct}
Unique %: {unique_pct}
Distinct sample values (sorted, max 50): {sample_str}

EXTRACTED METADATA
------------------
- Maximum Length: {max_length} characters
- Data Type Hint: {data_type_hint}
- Numeric Precision: {precision}
- Numeric Scale: {scale}
- Mandatory Field: YES
- Uniqueness Required: YES
- Format Restrictions: {format_restrictions}
- Allowed Values: {allowed_values}
- Conditional Rule: {conditional_rule}
- Semantic Type: {semantic_type}
- Semantic Display Name: {semantic_display_name}
- Semantic Description: {semantic_description}
- Format Hint (from glossary): {semantic_format_hint}

DIMENSION DEFINITIONS (use these definitions verbatim)
------------------------------------------------------
- Accuracy: the value reflects the real-world entity it represents.
  Anchor on sample values and column semantics (e.g. an email column's
  values must be syntactically resolvable; an amount must be a non-negative
  number when the field is a price).
- Completeness: the value is present (not null, not blank, not whitespace).
- Standardisation: the value follows a uniform representation across rows
  (e.g. consistent casing, consistent date format, consistent code system).
- Timeliness: the value is current and within an expected time window.
  Only meaningful for date/time columns. For non-date columns, emit:
  "<Field>: timeliness is not applicable for non-date fields".
- Validation: the value satisfies the column's structural rules — data type,
  length, allowed values, regex / format pattern.
- Uniqueness: the value does not duplicate another row's value when the
  column is an identifier. For clearly non-identifier columns (categorical,
  low-cardinality, free text), emit:
  "<Field>: duplicates are allowed for this non-identifier field".

INSTRUCTIONS
------------
1. Emit exactly six rules — one per dimension — in the order listed in
   the schema below. Do not skip a dimension. If a dimension does not
   apply, use the "not applicable" phrasing shown in the definitions.
2. Rule wording: "<Field> must <verb> <condition>" (one concise sentence).
   The "not applicable" rules are the only exceptions.
3. Use evidence-based limits. If metadata supplies a max_length, allowed
   values, or a regex, use that exactly — do not invent thresholds.
4. The dimension field MUST be spelled EXACTLY as listed in the schema:
   Accuracy, Completeness, Standardisation, Timeliness, Validation, Uniqueness.
5. Do NOT propose any rule that mentions another column. Cross-field rules
   are produced by a separate pass.
6. Return ONLY a JSON object — no prose, no markdown fence.

OUTPUT SCHEMA (return exactly these keys, in this order)
--------------------------------------------------------
{
  "business_field": "<human-readable field name, derived from column name>",
  "rules": [
    { "dimension": "Accuracy",     "data_quality_rule": "<one sentence>" },
    { "dimension": "Completeness", "data_quality_rule": "<one sentence>" },
    { "dimension": "Standardisation",  "data_quality_rule": "<one sentence>" },
    { "dimension": "Timeliness",   "data_quality_rule": "<one sentence>" },
    { "dimension": "Validation",     "data_quality_rule": "<one sentence>" },
    { "dimension": "Uniqueness",   "data_quality_rule": "<one sentence>" }
  ]
}

WORKED EXAMPLE — VAT number column (mandatory)
----------------------------------------------
{
  "business_field": "VAT Number",
  "rules": [
    { "dimension": "Accuracy",     "data_quality_rule": "VAT Number must correspond to an active VAT registration with the issuing tax authority" },
    { "dimension": "Completeness", "data_quality_rule": "VAT Number must not be blank" },
    { "dimension": "Standardisation",  "data_quality_rule": "VAT Number must be stored in uppercase with no spaces, hyphens, or punctuation" },
    { "dimension": "Timeliness",   "data_quality_rule": "VAT Number: timeliness is not applicable for non-date fields" },
    { "dimension": "Validation",     "data_quality_rule": "VAT Number must be alphanumeric with length between 8 and 14 characters after normalization" },
    { "dimension": "Uniqueness",   "data_quality_rule": "VAT Number must be unique across all records once normalized" }
  ]
}
```

---

## 3. Cross-Field Rule Generator (whole-dataset, single call)

**System prompt:**
```
You are a data quality expert. Return only valid JSON.
```

**User prompt:**
```
You are a data-quality rule engine specialising in cross-field
constraints. Your job is to look at the WHOLE table below and propose
rules that involve TWO OR MORE columns at once. Single-column rules are
out of scope and must not appear in your output.

DATASET COLUMNS (with up to 5 sample values each)
-------------------------------------------------
{catalog_block}

HOW TO THINK ABOUT THIS
-----------------------
Read the column list once, top-down, and ask:

1. Which columns together IDENTIFY a record? (composite uniqueness)
   Prefer THREE-COLUMN tuples — they are stronger and more meaningful
   than 2-column tuples. A business name alone is too coarse; name +
   country + entity_type is the canonical customer-master key. Order
   number + line_number + fiscal_year, patient_id + visit_date + visit_type,
   etc. Always look for the FULL tuple, not the minimal one.

2. Which columns are PRESENT-OR-ABSENT depending on another column?
   Look for fields that only make sense for some values of another field
   — e.g. a tax-registration number required only for certain countries,
   or a discharge date required only when status = 'closed'. These often
   involve THREE columns: a target, a context, and a discriminator
   ("vat_no required when country is EU AND entity_type is Corporation").

3. Which columns DERIVE FROM another column?
   Look for prefixes, country codes, dialing codes, currency-from-locale,
   etc. A field that always begins with the value of another field, or is
   determined by a lookup from it. Don't stop at one pairwise rule — if
   country drives vat_no AND currency, propose both, or a single
   three-column rule.

4. Which columns satisfy ARITHMETIC identities?
   THREE OR FOUR COLUMNS is the norm here: net + tax = gross, quantity ×
   unit_price = line_total, start_date + duration = end_date, opening +
   debits − credits = closing. Always include every column in the
   identity, not just the two most obvious ones.

5. Which columns must REFERENCE THE SAME CONCEPT consistently?
   A country and a currency. A state and a country and a country code.
   A category and a sub-category and a top-level group. These chains are
   usually 3+ columns deep — chase the full chain.

6. Which columns have CONDITIONAL VALUES derived from another?
   "entity_type = LLP whenever company_type = LIMITED_LIABILITY_PARTNERSHIP".
   Often extends to a third column: "AND legal_status must be ACTIVE".

OUTPUT REQUIREMENTS
-------------------
- 0 to 10 cross-field rules total. Quality over quantity. One strong rule
  is better than three weak ones.
- Every rule MUST involve two or more columns from the dataset.
- STRONGLY PREFER 3+ column rules when the relationship genuinely spans
  three columns. Do not artificially split a 3-column composite-uniqueness
  rule into multiple 2-column rules — that loses information. Likewise,
  do not artificially merge unrelated 2-column rules into one 3-column
  rule.
- Use EXACT column names from the list above. Do not invent columns.
- Use specifics drawn from sample values where possible — a literal value
  list, a country code, a numeric tolerance. Avoid generic phrasings like
  "<a> and <b> must be consistent".
- If no honest cross-field rule exists in this dataset, return rules: [].
  An empty list is acceptable when the columns truly do not relate.
- Return ONLY a JSON object matching the schema below.

OUTPUT SCHEMA
-------------
{
  "rules": [
    {
      "data_quality_rule": "<one sentence — must mention two or more columns by exact name>",
      "columns": ["<column_a>", "<column_b>", "<...>"]
    }
  ]
}

WORKED EXAMPLE — customer master data
-------------------------------------
DATASET COLUMNS:
- name: ["Acme GmbH", "Brico SARL", "Globex Ltd"]
- country: ["DE", "FR", "GB", "IN"]
- entity_type: ["Corporation", "LLC", "Partnership"]
- vat_no: ["DE123456789", "FR12345678901"]
- pan_number: ["AAAPL1234C"]
- net_amount: ["100.00", "250.00"]
- tax_amount: ["18.00", "45.00"]
- gross_amount: ["118.00", "295.00"]
- currency: ["EUR", "USD"]

{
  "rules": [
    {
      "data_quality_rule": "Flag probable duplicate when normalized name fuzzy match is at least 85% and country and entity_type match exactly",
      "columns": ["name", "country", "entity_type"]
    },
    {
      "data_quality_rule": "vat_no must start with the 2-letter ISO code stored in country (e.g. country=DE → vat_no starts with DE)",
      "columns": ["vat_no", "country"]
    },
    {
      "data_quality_rule": "vat_no must be present when country is in [DE, FR, IT, ES, NL, GB] AND entity_type is 'Corporation'",
      "columns": ["vat_no", "country", "entity_type"]
    },
    {
      "data_quality_rule": "currency must equal EUR when country is in [DE, FR, IT, ES, NL] AND entity_type is 'Corporation' (Eurozone corporate accounts)",
      "columns": ["currency", "country", "entity_type"]
    },
    {
      "data_quality_rule": "gross_amount must equal net_amount + tax_amount within a tolerance of 0.01 in the same currency",
      "columns": ["gross_amount", "net_amount", "tax_amount", "currency"]
    }
  ]
}

Note in the example above: out of 5 rules, 4 of them involve 3+ columns.
That ratio (most rules being 3+ columns) is what we want for a real dataset
when the relationships genuinely span 3+ columns. Don't force it when only
2 columns relate, but don't artificially limit yourself to pairs either.
```

---

## 4. CDE Recommender + Semantic Classification (per-column metadata)

**System prompt:**
```
You are a senior master-data analyst. For each column in a tabular dataset you receive, produce three things:

  1. A clear one-sentence description of what the column represents.
  2. A boolean `recommended` flag — true iff the column is a Critical Data Element (CDE), i.e. a field important enough that the business would want data-quality rules running against it. CDEs are typically primary identifiers, tax / regulatory identifiers, legal or trade names, country / currency / company codes, or account numbers. Audit timestamps, soft-delete flags, free-text comments, and purely descriptive attributes (city, fax, search-term) are typically NOT CDEs.
  3. A `semantic_type` — exactly one short snake_case tag from the controlled list below that best classifies the column's value format. This drives downstream format-validation scoring. BIAS STRONGLY toward the specific identifier tag when either the column name OR the sample values match — never fall back to `alphanumeric_id`, `numeric_id`, `enum_code`, or `other` when a specific tag applies.

Controlled tag list:
       pan, gstin, tan, cin, vat, ein, ssn, aadhaar, iban, swift, ifsc, iso_country, iso_currency, email, phone, url, postal_code, indian_pin, numeric_id, alphanumeric_id, account_number, date, datetime, year, boolean, amount, quantity, percentage, free_text_name, free_text_address, free_text_description, enum_code, other.

Examples of correct classification (memorise these — they cover the most common mistakes):
  • column `pan_number` with values like ABCDE1234F → `pan` (NOT alphanumeric_id)
  • column `STCD1` with samples ABCDE1234F → `pan` (NOT tan, NOT alphanumeric_id)
  • column `gstin` with values like 27ABCDE1234F1Z5 → `gstin` (NOT alphanumeric_id)
  • column `STCD2` with samples 27ABCDE1234F1Z5 → `gstin`
  • column `email` with values like a@b.com → `email` (NOT free_text_description)
  • column `LAND1` with 2-letter values like IN, US → `iso_country` (NOT enum_code)
  • column `WAERS` with values INR, USD → `iso_currency`
  • column `pincode` with values like 400001 → `indian_pin`
  • column `ifsc_code` with values HDFC0000001 → `ifsc`
  • column `mobile` with values +91-9876543210 → `phone`
  • column `customer_name` with values like 'Acme Pvt Ltd' → `free_text_name`
  • column `created_at` with timestamps → `datetime`

Use `other` ONLY when no tag from the controlled list could plausibly apply. Free-text fields that are clearly names go to `free_text_name`, addresses to `free_text_address`, longer descriptions to `free_text_description` — not `other`.

Always return strict JSON. No markdown.
```

**User prompt:**
```
Dataset context: {system_label} · {stream_label}.

COLUMNS
=======
{columns_block_json}

RETURN THIS EXACT JSON SHAPE:
{
  "columns": [
    {
      "name": "<original column name, copied verbatim>",
      "description": "<one sentence, plain English, no jargon dump>",
      "recommended": true | false,
      "reason": "<≤12 words explaining the recommendation>",
      "semantic_type": "<one tag from the controlled list>"
    }
  ]
}

Rules:
1. The output array must include every column from the input in the same order.
2. Copy each column name verbatim into the `name` field — do not rename, case-fold, or translate.
3. `description` must be a single sentence describing the field's meaning. If the column is clearly an ERP technical code (e.g. SAP table.field), expand the acronym. Mention the format when obvious from samples.
4. `recommended` is true only if the field is a CDE per the system rules.
5. `reason` is short — it answers "why recommended" or "why not".
6. `semantic_type` is exactly one tag from the controlled list in the system message. When unsure between two tags, pick the more specific one. Default to 'other' only when no tag applies.
7. JSON only. No markdown fences, no commentary.
```

Where `{columns_block_json}` is an array like:
```json
[
  {"name": "pan_number", "samples": ["ABCDE1234F", "FGHIJ5678K", ...], "null_pct": 2.5, "unique_pct": 99.8},
  {"name": "country", "samples": ["IN", "US", "DE"], "null_pct": 0.0, "unique_pct": 12.4}
]
```

---

## 5. Cross-Field Rule → Pandas Expression Translator

Translates a free-text cross-field rule into an executable pandas boolean mask.

**System prompt:**
```
You are a data quality expert. Output strict JSON only.
```

**User prompt:**
```
You translate one English data-quality rule
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

Return ONLY the JSON object.
```

---

## 6. Single-Rule AI Resolver (English → regex for unmapped Cleansing rules)

Used when the Rule Generator couldn't translate a free-text rule into a regex.

**System prompt:**
```
You are a data quality regex expert. Output strict JSON only.
```

**User prompt:**
```
Column: {column}
Sample values: {samples}
Data quality rule: {rule_text}

Return ONLY a JSON object: {"regex": "<python re pattern that ACCEPTS valid values>", "applies": true|false, "explanation": "<one line>"}
Set applies=false if the rule cannot be encoded as a single-cell regex (e.g. cross-row uniqueness, fuzzy accuracy checks, business judgement). The regex must be a complete pattern (anchor with ^ and $ unless inappropriate).
```

---

## 7. Ad-hoc Cleansing AI Suggestion (user types a natural-language fix request)

**System prompt:**
```
You are a data quality expert. Respond only with valid JSON.
```

**User prompt:**
```
Column name: {column}
Sample values: {sample[:10]}
User request: {user_question}

Return ONLY a JSON object with these keys:
  mode (one of: Clean, Replace, Extract, Validate, Case, Length)
  pattern (regex string, if applicable)
  replace (replacement string, if mode is Replace)
  case (UPPERCASE / lowercase / Title Case, if mode is Case)
  explanation (one-line human description)
```

---

## Call Parameters (apply to all prompts above)

| Parameter | Value | Why |
|---|---|---|
| `model` | `gpt-4o-mini` (Azure OpenAI deployment) | Cost-optimised, sufficient for structured JSON output |
| `temperature` | `0` | Deterministic — same inputs always yield the same rules |
| `seed` | `42` | Reproducibility across runs (Foundry preview feature) |
| `response_format` | `{"type": "json_object"}` | Forces valid JSON without code-fence wrapping |
| `max_tokens` (per-column) | `1500` | Six rules with worked example fits comfortably |
| `max_tokens` (cross-field) | `1500` | 0–10 rules with column lists |
| `max_tokens` (CDE recommender) | `4000` | Per-column entries scale with dataset width |
| `max_tokens` (resolver / translator) | `300` | Single regex or expression |

---

## Recommended Foundry Flow Topology

```
[Upload dataset] ─► [Sample 50 rows / column]
                          │
                          ├──► CDE Recommender (Prompt 4)        — once per dataset
                          │       └─► caches semantic_type per column
                          │
                          ├──► Per-Column Rule Gen (Prompt 2)    — fan-out, one call per column
                          │       └─► six rules each
                          │
                          ├──► Cross-Field Rule Gen (Prompt 3)   — single whole-dataset call
                          │       └─► 0-10 multi-column rules
                          │
                          └──► [Steward review UI]
                                   │
                                   ├──► AI Resolver (Prompt 6)   — on unmapped rules, one call each
                                   └──► CF Translator (Prompt 5) — once per cross-field rule
```

Per-column generation should run in **parallel** with bounded concurrency (8 workers ≈ 22 calls/min, comfortably under Azure 60 RPM default).

---

## Post-Processing Filters

After receiving rule output, the engine applies these filters:

1. **Drop "not applicable" sentinels** — `"...not applicable for non-date fields"` and `"...duplicates are allowed for this non-identifier field"` rows are dropped.
2. **Drop Timeliness rules on non-date columns** when `semantic_type` is not in `{date, datetime, year, duration, age}`.
3. **Drop Uniqueness rules on non-identifier columns** when `semantic_type` is not identifier-shaped (`identifier_*`, `*_id`, `customer_id`, `employee_id`, etc.).
4. **Drop unverifiable Accuracy rules** — Accuracy rules with no regex pattern and no validation expression are tautological narratives ("X must accurately reflect the real-world entity") and are dropped at three layers (generation, read, mapping).
5. **Drop cross-field rules with hallucinated columns** — every column name in the rule's `columns` array must exist in the dataset; recover by scanning rule text for real column names; if fewer than 2 real columns are found, drop.
