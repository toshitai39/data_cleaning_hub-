"""Pydantic schemas for API requests and responses."""
from __future__ import annotations

from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field


# ---------- auth ----------------------------------------------------------

class LoginRequest(BaseModel):
    username: str
    password: str


class LoginResponse(BaseModel):
    session_id: str
    username: str
    name: str


# ---------- load data -----------------------------------------------------

class LoadResponse(BaseModel):
    filename: str
    rows: int
    columns: int
    column_names: List[str]
    dtypes: Dict[str, str]
    preview: List[Dict[str, Any]]
    sheets: Optional[List[str]] = None


# ---------- profiling -----------------------------------------------------

class ColumnProfileOut(BaseModel):
    column_name: str
    dtype: str
    human_readable_dtype: str
    total_rows: int
    null_count: int
    null_percentage: float
    unique_count: int
    unique_percentage: float
    duplicate_count: int
    duplicate_percentage: float
    memory_usage: str
    risk_score: int
    risk_level: str
    key_issues: List[str] = []
    suggestions: List[str] = []
    sample_values: List[Any] = []
    min_length: int = 0
    max_length: int = 0
    avg_length: float = 0.0
    pattern_counts: Dict[str, int] = {}
    cleansing_recommendations: List[Dict[str, Any]] = []


class QualityReportOut(BaseModel):
    total_rows: int
    total_columns: int
    total_cells: int
    missing_cells: int
    missing_percentage: float
    exact_duplicate_rows: int
    exact_duplicate_percentage: float
    fuzzy_duplicate_groups: int
    fuzzy_duplicate_rows: int
    columns_with_issues: List[str]
    overall_score: float


class ProfileResponse(BaseModel):
    quality_report: QualityReportOut
    columns: List[ColumnProfileOut]
    dtype_distribution: Dict[str, int]


# ---------- duplicates ----------------------------------------------------

class DuplicateGroupOut(BaseModel):
    group_id: int
    indices: List[int]
    values: List[Dict[str, Any]]
    match_type: str
    similarity_score: Optional[float] = None
    key_columns: List[str] = []
    representative_value: Optional[str] = None


class FindExactDuplicatesRequest(BaseModel):
    subset: Optional[List[str]] = None


class FindFuzzyDuplicatesRequest(BaseModel):
    columns: List[str]
    threshold: float = 85.0
    algorithm: str = "rapidfuzz"


class RemoveDuplicatesRequest(BaseModel):
    subset: Optional[List[str]] = None
    keep: str = "first"


# ---------- preview / data --------------------------------------------------

class PreviewResponse(BaseModel):
    page: int
    page_size: int
    total_rows: int
    total_pages: int
    columns: List[str]
    rows: List[Dict[str, Any]]


class CompareResponse(BaseModel):
    original_rows: int
    modified_rows: int
    original_columns: int
    modified_columns: int
    rows_changed: int
    columns_added: List[str]
    columns_removed: List[str]
    operations: List[Dict[str, Any]]


# ---------- quality / rules -----------------------------------------------

class GenerateRulesRequest(BaseModel):
    columns: Optional[List[str]] = None


class ApplyRulesRequest(BaseModel):
    rules: List[Dict[str, Any]]


class QualityResultOut(BaseModel):
    column: str
    dimension: str = "—"
    rule: str
    pass_count: int
    fail_count: int
    fail_percentage: float
    sample_failures: List[Any] = []


# ---------- export --------------------------------------------------------

class ExportRequest(BaseModel):
    format: str = Field(default="csv", description="csv|xlsx|parquet|json|feather")
    columns: Optional[List[str]] = None
    sample_pct: Optional[float] = None


# ---------- multi-file ----------------------------------------------------

class MultiFileSchemaResponse(BaseModel):
    files: List[str]
    schema_table: List[Dict[str, Any]]
    stats: List[Dict[str, Any]]


# ---------- audit ---------------------------------------------------------

class AuditEntry(BaseModel):
    id: int
    timestamp: str
    username: Optional[str] = None
    action: Optional[str] = None
    detail: Optional[str] = None
    category: Optional[str] = None
    row_count: Optional[int] = None
    col_count: Optional[int] = None
    filename: Optional[str] = None
