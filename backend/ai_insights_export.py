"""AI Insights export — Markdown, HTML, JSON, CSV, DOCX (via markdown)."""

from __future__ import annotations

import json
import csv
import io
from typing import Any


def _priority_badge(p: str) -> str:
    return {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(p, "⚪")


def _severity_badge(s: str) -> str:
    return {"critical": "🔴", "high": "🟠", "medium": "🟡", "low": "🟢"}.get(s, "⚪")


# ---------------------------------------------------------------------------
# Markdown
# ---------------------------------------------------------------------------

def export_markdown(data: dict) -> str:
    lines = ["# AI Insights Report\n"]

    gen = data.get("generated_at", "")
    if gen:
        lines.append(f"*Generated: {gen[:19]}*\n")

    # Dataset understanding
    du = data.get("dataset_understanding", {})
    if du:
        lines.append("## Dataset Understanding\n")
        lines.append(f"**Purpose:** {du.get('purpose', 'N/A')}\n")
        lines.append(f"**Domain:** {du.get('domain', 'N/A')}\n")
        lines.append(f"**Confidence:** {du.get('confidence', 0)}%\n")
        if du.get("key_columns"):
            lines.append(f"**Key Columns:** {', '.join(du['key_columns'])}\n")
        if du.get("use_cases"):
            lines.append("**Use Cases:**\n")
            for uc in du["use_cases"]:
                lines.append(f"- {uc}\n")
        lines.append("")

    # Executive summary
    es = data.get("executive_summary", {})
    if es:
        lines.append("## Executive Summary\n")
        lines.append(f"**Situation:** {es.get('situation', 'N/A')}\n")
        if es.get("key_findings"):
            lines.append("**Key Findings:**\n")
            for f in es["key_findings"]:
                lines.append(f"- {f}\n")
        if es.get("risks"):
            lines.append("**Risks:**\n")
            for r in es["risks"]:
                if r:
                    lines.append(f"- {r}\n")
        if es.get("opportunities"):
            lines.append("**Opportunities:**\n")
            for o in es["opportunities"]:
                if o:
                    lines.append(f"- {o}\n")
        if es.get("recommendations"):
            lines.append("**Recommendations:**\n")
            for r in es["recommendations"]:
                if r:
                    lines.append(f"- {r}\n")
        lines.append("")

    # Insights
    insights = data.get("insights", [])
    if insights:
        lines.append("## Insights\n")
        for ins in insights:
            badge = _priority_badge(ins.get("priority", "medium"))
            lines.append(f"### {badge} {ins.get('title', 'Untitled')}\n")
            lines.append(f"**Category:** {ins.get('category', 'N/A')} | **Priority:** {ins.get('priority', 'N/A')} | **Impact:** {ins.get('impact_score', 5)}/10\n")
            lines.append(f"{ins.get('detail', '')}\n")
            if ins.get("evidence"):
                lines.append(f"**Evidence:** {ins['evidence']}\n")
            if ins.get("action"):
                lines.append(f"**Action:** {ins['action']}\n")
            lines.append("")

    # KPIs
    kpis = data.get("kpis", [])
    if kpis:
        lines.append("## Key Performance Indicators\n")
        for kpi in kpis:
            trend_icon = {"increasing": "📈", "decreasing": "📉", "stable": "➡️", "volatile": "📊"}.get(kpi.get("trend", ""), "")
            lines.append(f"- **{kpi.get('name', 'N/A')}:** {kpi.get('value', 'N/A')} {trend_icon} ({kpi.get('status', 'N/A')})")
        lines.append("")

    # Risks
    risks = data.get("risks", [])
    if risks:
        lines.append("## Risk Assessment\n")
        for risk in risks:
            badge = _severity_badge(risk.get("severity", "medium"))
            lines.append(f"### {badge} {risk.get('title', 'Risk')}\n")
            lines.append(f"**Severity:** {risk.get('severity', 'N/A')}\n")
            lines.append(f"{risk.get('description', '')}\n")
            if risk.get("impact"):
                lines.append(f"**Impact:** {risk['impact']}\n")
            if risk.get("mitigation"):
                lines.append(f"**Mitigation:** {risk['mitigation']}\n")
            lines.append("")

    # ML recommendations
    ml = data.get("ml_recommendations", {})
    if ml:
        lines.append("## Machine Learning Readiness\n")
        if ml.get("target_candidates"):
            lines.append(f"**Target Candidates:** {', '.join(ml['target_candidates'])}\n")
        if ml.get("recommended_tasks"):
            lines.append(f"**Recommended Tasks:** {', '.join(ml['recommended_tasks'])}\n")
        if ml.get("algorithms"):
            lines.append(f"**Suggested Algorithms:** {', '.join(ml['algorithms'])}\n")
        if ml.get("feature_engineering"):
            lines.append("**Feature Engineering:**\n")
            for fe in ml["feature_engineering"]:
                lines.append(f"- {fe}\n")
        lines.append("")

    # Forecast suggestions
    fc = data.get("forecast_suggestions", [])
    if fc:
        lines.append("## Forecasting Suggestions\n")
        for f in fc:
            lines.append(f"- **{f.get('column', 'N/A')}:** {f.get('metric', 'N/A')} via {f.get('method', 'N/A')} — {f.get('reason', '')}\n")
        lines.append("")

    # Data quality
    dq = data.get("data_quality_assessment", {})
    if dq:
        lines.append("## Data Quality Assessment\n")
        lines.append(f"**Score:** {dq.get('score', 0)}/100 ({dq.get('status', 'N/A')})\n")
        if dq.get("issues"):
            lines.append("**Issues:**\n")
            for issue in dq["issues"]:
                lines.append(f"- {issue}\n")
        if dq.get("treatment_recommendations"):
            lines.append("**Recommendations:**\n")
            for rec in dq["treatment_recommendations"]:
                lines.append(f"- {rec}\n")

    return "\n".join(lines)


# ---------------------------------------------------------------------------
# HTML
# ---------------------------------------------------------------------------

def export_html(data: dict) -> str:
    md = export_markdown(data)
    # Simple markdown to HTML
    html = md
    html = html.replace("# ", "<h1>").replace("\n\n", "</p><p>")
    lines_out = []
    for line in html.split("\n"):
        if line.startswith("<h1>"):
            lines_out.append(line.replace("<h1>", "<h1>") + "</h1>")
        elif line.startswith("## "):
            lines_out.append(f"<h2>{line[3:]}</h2>")
        elif line.startswith("### "):
            lines_out.append(f"<h3>{line[4:]}</h3>")
        elif line.startswith("- "):
            lines_out.append(f"<li>{line[2:]}</li>")
        elif line.startswith("**"):
            lines_out.append(f"<strong>{line}</strong>")
        else:
            lines_out.append(f"<p>{line}</p>")

    body = "\n".join(lines_out)
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI Insights Report</title>
<style>
body {{ font-family: -apple-system, sans-serif; max-width: 900px; margin: 0 auto; padding: 24px; background: #0d1117; color: #c9d1d9; }}
h1 {{ color: #e6edf3; border-bottom: 1px solid #21262d; padding-bottom: 12px; }}
h2 {{ color: #58a6ff; margin-top: 28px; }}
h3 {{ color: #e6edf3; }}
li {{ margin: 4px 0; }}
strong {{ color: #e6edf3; }}
p {{ line-height: 1.6; }}
</style>
</head>
<body>
{body}
</body>
</html>"""


# ---------------------------------------------------------------------------
# JSON
# ---------------------------------------------------------------------------

def export_json(data: dict) -> str:
    # Remove raw_stats for cleaner output
    clean = {k: v for k, v in data.items() if k != "raw_stats"}
    return json.dumps(clean, indent=2, default=str)


# ---------------------------------------------------------------------------
# CSV
# ---------------------------------------------------------------------------

def export_csv(data: dict) -> str:
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(["Category", "Title", "Priority", "Impact", "Detail", "Evidence", "Action"])

    for ins in data.get("insights", []):
        writer.writerow([
            ins.get("category", ""),
            ins.get("title", ""),
            ins.get("priority", ""),
            ins.get("impact_score", ""),
            ins.get("detail", ""),
            ins.get("evidence", ""),
            ins.get("action", ""),
        ])

    for risk in data.get("risks", []):
        writer.writerow([
            "risk",
            risk.get("title", ""),
            risk.get("severity", ""),
            "",
            risk.get("description", ""),
            risk.get("impact", ""),
            risk.get("mitigation", ""),
        ])

    for kpi in data.get("kpis", []):
        writer.writerow([
            "kpi",
            kpi.get("name", ""),
            kpi.get("status", ""),
            "",
            f"Value: {kpi.get('value', 'N/A')} | Trend: {kpi.get('trend', 'N/A')}",
            "",
            "",
        ])

    return buf.getvalue()
