"""1:1 port of features/profiling/ui.py AIValidationEngine + DynamicValidationDetector.

The AI prompt is COPIED VERBATIM from lines 274-365 — do not edit wording without
matching the Streamlit version.
"""
from __future__ import annotations

import hashlib
import json
import logging
import re
import time
from datetime import datetime
from typing import Any, Callable, Dict, List, Optional

import pandas as pd

from .azure_openai_config import AzureOpenAIConfig
from .excel_metadata import (
    extract_column_metadata,
    extract_excel_cell_notes,
    extract_client_rules_from_excel_metadata,
)

logger = logging.getLogger(__name__)


class AIValidationEngine:
    """Mirror of features/profiling/ui.py AIValidationEngine (lines 179-617)."""

    DQ_DIMENSIONS = [
        "Accuracy", "Completeness", "Consistency", "Validity",
        "Uniqueness", "Timeliness", "Integrity", "Conformity",
        "Reliability", "Relevance", "Precision", "Accessibility",
        "Character Length",
    ]

    def __init__(self) -> None:
        self.client = None
        self.cache: Dict[str, Any] = {}
        self._init_warning: Optional[str] = None
        self._initialize_client()

    def _initialize_client(self) -> None:
        try:
            missing = AzureOpenAIConfig.validate()
            if missing:
                self._init_warning = (
                    f"Azure OpenAI not configured. Missing: {', '.join(missing)}"
                )
                return
            from openai import AzureOpenAI
            self.client = AzureOpenAI(
                azure_endpoint=AzureOpenAIConfig.AZURE_OPENAI_ENDPOINT,
                api_key=AzureOpenAIConfig.AZURE_OPENAI_KEY,
                api_version=AzureOpenAIConfig.AZURE_OPENAI_API_VERSION,
            )
        except Exception as exc:
            self._init_warning = f"Failed to initialize Azure OpenAI: {exc}"

    def _get_cache_key(self, column_name: str, sample_data: List[str], data_type: str) -> str:
        data_hash = hashlib.md5(str(sample_data[:50]).encode()).hexdigest()
        return f"{column_name}_{data_type}_{data_hash}"

    def _call_azure_openai(self, messages: List[Dict], temperature: float = 0.1) -> Optional[str]:
        if not self.client:
            return None
        try:
            response = self.client.chat.completions.create(
                model=AzureOpenAIConfig.AZURE_OPENAI_DEPLOYMENT,
                messages=messages,
                temperature=temperature,
                max_completion_tokens=4000,
            )
            return response.choices[0].message.content
        except Exception as exc:
            error_msg = str(exc)
            if "token" in error_msg.lower() or "length" in error_msg.lower():
                logger.warning("Token limit reached. Using fallback rules.")
                return None
            logger.error("Azure OpenAI API Error: %s", error_msg)
            raise

    def analyze_column_semantic_type(
        self,
        column_name: str,
        sample_data: List[str],
        data_type: str,
        null_pct: float,
        unique_pct: float,
        metadata: Optional[Dict[str, Any]] = None,
        excel_notes: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Verbatim port of features/profiling/ui.py:238-385."""
        cache_key = self._get_cache_key(column_name, sample_data, data_type)
        if cache_key in self.cache:
            return self.cache[cache_key]

        samples = sample_data[:100] if sample_data else []
        sample_str = json.dumps(samples, indent=2)

        metadata_section = ""
        if metadata:
            metadata_section = "\nEXTRACTED METADATA FROM COLUMN NAME:\n"
            if metadata.get("max_length"):
                metadata_section += f"- Maximum Length: {metadata['max_length']} characters\n"
            if metadata.get("data_type_hint"):
                metadata_section += f"- Data Type Hint: {metadata['data_type_hint']}\n"

        if excel_notes:
            metadata_section += f"\nEXCEL NOTES/COMMENTS:\n{excel_notes}\n"

        # ===== PROMPT COPIED VERBATIM FROM STREAMLIT =====
        prompt = f"""Analyze this data column and generate human-readable validation rules.

COLUMN INFORMATION
==================
Column Name: {column_name}
Data Type: {data_type}
Sample Values: {sample_str}
Null Percentage: {null_pct:.1f}%
Unique Percentage: {unique_pct:.1f}%
{metadata_section}

IMPORTANT INSTRUCTIONS
======================
1. If METADATA shows a maximum length (e.g., VARCHAR2(360), CHAR(19)), you MUST create a "Conformity" rule for it
   Example: "Supplier Name must not exceed 360 characters"

2. If EXCEL NOTES contain validation rules or constraints, incorporate them into your rules

3. Even if the column has NO DATA (100% null), still generate meaningful rules based on:
   - Column name semantics
   - Metadata constraints
   - Excel notes
   - Industry standards for that field type

REQUIRED OUTPUT FORMAT
======================
Return a JSON object with this exact structure:

{{
  "business_field_name": "Human-friendly field name (e.g., 'Posting Date', 'Email Address', 'Mobile Number')",
  "rules": [
    {{
      "dimension": "One of: Accuracy, Completeness, Consistency, Validity, Uniqueness, Timeliness, Integrity, Conformity, Reliability, Relevance, Precision, Accessibility, Character Length",
      "rule_statement": "Human readable rule in format: [Field Name] + Must/Should + Business Condition. Example: 'Posting Date must not be future dated'"
    }}
  ]
}}

RULE WRITING GUIDELINES
=======================
Write rules in this exact format: [Field Name] + Must/Should + Business Condition

EXAMPLES BY FIELD TYPE:

Date Fields (Date of Birth, Posting Date, Invoice Date):
- Date of Birth must be a valid calendar date
- Date of Birth cannot be in the future
- Date of Birth cannot be more than 120 years in the past
- Posting Date must not be future dated
- Posting Date must be within the active financial period
- Invoice Date should not be blank

Email Fields (Email Address):
- Email Address must follow standard email format
- Email Address must contain @ symbol
- Email Address must contain valid domain name
- Email Address should not contain spaces
- Email Address must be unique for each customer

Phone Fields (Mobile Number, Phone):
- Mobile Number must contain only digits
- Mobile Number must have 10 digits
- Mobile Number must start with valid prefix (6,7,8,9)
- Mobile Number should not contain special characters

ID Fields (PAN, GST, Asset ID):
- PAN must follow government issued format
- PAN must be 10 characters
- PAN must be alphanumeric
- Asset ID must follow organization coding standard

Amount Fields (Amount, Cost, Price):
- Amount must be numeric
- Amount should not be negative
- Amount must have maximum 2 decimal places
- Amount should not exceed defined business limit

Text Fields (Description, Name):
- Description should not be blank
- Description should not contain only special characters
- Description should not contain generic values like "Test" or "NA"

REQUIREMENTS
============
1. Generate 1-3 meaningful rules per column
2. Use exact format: [Field Name] + Must/Should + Business Condition
3. Rules must be immediately understandable by business users
4. No technical jargon, regex, or code references
5. Each rule should be actionable and specific
6. Assign most appropriate DQ dimension

Return ONLY valid JSON, no markdown."""
        # ===== END VERBATIM PROMPT =====

        messages = [
            {
                "role": "system",
                "content": (
                    "You are a Business Data Analyst who writes clear, "
                    "human-readable data quality rules for enterprise systems. "
                    "Return only JSON."
                ),
            },
            {"role": "user", "content": prompt},
        ]

        response = self._call_azure_openai(messages, temperature=0.1)
        if response:
            try:
                cleaned = re.sub(r"```json\s*|\s*```", "", response).strip()
                result = json.loads(cleaned)
                self.cache[cache_key] = result
                return result
            except json.JSONDecodeError as exc:
                logger.warning("Failed to parse AI response for %s: %s", column_name, exc)

        return self._fallback_analysis(column_name, sample_data, data_type, null_pct, unique_pct)

    def _fallback_analysis(self, column_name: str, sample_data: List[str],
                           data_type: str, null_pct: float, unique_pct: float) -> Dict[str, Any]:
        rules = []
        field_name = column_name.replace("_", " ").title()
        if null_pct > 0:
            rules.append({"dimension": "Completeness",
                          "rule_statement": f"{field_name} should not be blank or null"})
        if unique_pct >= 95:
            rules.append({"dimension": "Uniqueness",
                          "rule_statement": f"{field_name} must be unique"})
        if "date" in data_type.lower():
            rules.append({"dimension": "Validity",
                          "rule_statement": f"{field_name} must be a valid calendar date"})
            rules.append({"dimension": "Timeliness",
                          "rule_statement": f"{field_name} must not be future dated"})
        elif "int" in data_type.lower() or "float" in data_type.lower():
            rules.append({"dimension": "Validity",
                          "rule_statement": f"{field_name} must be numeric"})
        elif "object" in data_type.lower():
            rules.append({"dimension": "Validity",
                          "rule_statement": f"{field_name} must contain valid text"})
        return {"business_field_name": field_name, "rules": rules}

    def generate_dynamic_rules(self, df: pd.DataFrame, column_name: str,
                               profile: Any, excel_notes: Optional[Dict[str, str]] = None
                               ) -> List[Dict[str, Any]]:
        metadata = extract_column_metadata(column_name)
        notes = excel_notes.get(column_name) if excel_notes else None
        sample_data = df[column_name].dropna().astype(str).head(100).tolist()
        data_type = str(profile.dtype)
        null_pct = profile.null_percentage
        unique_pct = profile.unique_percentage

        ai_analysis = self.analyze_column_semantic_type(
            column_name, sample_data, data_type, null_pct, unique_pct,
            metadata=metadata, excel_notes=notes,
        )

        rules: List[Dict[str, Any]] = []
        field_name = ai_analysis.get("business_field_name", column_name)
        for rule in ai_analysis.get("rules", []):
            dimension = rule.get("dimension", "Validity")
            if dimension not in self.DQ_DIMENSIONS:
                dimension = "Validity"
            rules.append({
                "S.No": len(rules) + 1,
                "Column": column_name,
                "Business Field": field_name,
                "Dimension": dimension,
                "Data Quality Rule": rule.get("rule_statement", "No rule specified"),
                "Source": "AI Generated",
            })
        return rules

    def validate_data_against_rules(self, df: pd.DataFrame, rules: List[Dict]) -> pd.DataFrame:
        """Verbatim port of features/profiling/ui.py:506-617."""
        validation_results: List[Dict[str, Any]] = []

        for rule in rules:
            column = rule.get("Column")
            if column not in df.columns:
                continue
            rule_statement = (rule.get("Data Quality Rule") or "").lower()
            invalid_count = 0
            invalid_examples: List[Any] = []

            try:
                if "not be blank" in rule_statement or "not be null" in rule_statement:
                    mask = df[column].isna()
                    invalid_count = int(mask.sum())
                    invalid_examples = df[mask][column].head(5).tolist()
                elif "unique" in rule_statement:
                    mask = df[column].duplicated(keep=False)
                    invalid_count = int(mask.sum())
                    dup_values = df[mask][column].value_counts().head(3)
                    invalid_examples = [f"{val} ({count} times)" for val, count in dup_values.items()]
                elif "valid calendar date" in rule_statement or "valid date" in rule_statement:
                    converted = pd.to_datetime(df[column], errors="coerce")
                    mask = converted.isna() & df[column].notna()
                    invalid_count = int(mask.sum())
                    invalid_examples = df[mask][column].head(5).astype(str).tolist()
                elif "not be future dated" in rule_statement or "not be in the future" in rule_statement:
                    try:
                        dates = pd.to_datetime(df[column], errors="coerce")
                        mask = dates > datetime.now()
                        invalid_count = int(mask.sum())
                        invalid_examples = df[mask][column].head(5).astype(str).tolist()
                    except Exception:
                        invalid_count = 0
                elif "numeric" in rule_statement:
                    converted = pd.to_numeric(df[column], errors="coerce")
                    mask = converted.isna() & df[column].notna()
                    invalid_count = int(mask.sum())
                    invalid_examples = df[mask][column].head(5).astype(str).tolist()
                elif "not be negative" in rule_statement:
                    try:
                        numeric_vals = pd.to_numeric(df[column], errors="coerce")
                        mask = numeric_vals < 0
                        invalid_count = int(mask.sum())
                        invalid_examples = df[mask][column].head(5).astype(str).tolist()
                    except Exception:
                        invalid_count = 0
                elif "only digits" in rule_statement:
                    mask = ~df[column].astype(str).str.match(r"^\d+$")
                    invalid_count = int(mask.sum())
                    invalid_examples = df[mask][column].head(5).astype(str).tolist()
                elif "email" in rule_statement:
                    pat = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
                    mask = ~df[column].astype(str).str.match(pat)
                    invalid_count = int(mask.sum())
                    invalid_examples = df[mask][column].head(5).astype(str).tolist()
                elif "alphanumeric" in rule_statement:
                    mask = ~df[column].astype(str).str.match(r"^[a-zA-Z0-9]+$")
                    invalid_count = int(mask.sum())
                    invalid_examples = df[mask][column].head(5).astype(str).tolist()
                elif "maximum" in rule_statement and "character" in rule_statement:
                    m = re.search(r"maximum (\d+) character", rule_statement)
                    if m:
                        max_len = int(m.group(1))
                        mask = df[column].astype(str).str.len() > max_len
                        invalid_count = int(mask.sum())
                        invalid_examples = df[mask][column].head(5).astype(str).tolist()
                else:
                    invalid_count = 0
                    invalid_examples = []
            except Exception:
                invalid_count = 0
                invalid_examples = []

            if invalid_count == 0:
                examples_str = "All values valid - No issues found"
            elif invalid_examples:
                cleaned = []
                for ex in invalid_examples:
                    s = str(ex).strip()
                    if len(s) > 50:
                        s = s[:47] + "..."
                    cleaned.append(s)
                examples_str = "; ".join(cleaned)
            else:
                examples_str = f"{invalid_count} issues found (examples not captured)"

            validation_results.append({
                "Column": column,
                "Dimension": rule.get("Dimension"),
                "Source": rule.get("Source", "Unknown"),
                "Invalid_Count": int(invalid_count),
                "Issues_Found_Example": examples_str,
            })

        return pd.DataFrame(validation_results)


class DynamicValidationDetector:
    """Mirror of features/profiling/ui.py DynamicValidationDetector (lines 624-965)."""

    def __init__(self) -> None:
        self.ai_engine = AIValidationEngine()
        self.excel_notes: Dict[str, str] = {}

    def _generate_fallback_rules(self, column_name: str, profile: Any) -> List[Dict]:
        rules: List[Dict] = []
        if profile.null_percentage > 0:
            rules.append({
                "S.No": 1, "Column": column_name, "Business Field": column_name,
                "Dimension": "Completeness",
                "Data Quality Rule": f"{column_name} should not be blank",
                "Source": "AI Generated",
            })
        if profile.unique_percentage > 95:
            rules.append({
                "S.No": len(rules) + 1, "Column": column_name, "Business Field": column_name,
                "Dimension": "Uniqueness",
                "Data Quality Rule": f"{column_name} must be unique",
                "Source": "AI Generated",
            })
        dtype_lower = str(profile.dtype).lower()
        if "int" in dtype_lower or "float" in dtype_lower:
            rules.append({
                "S.No": len(rules) + 1, "Column": column_name, "Business Field": column_name,
                "Dimension": "Validity",
                "Data Quality Rule": f"{column_name} must be numeric",
                "Source": "AI Generated",
            })
        elif "date" in dtype_lower:
            rules.append({
                "S.No": len(rules) + 1, "Column": column_name, "Business Field": column_name,
                "Dimension": "Validity",
                "Data Quality Rule": f"{column_name} must be a valid date",
                "Source": "AI Generated",
            })
        return rules

    def detect_all_validations(
        self, df: pd.DataFrame, profiles: Dict, file_path: Optional[str] = None,
        sheet_name: Optional[str] = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> List[Dict]:
        """Verbatim port of features/profiling/ui.py:631-807, with progress callback
        replacing st.progress / st.empty."""
        if file_path:
            try:
                self.excel_notes = extract_excel_cell_notes(file_path, sheet_name)
            except Exception:
                self.excel_notes = {}

        all_validations: List[Dict] = []
        total_cols = len(df.columns)
        if total_cols == 0:
            return []

        successful_cols = 0
        failed_cols: List[str] = []
        skipped_cols = 0
        api_calls = 0
        max_api_calls_per_minute = AzureOpenAIConfig.MAX_REQUESTS_PER_MINUTE

        for idx, col in enumerate(df.columns):
            try:
                if progress_cb:
                    progress_cb({
                        "stage": "analyzing",
                        "index": idx + 1, "total": total_cols, "column": str(col),
                        "successful": successful_cols, "failed": len(failed_cols),
                    })

                if col not in profiles:
                    skipped_cols += 1
                    continue
                profile = profiles[col]

                # Rate limit: 60s pause when MAX_RPM hit (Streamlit parity).
                if api_calls >= max_api_calls_per_minute:
                    if progress_cb:
                        progress_cb({"stage": "rate_limit_pause", "wait": 60})
                    time.sleep(60)
                    api_calls = 0

                max_retries = 2
                rules_generated = False
                for attempt in range(max_retries):
                    try:
                        rules = self.ai_engine.generate_dynamic_rules(
                            df, col, profile, excel_notes=self.excel_notes,
                        )
                        if rules:
                            all_validations.extend(rules)
                            successful_cols += 1
                            api_calls += 1
                            rules_generated = True
                            break
                    except Exception as exc:
                        msg = str(exc).lower()
                        if "rate" in msg or "quota" in msg:
                            if progress_cb:
                                progress_cb({"stage": "rate_limit_pause", "wait": 60})
                            time.sleep(60)
                            api_calls = 0
                        elif attempt == max_retries - 1:
                            failed_cols.append(str(col))
                            fallback = self._generate_fallback_rules(col, profile)
                            all_validations.extend(fallback)
                        else:
                            time.sleep(2)

                if rules_generated:
                    time.sleep(0.5)
            except Exception:
                failed_cols.append(str(col))
                try:
                    all_validations.extend(self._generate_fallback_rules(col, profile))
                except Exception:
                    pass

        if progress_cb:
            progress_cb({
                "stage": "complete",
                "total": total_cols, "successful": successful_cols,
                "failed_count": len(failed_cols), "skipped": skipped_cols,
                "failed_cols": failed_cols,
            })
        return all_validations

    def generate_comprehensive_dq_rules(
        self, df: pd.DataFrame, profiles: Dict,
        file_path: Optional[str] = None, sheet_name: Optional[str] = None,
        progress_cb: Optional[Callable[[Dict[str, Any]], None]] = None,
    ) -> pd.DataFrame:
        """Verbatim port of features/profiling/ui.py:859-965.

        Combines client rules (Excel metadata) + AI rules + validation results.
        """
        # 1) client rules
        client_rules = extract_client_rules_from_excel_metadata(file_path, sheet_name, df)

        # 2) AI rules
        ai_rules = self.detect_all_validations(
            df, profiles, file_path=file_path, sheet_name=sheet_name,
            progress_cb=progress_cb,
        )

        all_rules = list(client_rules) + list(ai_rules)

        # 3) validate against data
        validation_results = self.ai_engine.validate_data_against_rules(df, all_rules)

        if not validation_results.empty:
            validation_results = validation_results.copy()
            validation_results["Column"] = validation_results["Column"].astype(str)
            validation_results["Dimension"] = validation_results["Dimension"].astype(str)
            validation_results["Source"] = validation_results["Source"].astype(str)
            agg_val = validation_results.groupby(
                ["Column", "Dimension", "Source"], sort=False,
            ).agg({
                "Invalid_Count": "sum",
                "Issues_Found_Example": lambda x: "; ".join(
                    [str(v) for v in x if pd.notna(v) and v != "All values valid - No issues found"]
                ) or "All values valid - No issues found",
            }).reset_index()
        else:
            agg_val = pd.DataFrame(columns=["Column", "Dimension", "Source",
                                            "Invalid_Count", "Issues_Found_Example"])

        # 4) merge by (Column, Dimension, Source)
        rules_map: Dict[Any, Dict[str, Any]] = {}
        for rule in all_rules:
            col = rule.get("Column")
            dim = rule.get("Dimension")
            src = rule.get("Source", "Unknown")
            key = (col, dim, src)
            rules_map.setdefault(key, {"Business Field": rule.get("Business Field"), "Rules": []})
            stmt = rule.get("Data Quality Rule")
            if stmt and stmt not in rules_map[key]["Rules"]:
                rules_map[key]["Rules"].append(stmt)

        # 5) build output rows
        output: List[Dict[str, Any]] = []
        for idx, ((col, dim, src), meta) in enumerate(rules_map.items(), 1):
            match = agg_val[(agg_val["Column"] == col)
                            & (agg_val["Dimension"] == dim)
                            & (agg_val["Source"] == src)]
            invalid_count = int(match.iloc[0]["Invalid_Count"]) if not match.empty else 0
            issues_example = (match.iloc[0]["Issues_Found_Example"]
                              if not match.empty
                              else "All values valid - No issues found")

            if src == "Client Extracted":
                source_label = "Client provided rule - From Excel metadata"
            elif src == "AI Generated":
                source_label = "AI Generated"
            else:
                source_label = src

            output.append({
                "S.No": idx,
                "Column": col,
                "Business Field": meta.get("Business Field"),
                "Dimension": dim,
                "Data Quality Rule": "; ".join(meta.get("Rules", [])),
                "Issues Found": invalid_count,
                "Issues Found Example": issues_example,
                "Source": source_label,
            })
        return pd.DataFrame(output)
