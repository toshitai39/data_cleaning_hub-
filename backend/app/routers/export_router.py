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


# ---------- profiling report (HTML / PDF) -------------------------------

@router.post("/report/html")
def report_html(sess: SessionData = Depends(require_dataframe)):
    html = generate_profiling_report_html(
        sess.df, sess.column_profiles, sess.quality_report, sess.filename,
    )
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return _stream(
        html.encode("utf-8"),
        "text/html",
        f"profiling_report_{timestamp}.html",
    )


@router.post("/report/pdf")
def report_pdf(sess: SessionData = Depends(require_dataframe)):
    html = generate_profiling_report_html(
        sess.df, sess.column_profiles, sess.quality_report, sess.filename,
    )
    pdf_bytes = html_to_pdf_bytes(html)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    if pdf_bytes:
        return _stream(
            pdf_bytes, "application/pdf",
            f"profiling_report_{timestamp}.pdf",
        )
    # Fall back to HTML when xhtml2pdf isn't installed (Streamlit parity)
    return _stream(
        html.encode("utf-8"),
        "text/html",
        f"profiling_report_{timestamp}.html",
    )
