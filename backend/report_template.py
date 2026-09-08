"""HTML Report Template — builds a self-contained, professional EDA report."""

from __future__ import annotations

import json
from typing import Any


def _esc(s: str) -> str:
    return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;").replace('"', "&quot;")


def _score_color(score: float) -> str:
    if score >= 80: return "#22c55e"
    if score >= 60: return "#3b82f6"
    if score >= 40: return "#f59e0b"
    return "#ef4444"


def _score_status(score: float) -> str:
    if score >= 80: return "Excellent"
    if score >= 60: return "Good"
    if score >= 40: return "Fair"
    return "Poor"


def _badge(value: str, color: str) -> str:
    return f'<span style="display:inline-block;padding:2px 8px;border-radius:4px;font-size:.7rem;font-weight:700;background:{color}22;color:{color};text-transform:uppercase;letter-spacing:.03em">{_esc(value)}</span>'


def _stat_card(label: str, value: str, color: str = "#c9d1d9") -> str:
    return f'''<div style="flex:1;min-width:120px;background:#161b22;border:1px solid #21262d;border-radius:8px;padding:14px;text-align:center">
        <div style="font-size:.7rem;color:#8b949e;text-transform:uppercase;letter-spacing:.05em;margin-bottom:6px">{_esc(label)}</div>
        <div style="font-size:1.3rem;font-weight:800;color:{color}">{_esc(str(value))}</div>
    </div>'''


def _table(headers: list[str], rows: list[list[str]], max_rows: int = 50) -> str:
    html = '<div style="overflow-x:auto;border:1px solid #21262d;border-radius:6px;margin:8px 0"><table style="width:100%;border-collapse:collapse;font-size:.82rem"><thead><tr>'
    for h in headers:
        html += f'<th style="padding:8px 10px;text-align:left;background:#161b22;border-bottom:1px solid #30363d;color:#8b949e;font-weight:700;font-size:.72rem;text-transform:uppercase;letter-spacing:.04em">{_esc(h)}</th>'
    html += '</tr></thead><tbody>'
    for i, row in enumerate(rows[:max_rows]):
        bg = "#0d1117" if i % 2 == 0 else "#161b22"
        html += f'<tr style="background:{bg}">'
        for cell in row:
            html += f'<td style="padding:6px 10px;border-bottom:1px solid #21262d;color:#c9d1d9;font-family:JetBrains Mono,monospace;font-size:.78rem">{cell}</td>'
        html += '</tr>'
    if len(rows) > max_rows:
        html += f'<tr><td colspan="{len(headers)}" style="padding:8px;text-align:center;color:#6e7681;font-style:italic">Showing {max_rows} of {len(rows)} rows</td></tr>'
    html += '</tbody></table></div>'
    return html


def _section(title: str, content: str, id_: str = "", icon: str = "") -> str:
    heading_icon = f'{icon} ' if icon else ''
    id_attr = f' id="{id_}"' if id_ else ''
    return f'''
    <div class="report-section"{id_attr}>
        <h2 style="font-size:1.1rem;font-weight:700;color:#e6edf3;margin:0 0 16px;padding-bottom:10px;border-bottom:1px solid #21262d">
            {heading_icon}{_esc(title)}
        </h2>
        {content}
    </div>'''


# ---------------------------------------------------------------------------
# Section builders
# ---------------------------------------------------------------------------

def _build_executive_summary(report: dict) -> str:
    b = report.get("branding", {})
    ov = report.get("dataset_overview", {})
    q = report.get("quality", {}).get("health_score", {})
    biz = report.get("business_story", {})
    insights = report.get("insights", [])

    cards = (
        _stat_card("Rows", f"{ov.get('rows', 0):,}", "#3b82f6")
        + _stat_card("Columns", ov.get("columns", 0), "#3b82f6")
        + _stat_card("Memory", f"{ov.get('memory_mb', 0)} MB", "#8b949e")
        + _stat_card("Quality Score", f"{q.get('score', 'N/A')}/100", _score_color(q.get("score", 0)))
        + _stat_card("Missing", f"{ov.get('missing_pct', 0)}%", "#f59e0b" if ov.get("missing_pct", 0) > 5 else "#22c55e")
    )

    content = f'''
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:20px">{cards}</div>
    <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px;margin-bottom:16px">
        <h3 style="margin:0 0 8px;color:#e6edf3;font-size:.95rem">Situation</h3>
        <p style="color:#8b949e;font-size:.85rem;line-height:1.6;margin:0">{_esc(biz.get('situation', 'N/A'))}</p>
    </div>
    <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px;margin-bottom:16px">
        <h3 style="margin:0 0 8px;color:#e6edf3;font-size:.95rem">Key Insights</h3>
        <ul style="color:#8b949e;font-size:.85rem;line-height:1.8;margin:0;padding-left:20px">
            {"".join(f"<li>{_esc(ins)}</li>" for ins in insights[:6])}
        </ul>
    </div>'''
    return _section("Executive Summary", content, "executive-summary", "&#128202;")


def _build_dataset_overview(report: dict) -> str:
    ov = report.get("dataset_overview", {})
    details = report.get("column_details", [])

    cards = (
        _stat_card("Rows", f"{ov.get('rows', 0):,}")
        + _stat_card("Columns", ov.get("columns", 0))
        + _stat_card("Numeric", ov.get("numeric_columns", 0), "#3b82f6")
        + _stat_card("Categorical", ov.get("categorical_columns", 0), "#22c55e")
        + _stat_card("DateTime", ov.get("datetime_columns", 0), "#f59e0b")
        + _stat_card("Boolean", ov.get("boolean_columns", 0), "#8b5cf6")
    )

    headers = ["Column", "Type", "Non-Null", "Null %", "Unique", "Tags", "Semantic"]
    rows = []
    for d in details:
        tags = ", ".join(d.get("tags", []))
        rows.append([
            f'<strong>{_esc(d["name"])}</strong>',
            _badge(d["type"], "#3b82f6" if d["type"] == "numeric" else "#22c55e" if d["type"] == "categorical" else "#f59e0b"),
            str(d.get("non_null", 0)),
            f'{d.get("null_pct", 0)}%',
            str(d.get("unique_count", 0)),
            tags,
            _esc(d.get("semantic", "")),
        ])

    content = f'''
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px">{cards}</div>
    {_table(headers, rows)}
    '''
    return _section("Dataset Overview", content, "overview", "&#128203;")


def _build_quality_report(report: dict) -> str:
    q = report.get("quality", {})
    hs = q.get("health_score", {})
    breakdown = hs.get("breakdown", {})

    score_items = ""
    for label, val in breakdown.items():
        color = _score_color(val)
        score_items += f'''
        <div style="flex:1;min-width:120px">
            <div style="display:flex;justify-content:space-between;margin-bottom:4px">
                <span style="font-size:.78rem;color:#8b949e;text-transform:uppercase">{label}</span>
                <span style="font-size:.78rem;font-weight:700;color:{color}">{val}</span>
            </div>
            <div style="height:6px;border-radius:3px;background:#21262d;overflow:hidden">
                <div style="height:100%;width:{val}%;background:{color};border-radius:3px"></div>
            </div>
        </div>'''

    score_val = hs.get('score', 0)
    score_deg = score_val * 3.6
    score_color = _score_color(score_val)

    content = f'''
    <div style="display:flex;align-items:center;gap:24px;margin-bottom:20px">
        <div style="width:100px;height:100px;border-radius:50%;background:conic-gradient({score_color} 0deg, {score_color} {score_deg}deg, #21262d {score_deg}deg);display:flex;align-items:center;justify-content:center">
            <div style="font-size:1.6rem;font-weight:800;color:#e6edf3">{score_val}</div>
        </div>
        <div>
            <div style="font-size:.85rem;color:#8b949e">Overall Health Score</div>
            {_badge(hs.get('status', ''), score_color)}
        </div>
    </div>
    <div style="display:flex;flex-direction:column;gap:12px;margin-bottom:16px">{score_items}</div>
    '''
    return _section("Data Quality Report", content, "quality", "&#10003;&#65039;")


def _build_descriptive_stats(report: dict) -> str:
    stats = report.get("descriptive_stats", {})
    if not stats:
        return _section("Descriptive Statistics", '<p style="color:#6e7681">No numeric columns found.</p>', "stats", "&#128202;")

    headers = ["Column", "Count", "Mean", "Median", "Std", "Min", "Max", "Skew", "Kurt", "Q1", "Q3", "IQR"]
    rows = []
    for col, s in stats.items():
        rows.append([
            f'<strong>{_esc(col)}</strong>', str(s["count"]),
            f'{s["mean"]:.4f}', f'{s["median"]:.4f}', f'{s["std"]:.4f}',
            f'{s["min"]:.4f}', f'{s["max"]:.4f}',
            f'{s["skewness"]:.4f}', f'{s["kurtosis"]:.4f}',
            f'{s["q1"]:.4f}', f'{s["q3"]:.4f}', f'{s["iqr"]:.4f}',
        ])
    return _section("Descriptive Statistics", _table(headers, rows), "stats", "&#128202;")


def _build_correlation(report: dict) -> str:
    corr = report.get("correlation", {})
    if corr.get("error"):
        return _section("Correlation Analysis", f'<p style="color:#6e7681">{_esc(corr["error"])}</p>', "correlation", "&#128279;")

    pairs = corr.get("pairs", [])
    mc = corr.get("multicollinearity", [])

    if not pairs:
        return _section("Correlation Analysis", '<p style="color:#6e7681">Not enough numeric columns.</p>', "correlation", "&#128279;")

    headers = ["Feature A", "Feature B", "Correlation", "Strength", "Direction"]
    rows = []
    for p in pairs[:20]:
        color = "#22c55e" if p["value"] > 0 else "#ef4444"
        rows.append([
            _esc(p["feature_a"]), _esc(p["feature_b"]),
            f'<span style="color:{color};font-weight:700">{p["value"]:.4f}</span>',
            _badge(p["strength"], p.get("badge_color", "#8b949e")),
            p["direction"],
        ])

    mc_html = ""
    if mc:
        mc_items = "".join(
            f'<div style="padding:8px 12px;background:#ef444422;border:1px solid #ef444433;border-radius:6px;font-size:.82rem;color:#ef4444">'
            f'<strong>{_esc(m["feature_a"])}</strong> ↔ <strong>{_esc(m["feature_b"])}</strong>: r = {m["value"]:.4f}</div>'
            for m in mc[:5]
        )
        mc_html = f'<h3 style="font-size:.9rem;color:#ef4444;margin:16px 0 8px">Multicollinearity Warnings ({len(mc)} pairs)</h3><div style="display:flex;flex-direction:column;gap:6px">{mc_items}</div>'

    content = _table(headers, rows) + mc_html
    return _section("Correlation Analysis", content, "correlation", "&#128279;")


def _build_outliers(report: dict) -> str:
    out = report.get("outliers", {})
    cols = out.get("columns", [])
    if not cols:
        return _section("Outlier Analysis", '<p style="color:#6e7681">No numeric columns with outliers detected.</p>', "outliers", "&#9888;&#65039;")

    severity_colors = {"high": "#ef4444", "medium": "#f59e0b", "low": "#22c55e"}
    headers = ["Column", "IQR Outliers", "Z-Score Outliers", "%", "Severity", "Fence Range"]
    rows = []
    for c in cols:
        sev_color = severity_colors.get(c["severity"], "#8b949e")
        rows.append([
            f'<strong>{_esc(c["name"])}</strong>',
            str(c["iqr_outliers"]),
            str(c["zscore_outliers"]),
            f'{c["percentage"]}%',
            _badge(c["severity"], sev_color),
            f'[{c["lower_fence"]}, {c["upper_fence"]}]',
        ])

    content = f'''
    <div style="margin-bottom:12px">{_stat_card("Total Outliers", out.get("total_outliers", 0), "#ef4444")}</div>
    {_table(headers, rows)}
    '''
    return _section("Outlier Analysis", content, "outliers", "&#9888;&#65039;")


def _build_distribution(report: dict) -> str:
    dist = report.get("distribution", {})
    if dist.get("error"):
        return _section("Distribution Analysis", f'<p style="color:#6e7681">{_esc(dist["error"])}</p>', "distribution", "&#127916;")

    cols = dist.get("columns", [])
    if not cols:
        return _section("Distribution Analysis", '<p style="color:#6e7681">No columns analyzed.</p>', "distribution", "&#127916;")

    summary = dist.get("summary", {})
    cards = (
        _stat_card("Normal", summary.get("normal_columns", 0), "#22c55e")
        + _stat_card("Skewed", summary.get("skewed_columns", 0), "#f59e0b")
        + _stat_card("Symmetric", summary.get("symmetric_columns", 0), "#3b82f6")
        + _stat_card("With Outliers", summary.get("columns_with_outliers", 0), "#ef4444")
    )

    headers = ["Column", "Skewness", "Kurtosis", "Shape", "Quality"]
    rows = []
    for c in cols:
        shape = c.get("shape", {})
        qs = c.get("quality_score", {})
        skew_color = "#22c55e" if abs(shape.get("skewness", 0) or 0) < 0.5 else "#f59e0b"
        rows.append([
            f'<strong>{_esc(c["name"])}</strong>',
            f'<span style="color:{skew_color};font-weight:700">{(shape.get("skewness") or 0):.4f}</span>',
            f'{(shape.get("kurtosis") or 0):.4f}',
            _badge(shape.get("shape", ""), "#3b82f6"),
            f'{qs.get("score", 0)} — {_esc(qs.get("status", ""))}',
        ])

    content = f'<div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:16px">{cards}</div>' + _table(headers, rows)
    return _section("Distribution Analysis", content, "distribution", "&#127916;")


def _build_column_intelligence(report: dict) -> str:
    intel = report.get("column_intelligence", [])
    if not intel:
        return ""

    headers = ["Column", "Type", "Tags", "Unique", "Semantic"]
    rows = []
    for c in intel:
        tags_html = " ".join(_badge(t, "#8b5cf6") for t in c.get("tags", []))
        rows.append([
            f'<strong>{_esc(c["name"])}</strong>',
            _badge(c.get("type", ""), "#3b82f6"),
            tags_html,
            f'{c.get("unique_count", 0)} ({c.get("unique_pct", 0)}%)',
            _esc(c.get("semantic", "")),
        ])
    return _section("Column Intelligence", _table(headers, rows), "intelligence", "&#129504;")


def _build_ai_insights(report: dict) -> str:
    insights = report.get("insights", [])
    if not insights:
        return ""

    items = ""
    for i, ins in enumerate(insights, 1):
        items += f'''
        <div style="padding:10px 14px;background:#161b22;border:1px solid #21262d;border-left:3px solid #3b82f6;border-radius:6px;font-size:.85rem;color:#8b949e;line-height:1.5">
            <span style="font-weight:700;color:#e6edf3">#{i}</span> {_esc(ins)}
        </div>'''
    return _section("AI-Powered Insights", items, "insights", "&#128161;")


def _build_business_story(report: dict) -> str:
    biz = report.get("business_story", {})
    risks_html = ""
    if biz.get("risks"):
        risks_items = "".join(f"<li>{_esc(r)}</li>" for r in biz["risks"])
        risks_html = f'<h4 style="color:#ef4444;margin:12px 0 6px;font-size:.85rem">Risks</h4><ul style="color:#8b949e;padding-left:20px;margin:0">{risks_items}</ul>'

    opps_html = ""
    if biz.get("opportunities"):
        opps_items = "".join(f"<li>{_esc(o)}</li>" for o in biz["opportunities"])
        opps_html = f'<h4 style="color:#22c55e;margin:12px 0 6px;font-size:.85rem">Opportunities</h4><ul style="color:#8b949e;padding-left:20px;margin:0">{opps_items}</ul>'

    steps_html = ""
    if biz.get("next_steps"):
        steps_items = "".join(f"<li>{_esc(s)}</li>" for s in biz["next_steps"])
        steps_html = f'<h4 style="color:#3b82f6;margin:12px 0 6px;font-size:.85rem">Next Steps</h4><ol style="color:#8b949e;padding-left:20px;margin:0">{steps_items}</ol>'

    content = f'''
    <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px;margin-bottom:12px">
        <h3 style="margin:0 0 8px;color:#e6edf3;font-size:.95rem">Current Situation</h3>
        <p style="color:#8b949e;font-size:.85rem;line-height:1.6;margin:0">{_esc(biz.get("situation", ""))}</p>
    </div>
    <div style="background:#161b22;border:1px solid #21262d;border-radius:8px;padding:16px;margin-bottom:12px">
        <h3 style="margin:0 0 8px;color:#e6edf3;font-size:.95rem">Key Observations</h3>
        <ul style="color:#8b949e;padding-left:20px;margin:0">
            {"".join(f"<li>{_esc(o)}</li>" for o in biz.get("observations", []))}
        </ul>
    </div>
    {risks_html}{opps_html}{steps_html}
    '''
    return _section("Business Storytelling", content, "business", "&#128214;")


def _build_ml_readiness(report: dict) -> str:
    ml = report.get("ml_readiness", {})
    score = ml.get("score", 0)
    color = _score_color(score)

    recs_html = ""
    recs = ml.get("recommendations", [])
    if recs:
        recs_items = "".join(
            f'<li style="margin-bottom:4px">{_badge(r["priority"], "#f59e0b" if r["priority"] == "high" else "#3b82f6")} {_esc(r["text"])}</li>'
            for r in recs
        )
        recs_html = f'<h4 style="margin:12px 0 6px;color:#e6edf3;font-size:.85rem">Recommendations</h4><ul style="color:#8b949e;padding-left:20px;margin:0">{recs_items}</ul>'

    score_deg = score * 3.6

    content = f'''
    <div style="display:flex;align-items:center;gap:20px;margin-bottom:16px">
        <div style="width:80px;height:80px;border-radius:50%;background:conic-gradient({color} 0deg, {color} {score_deg}deg, #21262d {score_deg}deg);display:flex;align-items:center;justify-content:center">
            <div style="font-size:1.3rem;font-weight:800;color:#e6edf3">{score}</div>
        </div>
        <div>
            <div style="font-size:.85rem;color:#8b949e">ML Readiness Score</div>
            {_badge(ml.get('status', ''), color)}
        </div>
    </div>
    <div style="display:flex;flex-wrap:wrap;gap:10px;margin-bottom:12px">
        {_stat_card("Numeric Features", ml.get('numeric_features', 0), '#3b82f6')}
        {_stat_card("Categorical Features", ml.get('categorical_features', 0), '#22c55e')}
        {_stat_card("Target Candidates", len(ml.get('target_candidates', [])), '#f59e0b')}
    </div>
    {_badge("Encoding Needed", '#f59e0b') if ml.get('encoding_needed') else ''}
    {_badge("Scaling Needed", '#3b82f6') if ml.get('scaling_needed') else ''}
    {recs_html}
    '''
    return _section("Machine Learning Readiness", content, "ml", "&#129302;")


# ---------------------------------------------------------------------------
# Main builder
# ---------------------------------------------------------------------------

def build_html_report(report: dict) -> str:
    """Build a complete self-contained HTML report."""
    b = report.get("branding", {})
    title = b.get("title", "EDA Report")
    author = b.get("author", "Data Drop")
    footer = b.get("footer", "Generated by Data Drop")
    generated = report.get("generated_at", "")

    sections_html = ""
    sections_order = [
        ("executive-summary", _build_executive_summary),
        ("overview", _build_dataset_overview),
        ("quality", _build_quality_report),
        ("stats", _build_descriptive_stats),
        ("correlation", _build_correlation),
        ("outliers", _build_outliers),
        ("distribution", _build_distribution),
        ("intelligence", _build_column_intelligence),
        ("insights", _build_ai_insights),
        ("business", _build_business_story),
        ("ml", _build_ml_readiness),
    ]

    for sec_id, builder in sections_order:
        try:
            html = builder(report)
            if html:
                sections_html += html
        except Exception:
            continue

    # Table of contents
    toc_items = ""
    toc_map = [
        ("executive-summary", "Executive Summary"),
        ("overview", "Dataset Overview"),
        ("quality", "Data Quality"),
        ("stats", "Descriptive Statistics"),
        ("correlation", "Correlation Analysis"),
        ("outliers", "Outlier Analysis"),
        ("distribution", "Distribution Analysis"),
        ("intelligence", "Column Intelligence"),
        ("insights", "AI Insights"),
        ("business", "Business Story"),
        ("ml", "ML Readiness"),
    ]
    for sec_id, sec_title in toc_map:
        toc_items += f'<a href="#{sec_id}" style="display:block;padding:6px 12px;color:#8b949e;text-decoration:none;font-size:.82rem;border-radius:4px;transition:.2s" onmouseover="this.style.background=\'#161b22\';this.style.color=\'#e6edf3\'" onmouseout="this.style.background=\'\';this.style.color=\'#8b949e\'">{sec_title}</a>'

    return f'''<!DOCTYPE html>
<html lang="en" data-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{_esc(title)}</title>
    <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
    <style>
        *, *::before, *::after {{ box-sizing: border-box; margin: 0; padding: 0; }}
        body {{ font-family: 'Inter', system-ui, sans-serif; background: #0d1117; color: #c9d1d9; line-height: 1.6; }}
        .report-container {{ max-width: 1100px; margin: 0 auto; padding: 32px 24px; }}
        .report-header {{ text-align: center; padding: 40px 0 30px; border-bottom: 1px solid #21262d; margin-bottom: 32px; }}
        .report-header h1 {{ font-size: 1.8rem; font-weight: 800; color: #e6edf3; margin-bottom: 8px; }}
        .report-header .meta {{ color: #6e7681; font-size: .82rem; }}
        .report-section {{ background: #0d1117; border: 1px solid #21262d; border-radius: 12px; padding: 24px; margin-bottom: 20px; }}
        .toc {{ position: fixed; top: 80px; left: 20px; width: 200px; display: none; }}
        @media (min-width: 1400px) {{ .toc {{ display: block; }} .report-container {{ margin-left: 240px; }} }}
        .report-footer {{ text-align: center; padding: 32px 0; border-top: 1px solid #21262d; margin-top: 32px; color: #6e7681; font-size: .78rem; }}
        @media print {{
            body {{ background: #fff; color: #1f2328; }}
            .report-section {{ border-color: #d0d7de; background: #fff; break-inside: avoid; }}
            .report-header {{ border-bottom-color: #d0d7de; }}
            .toc {{ display: none !important; }}
        }}
    </style>
</head>
<body>
    <nav class="toc">
        <div style="font-size:.7rem;font-weight:700;color:#6e7681;text-transform:uppercase;letter-spacing:.08em;margin-bottom:8px;padding:6px 12px">Contents</div>
        {toc_items}
    </nav>
    <div class="report-container">
        <header class="report-header">
            <h1>{_esc(title)}</h1>
            <div class="meta">
                Author: {_esc(author)} &middot; Generated: {generated[:10] if generated else "N/A"} &middot; {footer}
            </div>
        </header>
        {sections_html}
        <footer class="report-footer">
            {footer} &middot; {generated[:10] if generated else ""}
        </footer>
    </div>
</body>
</html>'''
