"""Export endpoints — 1:1 parity with features/export/ui.py.

Endpoints:
  POST /export/single           single-file export (CSV/Excel/Parquet/JSON/Feather)
  POST /export/batch            ZIP of multiple chunks (large datasets)
  POST /export/report/html      profiling report (HTML)
  POST /export/report/pdf       profiling report (PDF, falls back to HTML if xhtml2pdf missing)
"""
from __future__ import annotations

import gzip
import io
import zipfile
from datetime import datetime
from typing import List, Optional

import pandas as pd
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel

from ..deps import require_dataframe
from ..session_store import SessionData

# Import features/export/pdf_report.py directly (Streamlit-free).
import importlib.util as _imp
import sys as _sys
from pathlib import Path as _Path

_root = _Path(__file__).resolve().parents[3]
_pdf_spec = _imp.spec_from_file_location("_pdf_report", str(_root / "features/export/pdf_report.py"))
_pdf_mod = _imp.module_from_spec(_pdf_spec)
_sys.modules["_pdf_report"] = _pdf_mod
_pdf_spec.loader.exec_module(_pdf_mod)
generate_profiling_report_html = _pdf_mod.generate_profiling_report_html
html_to_pdf_bytes = _pdf_mod.html_to_pdf_bytes


router = APIRouter(prefix="/export", tags=["export"])


# ---------- schemas ------------------------------------------------------

class SingleExportBody(BaseModel):
    format: str  # "CSV" | "Excel" | "Parquet" | "JSON" | "Feather"
    columns: Optional[List[str]] = None     # None or [] → all
    sample_pct: int = 100                    # 1-100
    include_index: bool = False
    encoding: str = "utf-8"
    compression: str = "none"                # "none" | "gzip" | "zip" | "bz2"
    delimiter: str = ","
    quotechar: str = '"'


class BatchExportBody(BaseModel):
    format: str
    rows_per_file: int = 100_000
    columns: Optional[List[str]] = None


# ---------- helpers ------------------------------------------------------

def _select_and_sample(df: pd.DataFrame, columns: Optional[List[str]],
                       sample_pct: int) -> pd.DataFrame:
    if columns:
        valid = [c for c in columns if c in df.columns]
        if valid:
            df = df[valid]
    if sample_pct < 100:
        df = df.sample(frac=sample_pct / 100, random_state=42)
    return df


def _stream(data: bytes, media: str, filename: str) -> StreamingResponse:
    return StreamingResponse(
        io.BytesIO(data),
        media_type=media,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


# ---------- single-file export ------------------------------------------

@router.post("/single")
def export_single(body: SingleExportBody, sess: SessionData = Depends(require_dataframe)):
    """Verbatim port of _generate_export."""
    df = _select_and_sample(sess.df, body.columns, body.sample_pct)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"export_{timestamp}"
    fmt = body.format

    try:
        if fmt == "CSV":
            if body.compression != "none":
                filename = f"{base}.csv.{body.compression}"
                csv_text = df.to_csv(
                    index=body.include_index, encoding=body.encoding,
                    compression=body.compression,
                    sep=body.delimiter, quotechar=body.quotechar,
                )
                # When compression is requested without a path, pandas returns the
                # compressed bytes as a string-of-bytes on some versions; force
                # bytes-on-disk by writing through BytesIO.
                if isinstance(csv_text, str):
                    data = csv_text.encode(body.encoding)
                else:
                    data = csv_text  # already bytes
            else:
                filename = f"{base}.csv"
                data = df.to_csv(
                    index=body.include_index, encoding=body.encoding,
                    sep=body.delimiter, quotechar=body.quotechar,
                ).encode(body.encoding, errors="replace")
            return _stream(data, "text/csv", filename)

        if fmt == "Excel":
            if len(df) > 1_048_576:
                raise HTTPException(
                    status_code=400,
                    detail="Excel limit exceeded (1,048,576 rows). Use Parquet or CSV instead.",
                )
            filename = f"{base}.xlsx"
            output = io.BytesIO()
            with pd.ExcelWriter(output, engine="openpyxl") as writer:
                df.to_excel(writer, index=body.include_index, sheet_name="Data")
            return _stream(
                output.getvalue(),
                "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
                filename,
            )

        if fmt == "Parquet":
            filename = f"{base}.parquet"
            output = io.BytesIO()
            df.to_parquet(output, index=body.include_index, compression="snappy")
            return _stream(output.getvalue(), "application/octet-stream", filename)

        if fmt == "JSON":
            json_str = df.to_json(orient="records", indent=2)
            if body.compression != "none":
                # Streamlit only supports gzip for JSON
                filename = f"{base}.json.gz"
                data = gzip.compress(json_str.encode("utf-8"))
            else:
                filename = f"{base}.json"
                data = json_str.encode("utf-8")
            return _stream(data, "application/json", filename)

        if fmt == "Feather":
            filename = f"{base}.feather"
            output = io.BytesIO()
            df.reset_index(drop=True).to_feather(output)
            return _stream(output.getvalue(), "application/octet-stream", filename)

        raise HTTPException(status_code=400, detail=f"Unsupported format: {fmt}")

    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Export failed: {exc}")


# ---------- batch export -------------------------------------------------

@router.post("/batch")
def export_batch(body: BatchExportBody, sess: SessionData = Depends(require_dataframe)):
    """Verbatim port of _generate_batch_export — ZIP of N chunks."""
    df = sess.df
    columns = body.columns or list(df.columns.astype(str))
    columns = [c for c in columns if c in df.columns]
    if not columns:
        columns = list(df.columns.astype(str))
    total_rows = len(df)
    rows_per_file = max(1, body.rows_per_file)
    num_files = (total_rows + rows_per_file - 1) // rows_per_file

    zip_buffer = io.BytesIO()
    with zipfile.ZipFile(zip_buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        for i in range(num_files):
            start_idx = i * rows_per_file
            end_idx = min((i + 1) * rows_per_file, total_rows)
            chunk = df.iloc[start_idx:end_idx][columns]
            if body.format == "CSV":
                chunk_bytes = chunk.to_csv(index=False).encode("utf-8")
                fname = f"batch_{i+1:03d}_{start_idx}_{end_idx}.csv"
            elif body.format == "Parquet":
                buf = io.BytesIO()
                chunk.to_parquet(buf, compression="snappy", index=False)
                chunk_bytes = buf.getvalue()
                fname = f"batch_{i+1:03d}_{start_idx}_{end_idx}.parquet"
            else:
                # Default fallback like Streamlit
                chunk_bytes = chunk.to_csv(index=False).encode("utf-8")
                fname = f"batch_{i+1:03d}_{start_idx}_{end_idx}.csv"
            zf.writestr(fname, chunk_bytes)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _stream(
        zip_buffer.getvalue(),
        "application/zip",
        f"batch_export_{timestamp}.zip",
    )


# ---------- client-grade DQ report (HTML / PDF) -------------------------

from sqlalchemy.orm import Session  # noqa: E402
from ..db import get_db  # noqa: E402
from ..models import Project  # noqa: E402
from ..services.cleansing_report import (  # noqa: E402
    build_report_html as _build_dq_report_html,
    html_to_pdf_bytes as _dq_html_to_pdf,
)
from ..services.stream_context import build_project_context  # noqa: E402


def _resolve_project_context(sess: SessionData, db: Session):
    """Look up the active project's master-data context so the report
    cover and DAMA Uniqueness scoring reflect entity-master vs joined-view
    semantics correctly."""
    if not sess.active_project_id or not sess.user or not sess.user.get("username"):
        return {}
    project = (
        db.query(Project)
        .filter(
            Project.id == sess.active_project_id,
            Project.user_username == sess.user["username"],
        )
        .one_or_none()
    )
    return build_project_context(project) if project is not None else {}


@router.post("/report/html")
def report_html(sess: SessionData = Depends(require_dataframe),
                db: Session = Depends(get_db)):
    """Client-grade Data Quality report — covers cleansing actions,
    rejected rows, DAMA dimension scorecard, per-CDE health, and
    recommended next steps. Sourced live from session state, so the
    numbers always match what the steward sees on screen."""
    project_context = _resolve_project_context(sess, db)
    html = _build_dq_report_html(sess, project_context=project_context)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = (sess.filename or "dataset").rsplit(".", 1)[0]
    return _stream(
        html.encode("utf-8"),
        "text/html",
        f"data_quality_report_{base}_{timestamp}.html",
    )


@router.post("/report/pdf")
def report_pdf(sess: SessionData = Depends(require_dataframe),
               db: Session = Depends(get_db)):
    """PDF version of the client-grade report. Falls back to HTML
    download when xhtml2pdf is not installed in the runtime."""
    project_context = _resolve_project_context(sess, db)
    html = _build_dq_report_html(sess, project_context=project_context)
    pdf_bytes = _dq_html_to_pdf(html)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = (sess.filename or "dataset").rsplit(".", 1)[0]
    if pdf_bytes:
        return _stream(
            pdf_bytes, "application/pdf",
            f"data_quality_report_{base}_{timestamp}.pdf",
        )
    return _stream(
        html.encode("utf-8"),
        "text/html",
        f"data_quality_report_{base}_{timestamp}.html",
    )
