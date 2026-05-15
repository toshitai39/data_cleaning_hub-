"""Client-grade Data Quality Report.

Produces a single self-contained HTML page that combines every signal
the steward has generated through the pipeline:

  • Cover with project context (system / stream / generated-by / date)
  • Executive narrative summary
  • Dataset shape — original vs current rows, columns
  • DAMA six-dimension scorecard with scores, ratings, key findings
  • Rules generated, applied, rejected — per dimension
  • Cleansing history — every action taken with timestamp
  • Rejected rows summary with reasons
  • Per-CDE scorecard (semantic type, completeness, validity, score)
  • Prioritised remediation actions
  • Footer

Designed to render correctly when fields are missing — graceful
degradation everywhere. The same HTML is converted to PDF via xhtml2pdf
when available; falls back to HTML download otherwise.
"""
from __future__ import annotations

import html as _html
import io
from datetime import datetime
from typing import Any, Dict, List, Optional

import pandas as pd

from .dama_assessment import compute_executive_summary
from ..session_store import SessionData


# ── Branding tokens (mirror the frontend dark-purple identity) ─────────────
_BRAND_BG = "#1B0E3D"
_BRAND_ACCENT = "#6A28A8"
_BRAND_ROSE = "#B11D77"
_INK = "#1A1A1A"
_MUTED = "#6B7280"
_BORDER = "#E5E7EB"
_GOOD = "#15803d"
_WARN = "#b45309"
_BAD = "#b91c1c"
_SOFT_GOOD = "#f0fdf4"
_SOFT_WARN = "#fffbeb"
_SOFT_BAD = "#fef2f2"


def _esc(s: Any) -> str:
    return _html.escape(str(s) if s is not None else "")


def _fmt_int(n: Any) -> str:
    try:
        return f"{int(n):,}"
    except (ValueError, TypeError):
        return str(n)


def _fmt_pct(v: Any, decimals: int = 1) -> str:
    try:
        return f"{float(v) * 100:.{decimals}f}%" if float(v) <= 1.0 else f"{float(v):.{decimals}f}%"
    except (ValueError, TypeError):
        return "—"


def _rating_color(rating: str) -> tuple[str, str]:
    """(background, foreground) for a DAMA rating chip."""
    table = {
        "Strong":          (_SOFT_GOOD, _GOOD),
        "Moderate":        (_SOFT_WARN, _WARN),
        "Needs Attention": (_SOFT_WARN, _WARN),
        "Critical":        (_SOFT_BAD,  _BAD),
    }
    return table.get(rating, ("#f1f5f9", "#475569"))


# ── Section builders ──────────────────────────────────────────────────────

def _cover_section(filename: str, project_context: Optional[Dict[str, Any]],
                   user: Optional[Dict[str, Any]]) -> str:
    now = datetime.now().strftime("%d %B %Y · %H:%M")
    system = (project_context or {}).get("system_label", "—")
    stream = (project_context or {}).get("stream_label", "—")
    user_name = (user or {}).get("name") or (user or {}).get("username") or "—"
    return f"""
    <section class="cover">
      <div class="cover-eyebrow">DATA QUALITY REPORT</div>
      <h1>{_esc(filename)}</h1>
      <div class="cover-meta">
        <div><span class="lbl">Source system</span><span class="val">{_esc(system)}</span></div>
        <div><span class="lbl">Master-data stream</span><span class="val">{_esc(stream)}</span></div>
        <div><span class="lbl">Prepared by</span><span class="val">{_esc(user_name)}</span></div>
        <div><span class="lbl">Generated</span><span class="val">{_esc(now)}</span></div>
      </div>
    </section>
    """


def _executive_summary_section(exec_summary: Dict[str, Any],
                               original_rows: int, current_rows: int,
                               total_columns: int,
                               rules_applied: int, rules_total: int,
                               rejected_rows: int) -> str:
    overall = exec_summary.get("overall_score", 0.0)
    overall_pct = int(round(overall * 100)) if overall <= 1.0 else int(round(overall))
    rating = exec_summary.get("overall_rating", "—")
    rb, rf = _rating_color(rating)
    rows_removed = max(0, original_rows - current_rows)
    cleanse_pct = (rules_applied / rules_total * 100) if rules_total else 0

    return f"""
    <section class="section">
      <h2>Executive Summary</h2>
      <p class="lede">
        This report summarises the data quality assessment performed on
        <strong>{_esc(_fmt_int(original_rows))}</strong> records across
        <strong>{_esc(total_columns)}</strong> critical data elements.
        After applying <strong>{_esc(rules_applied)}</strong> of
        <strong>{_esc(rules_total)}</strong> generated rules
        ({cleanse_pct:.0f}% complete), the dataset has
        <strong>{_esc(_fmt_int(current_rows))}</strong> validated records
        with <strong>{_esc(_fmt_int(rejected_rows))}</strong> rejected for review.
      </p>
      <div class="kpi-grid">
        <div class="kpi kpi-accent">
          <div class="kpi-val">{overall_pct}</div>
          <div class="kpi-lbl">Overall Score / 100</div>
          <div class="kpi-sub"><span class="chip" style="background:{rb};color:{rf};">{_esc(rating)}</span></div>
        </div>
        <div class="kpi">
          <div class="kpi-val">{_fmt_int(original_rows)}</div>
          <div class="kpi-lbl">Original Rows</div>
        </div>
        <div class="kpi">
          <div class="kpi-val">{_fmt_int(current_rows)}</div>
          <div class="kpi-lbl">Current Rows</div>
          {(f'<div class="kpi-sub" style="color:{_BAD};">−{rows_removed:,} removed</div>') if rows_removed else ''}
        </div>
        <div class="kpi">
          <div class="kpi-val">{_fmt_int(rules_total)}</div>
          <div class="kpi-lbl">Rules Generated</div>
          <div class="kpi-sub">{_fmt_int(rules_applied)} applied</div>
        </div>
      </div>
    </section>
    """


def _dimension_scorecard_section(exec_summary: Dict[str, Any]) -> str:
    rows = []
    for dim in exec_summary.get("dimensions", []):
        if not dim.get("enabled", True):
            continue
        rb, rf = _rating_color(dim.get("rating", "—"))
        score = dim.get("score", 0)
        score_pct = int(round((float(score) * 100) if float(score) <= 1.0 else float(score)))
        rows.append(f"""
          <tr>
            <td><strong>{_esc(dim.get('dimension', ''))}</strong></td>
            <td class="num">{score_pct}</td>
            <td><span class="chip" style="background:{rb};color:{rf};">{_esc(dim.get('rating', '—'))}</span></td>
            <td>{_esc(dim.get('key_finding', '—'))}</td>
            <td class="num">{_fmt_int(dim.get('records_impacted', 0))}</td>
          </tr>
        """)
    if not rows:
        return ""
    return f"""
    <section class="section">
      <h2>DAMA Six-Dimension Scorecard</h2>
      <table class="report-table">
        <thead>
          <tr>
            <th>Dimension</th>
            <th class="num">Score</th>
            <th>Rating</th>
            <th>Key finding</th>
            <th class="num">Records impacted</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def _rules_section(sess: SessionData) -> str:
    rg_df = getattr(sess, "ai_validation_rules", None)
    if not isinstance(rg_df, pd.DataFrame) or rg_df.empty:
        return f"""
        <section class="section">
          <h2>Rules Generated</h2>
          <p class="muted">No data-quality rules were generated for this dataset.</p>
        </section>
        """
    by_dim = rg_df.groupby("Dimension").size().to_dict() if "Dimension" in rg_df.columns else {}
    applied_by_dim = dict(sess.applied_rules_by_dim or {})
    rows = []
    for dim in sorted(by_dim.keys()):
        gen = by_dim[dim]
        applied = applied_by_dim.get(dim, 0)
        cov = (applied / gen * 100) if gen else 0
        rows.append(f"""
          <tr>
            <td><strong>{_esc(dim)}</strong></td>
            <td class="num">{_fmt_int(gen)}</td>
            <td class="num">{_fmt_int(applied)}</td>
            <td class="num">{cov:.0f}%</td>
          </tr>
        """)
    total_gen = int(len(rg_df))
    total_app = sum(applied_by_dim.values())
    rows.append(f"""
      <tr class="total-row">
        <td><strong>Total</strong></td>
        <td class="num"><strong>{_fmt_int(total_gen)}</strong></td>
        <td class="num"><strong>{_fmt_int(total_app)}</strong></td>
        <td class="num"><strong>{(total_app / total_gen * 100) if total_gen else 0:.0f}%</strong></td>
      </tr>
    """)
    return f"""
    <section class="section">
      <h2>Rules Generated &amp; Applied — by DAMA Dimension</h2>
      <table class="report-table">
        <thead>
          <tr><th>Dimension</th><th class="num">Generated</th><th class="num">Applied</th><th class="num">Coverage</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def _cleansing_history_section(sess: SessionData) -> str:
    history = list(sess.validation_history or [])
    if not history:
        return ""
    rows = []
    for h in history:
        rows.append(f"""
          <tr>
            <td>{_esc(h.get('timestamp', '—'))}</td>
            <td>{_esc(h.get('column', '—'))}</td>
            <td>{_esc(h.get('description', '—'))}</td>
            <td class="num" style="color:{_BAD if h.get('rejected_count', 0) > 0 else _INK};">
              {_fmt_int(h.get('rejected_count', 0))}
            </td>
          </tr>
        """)
    return f"""
    <section class="section">
      <h2>Cleansing Actions Log</h2>
      <p class="muted">Every action taken on the working dataset, in order.</p>
      <table class="report-table">
        <thead>
          <tr><th>Timestamp</th><th>Critical Data Element</th><th>Action</th><th class="num">Rows rejected</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def _rejected_rows_section(sess: SessionData) -> str:
    rej = sess.reject_df
    if not isinstance(rej, pd.DataFrame) or rej.empty:
        return ""
    total = int(len(rej))
    # Group by Rejection_Reason for a tidy summary
    reasons_html = ""
    if "Rejection_Reason" in rej.columns:
        grouped = rej["Rejection_Reason"].value_counts().head(15)
        for reason, count in grouped.items():
            reasons_html += f"""
              <tr>
                <td>{_esc(reason)}</td>
                <td class="num">{_fmt_int(count)}</td>
              </tr>
            """
    return f"""
    <section class="section">
      <h2>Rejected Rows — Why They Were Rejected</h2>
      <p class="lede">
        <strong>{_fmt_int(total)}</strong> rows were removed from the working dataset during cleansing.
        They are preserved in the rejection log for audit and re-review.
      </p>
      {f'''
      <table class="report-table">
        <thead>
          <tr><th>Reason</th><th class="num">Row count</th></tr>
        </thead>
        <tbody>{reasons_html}</tbody>
      </table>
      ''' if reasons_html else '<p class="muted">No rejection reasons were recorded.</p>'}
    </section>
    """


def _per_cde_section(df: pd.DataFrame, glossary: Optional[Dict[str, Any]]) -> str:
    if df is None or df.empty:
        return ""
    total_rows = int(len(df))
    rows = []
    for col in df.columns:
        try:
            non_null = int(df[col].notna().sum())
            non_blank = int((df[col].astype(str).str.strip() != "").sum() if df[col].dtype == object else non_null)
            fill_rate = (non_null / total_rows) if total_rows else 0
            uniq = int(df[col].nunique(dropna=True))
            uniq_pct = (uniq / total_rows) if total_rows else 0
        except Exception:
            non_null = non_blank = uniq = 0
            fill_rate = uniq_pct = 0
        sem = ""
        if glossary and isinstance(glossary, dict):
            entry = glossary.get(str(col)) or {}
            sem = entry.get("semantic_type", "") or ""
        fill_color = _GOOD if fill_rate >= 0.95 else (_WARN if fill_rate >= 0.7 else _BAD)
        rows.append(f"""
          <tr>
            <td><strong>{_esc(col)}</strong></td>
            <td><span class="chip" style="background:#f5f3ff;color:#581c87;">{_esc(sem or '—')}</span></td>
            <td class="num">{_fmt_int(non_null)}</td>
            <td class="num" style="color:{fill_color};">{_fmt_pct(fill_rate, 1)}</td>
            <td class="num">{_fmt_int(uniq)}</td>
            <td class="num">{_fmt_pct(uniq_pct, 1)}</td>
          </tr>
        """)
    return f"""
    <section class="section">
      <h2>Critical Data Element Scorecard</h2>
      <p class="muted">Fill rate and cardinality for every CDE in the analysed scope.</p>
      <table class="report-table">
        <thead>
          <tr>
            <th>Critical Data Element</th>
            <th>Semantic type</th>
            <th class="num">Filled</th>
            <th class="num">Fill %</th>
            <th class="num">Unique</th>
            <th class="num">Unique %</th>
          </tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


def _remediation_section(exec_summary: Dict[str, Any]) -> str:
    actions = exec_summary.get("remediation_actions", []) or []
    if not actions:
        return ""
    rows = []
    for a in actions[:10]:
        rows.append(f"""
          <tr>
            <td><span class="chip pri-{_esc(a.get('priority', '')).lower()}">{_esc(a.get('priority', ''))}</span></td>
            <td>{_esc(a.get('dimension', ''))}</td>
            <td>{_esc(a.get('action', ''))}</td>
            <td>{_esc(a.get('impact', ''))}</td>
            <td class="num">{_fmt_int(a.get('estimated_records', 0))}</td>
          </tr>
        """)
    return f"""
    <section class="section">
      <h2>Recommended Next Steps</h2>
      <table class="report-table">
        <thead>
          <tr><th>Priority</th><th>Dimension</th><th>Action</th><th>Impact</th><th class="num">Est. records</th></tr>
        </thead>
        <tbody>{''.join(rows)}</tbody>
      </table>
    </section>
    """


# ── HTML shell ────────────────────────────────────────────────────────────

def _css() -> str:
    return f"""
    <style>
      @page {{ size: A4; margin: 18mm 16mm; }}
      * {{ box-sizing: border-box; }}
      body {{
        font-family: 'Helvetica', 'Arial', sans-serif;
        color: {_INK}; margin: 0; padding: 0;
        font-size: 11.5px; line-height: 1.5;
      }}
      .page {{ max-width: 980px; margin: 0 auto; padding: 24px 32px 32px; }}
      .cover {{
        background: linear-gradient(135deg, {_BRAND_BG} 0%, {_BRAND_ACCENT} 60%, {_BRAND_ROSE} 100%);
        color: #fff; padding: 48px 36px; margin: 0 -32px 32px;
        border-radius: 0;
      }}
      .cover-eyebrow {{
        font-size: 10px; font-weight: 800; letter-spacing: 0.20em;
        opacity: 0.78; margin-bottom: 12px;
      }}
      .cover h1 {{
        font-size: 28px; font-weight: 700; margin: 0 0 28px;
        line-height: 1.15;
      }}
      .cover-meta {{
        display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px;
      }}
      .cover-meta > div {{
        background: rgba(255,255,255,0.10);
        border: 1px solid rgba(255,255,255,0.16);
        border-radius: 8px; padding: 10px 14px;
      }}
      .cover-meta .lbl {{
        display: block; font-size: 9.5px; font-weight: 700;
        letter-spacing: 0.10em; opacity: 0.72; text-transform: uppercase;
        margin-bottom: 2px;
      }}
      .cover-meta .val {{ display: block; font-size: 13px; font-weight: 600; }}

      .section {{ margin: 0 0 32px; page-break-inside: avoid; }}
      .section h2 {{
        font-size: 16px; font-weight: 700; color: {_INK};
        margin: 0 0 6px;
        padding-bottom: 6px;
        border-bottom: 2px solid {_BRAND_ACCENT};
      }}
      .lede {{ font-size: 12px; color: {_INK}; margin: 8px 0 16px; }}
      .muted {{ color: {_MUTED}; font-size: 11px; margin: 4px 0 12px; }}

      .kpi-grid {{
        display: grid; grid-template-columns: repeat(4, 1fr); gap: 12px;
        margin-top: 12px;
      }}
      .kpi {{
        background: #FAFAFA; border: 1px solid {_BORDER};
        border-radius: 10px; padding: 14px 16px;
      }}
      .kpi-accent {{
        background: linear-gradient(135deg, {_BRAND_ACCENT} 0%, {_BRAND_ROSE} 100%);
        color: #fff; border-color: transparent;
      }}
      .kpi-val {{
        font-size: 26px; font-weight: 700; line-height: 1.1;
        font-feature-settings: 'tnum';
      }}
      .kpi-lbl {{
        font-size: 9.5px; font-weight: 700; letter-spacing: 0.12em;
        text-transform: uppercase; margin-top: 6px; opacity: 0.78;
      }}
      .kpi-sub {{ font-size: 10.5px; margin-top: 4px; opacity: 0.78; }}

      table.report-table {{
        width: 100%; border-collapse: collapse; font-size: 11px;
        margin-top: 8px;
      }}
      table.report-table thead th {{
        background: #FAFAFA; color: {_MUTED};
        font-size: 9.5px; font-weight: 700; letter-spacing: 0.10em;
        text-transform: uppercase;
        padding: 8px 10px; text-align: left;
        border-bottom: 1px solid {_BORDER};
      }}
      table.report-table tbody td {{
        padding: 8px 10px; border-bottom: 1px solid #F1F1F1;
      }}
      table.report-table tr:hover td {{ background: #FBFAFC; }}
      table.report-table .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
      table.report-table tr.total-row td {{
        border-top: 2px solid {_BORDER}; background: #FAFAFA;
      }}

      .chip {{
        display: inline-block;
        padding: 2px 9px; border-radius: 999px;
        font-size: 9.5px; font-weight: 700; letter-spacing: 0.04em;
      }}
      .pri-high   {{ background: {_SOFT_BAD};  color: {_BAD};  }}
      .pri-medium {{ background: {_SOFT_WARN}; color: {_WARN}; }}
      .pri-low    {{ background: {_SOFT_GOOD}; color: {_GOOD}; }}

      .footer {{
        margin-top: 40px; padding-top: 16px;
        border-top: 1px solid {_BORDER};
        text-align: center; color: {_MUTED}; font-size: 10px;
      }}
      .footer .brand {{ color: {_BRAND_ACCENT}; font-weight: 700; }}
    </style>
    """


def build_report_html(sess: SessionData,
                       project_context: Optional[Dict[str, Any]] = None) -> str:
    """Build the full client-grade HTML report from session state."""
    df = sess.df if isinstance(sess.df, pd.DataFrame) else pd.DataFrame()
    original_df = sess.original_df if isinstance(sess.original_df, pd.DataFrame) else df

    glossary = sess.semantic_glossary if isinstance(sess.semantic_glossary, dict) else None
    cross_field_rules: List[Dict[str, Any]] = []
    if isinstance(sess.ai_validation_rules, pd.DataFrame) and "Dimension" in sess.ai_validation_rules.columns:
        cf = sess.ai_validation_rules[
            sess.ai_validation_rules["Dimension"].astype(str) == "Cross-field Validation"
        ]
        for _, r in cf.iterrows():
            cross_field_rules.append({
                "rule_text": str(r.get("Data Quality Rule", "")),
                "columns": str(r.get("Columns", "")),
            })

    exec_summary = compute_executive_summary(
        df, glossary=glossary,
        cross_field_rules=cross_field_rules or None,
        project_context=project_context,
    )

    original_rows = int(len(original_df))
    current_rows = int(len(df))
    total_columns = int(df.shape[1]) if not df.empty else 0
    rules_total = int(len(sess.ai_validation_rules)) if isinstance(sess.ai_validation_rules, pd.DataFrame) else 0
    rules_applied = int(sum((sess.applied_rules_by_dim or {}).values()))
    rejected_rows = int(len(sess.reject_df)) if isinstance(sess.reject_df, pd.DataFrame) else 0

    parts = [
        _cover_section(sess.filename or "Dataset", project_context, sess.user),
        _executive_summary_section(
            exec_summary, original_rows, current_rows, total_columns,
            rules_applied, rules_total, rejected_rows,
        ),
        _dimension_scorecard_section(exec_summary),
        _rules_section(sess),
        _cleansing_history_section(sess),
        _rejected_rows_section(sess),
        _per_cde_section(df, glossary),
        _remediation_section(exec_summary),
    ]

    body = "\n".join(p for p in parts if p)
    now = datetime.now().strftime("%d %B %Y · %H:%M")
    footer = f"""
    <div class="footer">
      Generated by <span class="brand">Uniqus Data Profiler</span> &nbsp;·&nbsp; {_esc(now)}
    </div>
    """

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<title>Data Quality Report — {_esc(sess.filename or 'Dataset')}</title>
{_css()}
</head>
<body>
<div class="page">
{body}
{footer}
</div>
</body>
</html>"""


def html_to_pdf_bytes(html: str) -> Optional[bytes]:
    """Convert HTML to PDF using xhtml2pdf. Returns None if the package
    isn't installed — caller falls back to HTML download."""
    try:
        import xhtml2pdf.pisa as pisa
        buffer = io.BytesIO()
        result = pisa.CreatePDF(io.StringIO(html), dest=buffer)
        if result.err:
            return None
        return buffer.getvalue()
    except ImportError:
        return None
    except Exception:
        return None
