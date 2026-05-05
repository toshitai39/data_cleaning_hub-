"""Patched copy of features/rule_generator/report.py:generate_dq_rule_report_html.

The original has a name-shadowing bug: it does `import html` at module level
but later assigns `html = f"..."` inside the function, which makes Python treat
`html` as a local variable for the whole function. The first reference
(`html.escape(...)`) raises UnboundLocalError before reaching the assignment.

The Streamlit deployment hits the same bug — PDF export is broken there. We
keep the behaviour and styling 1:1 but rename the local to fix the crash.
"""
from __future__ import annotations

import base64
import html as _html_lib
import io
import logging
from datetime import datetime
from pathlib import Path

import pandas as pd

logger = logging.getLogger(__name__)


def _get_base64_image(image_path: str) -> str:
    try:
        if not Path(image_path).exists():
            return ""
        with open(image_path, "rb") as f:
            return base64.b64encode(f.read()).decode("utf-8")
    except Exception:
        return ""


def generate_dq_rule_report_html(validation_df: pd.DataFrame, filename: str, total_rows: int) -> str:
    """Identical output to features/rule_generator/report.py — fixed shadowing bug."""
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    project_root = Path(__file__).resolve().parents[3]
    logo_path = project_root / "assets" / "Images" / "uniqus_logo.png"
    logo_b64 = _get_base64_image(str(logo_path))

    total_rules = len(validation_df)
    unique_cols = validation_df["Column"].nunique() if "Column" in validation_df.columns else 0
    total_issues = 0
    if "Issues Found" in validation_df.columns:
        total_issues = int(validation_df["Issues Found"].fillna(0).sum())

    dim_counts = {}
    if "Dimension" in validation_df.columns:
        dim_counts = validation_df["Dimension"].value_counts().to_dict()

    rows_html = ""
    for _, row in validation_df.iterrows():
        issues = row.get("Issues Found", 0)
        issue_style = (
            "color: #dc2626; font-weight: bold;" if issues and issues > 0 else "color: #16a34a;"
        )
        regex_pat = row.get("Regex Pattern", "")
        if pd.isna(regex_pat):
            regex_pat = ""
        regex_html = _html_lib.escape(str(regex_pat), quote=True)

        rows_html += f"""
        <tr>
            <td>{row.get('S.No', '')}</td>
            <td>{row.get('Column', '')}</td>
            <td><span class="badge dim-{str(row.get('Dimension', 'Validity')).lower()}">{row.get('Dimension', 'Validity')}</span></td>
            <td>{row.get('Data Quality Rule', '')}</td>
            <td style="font-family: monospace; font-size: 0.75rem;">{regex_html}</td>
            <td style="{issue_style}">{issues}</td>
            <td style="font-size: 0.75rem; color: #475569;">{row.get('Issues Found Example', '')}</td>
        </tr>
        """

    output = f"""
    <!DOCTYPE html>
    <html lang="en">
    <head>
        <meta charset="utf-8"/>
        <style>
            @page {{
                size: A4 landscape;
                margin: 1cm;
            }}
            body {{
                font-family: 'Helvetica', 'Arial', sans-serif;
                color: #1e293b;
                line-height: 1.4;
                font-size: 9pt;
            }}
            .header {{
                border-bottom: 2px solid #3b82f6;
                padding-bottom: 10px;
                margin-bottom: 20px;
            }}
            h1 {{
                color: #1e3a8a;
                margin: 0;
                font-size: 18pt;
            }}
            .subtitle {{
                color: #64748b;
                font-size: 10pt;
                margin-top: 5px;
            }}
            .summary-box {{
                background-color: #f8fafc;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 15px;
                margin-bottom: 20px;
            }}
            .summary-grid {{ width: 100%; }}
            .summary-item {{ text-align: center; padding: 10px; }}
            .summary-item .val {{ font-size: 16pt; font-weight: bold; color: #1e40af; display: block; }}
            .summary-item .lbl {{ font-size: 8pt; color: #64748b; text-transform: uppercase; }}
            table {{ width: 100%; border-collapse: collapse; margin-top: 10px; }}
            th {{ background-color: #f1f5f9; color: #334155; font-weight: bold; text-align: left; padding: 8px; border: 1px solid #e2e8f0; }}
            td {{ padding: 8px; border: 1px solid #e2e8f0; vertical-align: top; }}
            tr:nth-child(even) {{ background-color: #f8fafc; }}
            .badge {{ padding: 2px 6px; border-radius: 4px; font-size: 8pt; font-weight: bold; }}
            .dim-accuracy {{ background-color: #dbeafe; color: #1e40af; }}
            .dim-completeness {{ background-color: #dcfce7; color: #166534; }}
            .dim-consistency {{ background-color: #fef3c7; color: #92400e; }}
            .dim-validity {{ background-color: #fce7f3; color: #9d174d; }}
            .dim-uniqueness {{ background-color: #f3e8ff; color: #6b21a8; }}
            .footer {{ margin-top: 30px; text-align: center; font-size: 8pt; color: #94a3b8; border-top: 1px solid #e2e8f0; padding-top: 10px; }}
        </style>
    </head>
    <body>
        <table style="width: 100%; border: none; border-bottom: 2px solid #3b82f6; margin-bottom: 20px;">
            <tr>
                <td style="border: none; text-align: left; vertical-align: middle;">
                    <h1>Data Quality Rule &amp; Issues Report</h1>
                    <div class="subtitle">Dataset: {filename} | Generated: {now}</div>
                </td>
                <td style="border: none; text-align: right; vertical-align: middle;">
                    {f'<img src="data:image/png;base64,{logo_b64}" width="150"/>' if logo_b64 else '<strong>UNIQUS</strong>'}
                </td>
            </tr>
        </table>

        <div class="summary-box">
            <table class="summary-grid">
                <tr>
                    <td class="summary-item" style="border:none;">
                        <span class="val">{total_rows:,}</span>
                        <span class="lbl">Total Rows</span>
                    </td>
                    <td class="summary-item" style="border:none;">
                        <span class="val">{total_rules}</span>
                        <span class="lbl">Total Rules</span>
                    </td>
                    <td class="summary-item" style="border:none;">
                        <span class="val">{unique_cols}</span>
                        <span class="lbl">Columns Analyzed</span>
                    </td>
                    <td class="summary-item" style="border:none;">
                        <span class="val" style="color: { '#dc2626' if total_issues > 0 else '#16a34a' };">{total_issues}</span>
                        <span class="lbl">Total Issues Found</span>
                    </td>
                </tr>
            </table>
        </div>

        <h2>Rule Breakdown by Dimension</h2>
        <table>
            <tr>{"".join(f'<th>{k}</th>' for k in dim_counts.keys())}</tr>
            <tr>{"".join(f'<td>{v}</td>' for v in dim_counts.values())}</tr>
        </table>

        <h2>Detailed Findings</h2>
        <table>
            <thead>
                <tr>
                    <th style="width: 4%;">S.No</th>
                    <th style="width: 12%;">Column</th>
                    <th style="width: 8%;">Dimension</th>
                    <th style="width: 28%;">Data Quality Rule</th>
                    <th style="width: 18%;">Regex Pattern</th>
                    <th style="width: 8%;">Issues</th>
                    <th style="width: 22%;">Example of Issue</th>
                </tr>
            </thead>
            <tbody>
                {rows_html}
            </tbody>
        </table>

        <div class="footer">
            Confidential - For Internal Use Only - Generated by Enterprise Data Profiler Pro
        </div>
    </body>
    </html>
    """
    return output


def export_dq_report_to_pdf(validation_df: pd.DataFrame, filename: str, total_rows: int):
    try:
        from xhtml2pdf import pisa
    except ImportError:
        logger.error("xhtml2pdf not installed")
        return None
    html_text = generate_dq_rule_report_html(validation_df, filename, total_rows)
    pdf_buffer = io.BytesIO()
    pisa_status = pisa.CreatePDF(io.StringIO(html_text), dest=pdf_buffer)
    if pisa_status.err:
        logger.error("PDF generation error: %s", pisa_status.err)
        return None
    return pdf_buffer.getvalue()
