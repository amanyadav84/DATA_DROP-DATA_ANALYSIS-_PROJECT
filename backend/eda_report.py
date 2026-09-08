"""EDA Report Generator — orchestrates all analysis modules into a single report."""

from __future__ import annotations

import io
import json
import math
from datetime import datetime, timezone
from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from correlation import compute_correlation
from distribution import compute_distribution
from quality_report import analyze_dataset_quality
from processor import profile_dataframe, detect_column_type
from ai_service import ai_analyze


# ---------------------------------------------------------------------------
# Report profiles
# ---------------------------------------------------------------------------

REPORT_PROFILES = {
    "full": {"label": "Full Report", "sections": "all"},
    "quick": {"label": "Quick Report", "sections": "overview,quality,stats,charts,insights"},
    "technical": {"label": "Technical Report", "sections": "overview,quality,stats,distribution,correlation,outliers,ml,charts"},
    "business": {"label": "Business Report", "sections": "overview,quality,charts,insights,business,ml"},
    "executive": {"label": "Executive Report", "sections": "overview,charts,business,insights"},
}


# ---------------------------------------------------------------------------
# Column intelligence
# ---------------------------------------------------------------------------

def _detect_column_intelligence(df: pd.DataFrame) -> list[dict[str, Any]]:
    results = []
    for col in df.columns:
        series = df[col]
        non_null = series.dropna()
        if non_null.empty:
            results.append({"name": col, "type": "empty", "tags": [], "semantic": "Empty column"})
            continue

        tags = []
        semantic_parts = []
        n = len(non_null)
        n_unique = non_null.nunique()

        col_type = detect_column_type(series)

        # Identifiers
        if n_unique == n and col_type == "categorical":
            tags.append("identifier")
            semantic_parts.append("Unique identifier")
        elif n_unique == n and col_type == "numeric":
            tags.append("possible_id")
            semantic_parts.append("May be a numeric ID")

        # Boolean
        unique_str = set(non_null.astype(str).str.lower().unique())
        bool_vals = {"true", "false", "1", "0", "yes", "no", "t", "f", "y", "n"}
        if unique_str.issubset(bool_vals):
            tags.append("boolean")
            semantic_parts.append("Boolean/categorical binary")

        # Emails
        if col_type == "categorical" and n > 0:
            sample = non_null.head(100).astype(str)
            email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
            email_match = sample.str.match(email_pattern, na=False).mean()
            if email_match > 0.5:
                tags.append("emails")
                semantic_parts.append("Email addresses")

        # URLs
        if col_type == "categorical" and n > 0:
            sample = non_null.head(100).astype(str)
            url_match = sample.str.match(r"^https?://.+", na=False, flags=0).mean()
            if url_match > 0.5:
                tags.append("urls")
                semantic_parts.append("URLs")

        # Phone numbers
        if col_type == "categorical" and n > 0:
            sample = non_null.head(100).astype(str)
            phone_match = sample.str.match(r"^[\d\s\-\+()]{7,}$", na=False).mean()
            if phone_match > 0.5:
                tags.append("phone_numbers")
                semantic_parts.append("Phone numbers")

        # Currency
        if col_type == "categorical" and n > 0:
            sample = non_null.head(100).astype(str)
            currency_match = sample.str.match(r"^[\$€£¥₹][\d,]+\.?\d*$", na=False).mean()
            if currency_match > 0.5:
                tags.append("currency")
                semantic_parts.append("Currency values")

        # Date
        if col_type == "datetime":
            tags.append("datetime")
            semantic_parts.append("Date/time column")

        # Numeric
        if col_type == "numeric":
            tags.append("numeric")
            semantic_parts.append(f"Numeric (range: {non_null.min():.2f} to {non_null.max():.2f})")

        # Categorical
        if col_type == "categorical" and n_unique < 50:
            tags.append("categorical")
            semantic_parts.append(f"Categorical ({n_unique} categories)")

        # High cardinality
        if col_type == "categorical" and n_unique > n * 0.5:
            tags.append("high_cardinality")
            semantic_parts.append(f"High cardinality ({n_unique} unique values)")

        # Sensitive (heuristic)
        name_lower = col.lower()
        sensitive_keywords = ["password", "ssn", "social", "credit", "card", "secret", "token", "key"]
        if any(kw in name_lower for kw in sensitive_keywords):
            tags.append("sensitive")
            semantic_parts.append("Potentially sensitive data")

        # Location
        location_keywords = ["city", "state", "country", "address", "zip", "lat", "lon", "location"]
        if any(kw in name_lower for kw in location_keywords):
            tags.append("location")
            semantic_parts.append("Geographic data")

        if not tags:
            tags.append(col_type)
            semantic_parts.append(f"{col_type.capitalize()} column")

        results.append({
            "name": col,
            "type": col_type,
            "tags": tags,
            "semantic": "; ".join(semantic_parts),
            "unique_count": int(n_unique),
            "unique_pct": round(n_unique / n * 100, 2) if n else 0,
        })
    return results


# ---------------------------------------------------------------------------
# Outlier analysis
# ---------------------------------------------------------------------------

def _outlier_analysis(df: pd.DataFrame) -> dict[str, Any]:
    numeric_df = df.select_dtypes(include=[np.number])
    columns = []
    total_outliers = 0

    for col in numeric_df.columns:
        series = numeric_df[col].dropna()
        if len(series) < 4:
            continue

        vals = series.values.astype(float)

        # IQR method
        q1, q3 = float(np.percentile(vals, 25)), float(np.percentile(vals, 75))
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
        iqr_outliers = int(np.sum((vals < lower) | (vals > upper)))

        # Z-score method
        mean, std = float(np.mean(vals)), float(np.std(vals, ddof=1))
        z_scores = np.abs((vals - mean) / std) if std > 0 else np.zeros_like(vals)
        z_outliers = int(np.sum(z_scores > 3))

        pct = round(iqr_outliers / len(vals) * 100, 2)
        total_outliers += iqr_outliers

        severity = "low"
        if pct > 10:
            severity = "high"
        elif pct > 5:
            severity = "medium"

        columns.append({
            "name": col,
            "iqr_outliers": iqr_outliers,
            "zscore_outliers": z_outliers,
            "percentage": pct,
            "lower_fence": round(lower, 4),
            "upper_fence": round(upper, 4),
            "severity": severity,
        })

    return {
        "total_outliers": total_outliers,
        "columns": columns,
    }


# ---------------------------------------------------------------------------
# ML readiness
# ---------------------------------------------------------------------------

def _ml_readiness(df: pd.DataFrame, profile: dict) -> dict[str, Any]:
    n_rows, n_cols = df.shape
    numeric_cols = [c["name"] for c in profile["columns"] if c["type"] == "numeric"]
    categorical_cols = [c["name"] for c in profile["columns"] if c["type"] == "categorical"]
    datetime_cols = [c["name"] for c in profile["columns"] if c["type"] == "datetime"]

    missing_pct = profile["total_nulls"] / (n_rows * n_cols) * 100 if n_rows * n_cols else 0
    duplicate_pct = profile["duplicate_rows"] / n_rows * 100 if n_rows else 0

    # Target candidates: numeric columns with moderate cardinality
    target_candidates = []
    for c in profile["columns"]:
        if c["type"] == "numeric":
            unique_ratio = c["unique_count"] / n_rows if n_rows else 0
            if 0.01 < unique_ratio < 0.8:
                target_candidates.append(c["name"])

    # Feature quality
    constant_cols = [c["name"] for c in profile["columns"] if c["unique_count"] <= 1]
    high_card_cols = [c["name"] for c in profile["columns"]
                      if c["type"] == "categorical" and c["unique_count"] > n_rows * 0.5]

    # Encoding requirements
    encoding_needed = len(categorical_cols) > 0
    scaling_needed = len(numeric_cols) > 1

    # Score calculation
    score = 100.0
    if missing_pct > 30: score -= 30
    elif missing_pct > 10: score -= 15
    elif missing_pct > 5: score -= 5
    if duplicate_pct > 20: score -= 15
    elif duplicate_pct > 5: score -= 5
    if len(constant_cols) > 0: score -= len(constant_cols) * 5
    if len(high_card_cols) > 0: score -= len(high_card_cols) * 3
    if n_rows < 100: score -= 20
    elif n_rows < 1000: score -= 10
    if len(numeric_cols) == 0: score -= 20
    score = max(0, min(100, round(score, 1)))

    if score >= 80: status = "Excellent"
    elif score >= 60: status = "Good"
    elif score >= 40: status = "Fair"
    else: status = "Poor"

    return {
        "score": score,
        "status": status,
        "numeric_features": len(numeric_cols),
        "categorical_features": len(categorical_cols),
        "target_candidates": target_candidates[:5],
        "constant_features": constant_cols,
        "high_cardinality_features": high_card_cols,
        "missing_impact": "high" if missing_pct > 20 else "medium" if missing_pct > 5 else "low",
        "encoding_needed": encoding_needed,
        "encoding_columns": categorical_cols,
        "scaling_needed": scaling_needed,
        "scaling_columns": numeric_cols,
        "recommendations": _ml_recommendations(missing_pct, duplicate_pct, constant_cols,
                                                high_card_cols, n_rows, len(numeric_cols)),
    }


def _ml_recommendations(missing_pct, dup_pct, constant, high_card, n_rows, n_numeric):
    recs = []
    if missing_pct > 5:
        recs.append({"priority": "high", "text": f"Handle {missing_pct:.1f}% missing values before modeling."})
    if dup_pct > 5:
        recs.append({"priority": "high", "text": f"Remove {dup_pct:.1f}% duplicate rows."})
    if constant:
        recs.append({"priority": "medium", "text": f"Drop constant features: {', '.join(constant[:5])}."})
    if high_card:
        recs.append({"priority": "medium", "text": f"Encode or reduce high-cardinality features: {', '.join(high_card[:5])}."})
    if n_numeric > 1:
        recs.append({"priority": "low", "text": "Apply feature scaling (StandardScaler or RobustScaler)."})
    if n_rows < 1000:
        recs.append({"priority": "medium", "text": "Dataset is small — consider cross-validation and simpler models."})
    return recs


# ---------------------------------------------------------------------------
# AI insights
# ---------------------------------------------------------------------------

def _generate_ai_insights(df: pd.DataFrame, profile: dict, quality: dict,
                           corr_report: dict, dist_report: dict) -> list[str]:
    insights = []

    # Dataset overview insight
    n_rows, n_cols = df.shape
    insights.append(
        f"The dataset contains {n_rows:,} rows and {n_cols} columns "
        f"({len([c for c in profile['columns'] if c['type'] == 'numeric'])} numeric, "
        f"{len([c for c in profile['columns'] if c['type'] == 'categorical'])} categorical) "
        f"using approximately {profile['memory_kb']/1024:.1f} MB of memory."
    )

    # Quality
    health = quality.get("health_score", {})
    insights.append(
        f"Overall data quality score is {health.get('score', 'N/A')}/100 ({health.get('status', 'N/A')}). "
        f"Missing cells: {quality.get('missing_value_analysis', {}).get('overall_null_pct', 0)}% "
        f"of total. Duplicate rows: {quality.get('duplicate_analysis', {}).get('duplicate_pct', 0)}%."
    )

    # Correlation insights
    if corr_report.get("pairs"):
        top = corr_report["pairs"][0]
        insights.append(
            f"Strongest correlation: {top['feature_a']} ↔ {top['feature_b']} "
            f"(r = {top['value']:.3f}, {top['strength']})."
        )
        mc = corr_report.get("multicollinearity", [])
        if mc:
            mc_cols = set()
            for m in mc:
                mc_cols.add(m["feature_a"])
                mc_cols.add(m["feature_b"])
            insights.append(
                f"Multicollinearity detected in {len(mc)} pair(s) involving: "
                f"{', '.join(sorted(mc_cols)[:5])}. Consider dimensionality reduction."
            )

    # Distribution insights
    if dist_report.get("columns"):
        skewed = [c for c in dist_report["columns"] if "Skewed" in c["shape"].get("shape", "")]
        normal = [c for c in dist_report["columns"]
                  if c["normality"] and all(t["result"] == "Normally Distributed" for t in c["normality"])]
        if skewed:
            names = [c["name"] for c in skewed[:3]]
            insights.append(f"Skewed distributions detected: {', '.join(names)}. Consider transformations.")
        if normal:
            names = [c["name"] for c in normal[:3]]
            insights.append(f"Normal distributions: {', '.join(names)} — suitable for parametric tests.")

    # Missing value insights
    missing_cols = quality.get("missing_value_analysis", {}).get("columns", [])
    if missing_cols:
        top_missing = missing_cols[0]
        insights.append(
            f"Highest missing values in '{top_missing['name']}' "
            f"({top_missing['null_count']} values, {top_missing['null_pct']}%)."
        )

    # High cardinality
    hc = quality.get("unique_value_analysis", {}).get("high_cardinality_columns", [])
    if hc:
        names = [c["name"] for c in hc[:3]]
        insights.append(f"High-cardinality columns may cause overfitting: {', '.join(names)}.")

    return insights


# ---------------------------------------------------------------------------
# Business storytelling
# ---------------------------------------------------------------------------

def _generate_business_story(df: pd.DataFrame, profile: dict, quality: dict,
                              insights: list[str]) -> dict[str, Any]:
    health_score = quality.get("health_score", {}).get("score", 0)
    n_rows, n_cols = df.shape
    missing_pct = quality.get("missing_value_analysis", {}).get("overall_null_pct", 0)

    narrative = {
        "title": "Dataset Analysis Summary",
        "situation": (
            f"The dataset under review comprises {n_rows:,} records across {n_cols} attributes. "
            f"Data quality assessment yields an overall score of {health_score}/100. "
            f"Missing data accounts for {missing_pct}% of all cells."
        ),
        "observations": insights[:5] if insights else ["No significant observations."],
        "risks": [],
        "opportunities": [],
        "next_steps": [],
    }

    if missing_pct > 10:
        narrative["risks"].append("High missing data rate may bias analyses and reduce model accuracy.")
    if health_score < 60:
        narrative["risks"].append("Low data quality score indicates significant data cleaning is needed.")

    numeric_count = len([c for c in profile["columns"] if c["type"] == "numeric"])
    if numeric_count >= 3:
        narrative["opportunities"].append(
            f"With {numeric_count} numeric features, multivariate analysis and predictive modeling are viable."
        )
    if missing_pct < 5 and health_score >= 80:
        narrative["opportunities"].append("High data quality enables reliable statistical analysis and ML modeling.")

    narrative["next_steps"] = [
        "Complete data cleaning and preprocessing.",
        "Perform detailed exploratory analysis on key features.",
        "Build baseline predictive models.",
        "Validate findings with domain experts.",
    ]

    return narrative


# ---------------------------------------------------------------------------
# Main report generation
# ---------------------------------------------------------------------------

def generate_eda_report(df: pd.DataFrame, filename: str, profile: dict,
                         report_type: str = "full",
                         branding: dict | None = None) -> dict[str, Any]:
    """Generate a complete EDA report dictionary."""
    now = datetime.now(timezone.utc)
    brand = branding or {}

    sections_requested = REPORT_PROFILES.get(report_type, REPORT_PROFILES["full"])["sections"]

    # Core analyses
    quality = analyze_dataset_quality(df, profile)

    corr_report = {}
    if "correlation" in sections_requested or sections_requested == "all":
        try:
            corr_report = compute_correlation(df, "pearson")
        except Exception:
            corr_report = {"error": "Could not compute correlations"}

    dist_report = {}
    if "distribution" in sections_requested or sections_requested == "all":
        try:
            dist_report = compute_distribution(df)
        except Exception:
            dist_report = {"error": "Could not compute distributions"}

    outliers = _outlier_analysis(df)
    col_intel = _detect_column_intelligence(df)
    ml = _ml_readiness(df, profile)
    insights = _generate_ai_insights(df, profile, quality, corr_report, dist_report)
    business = _generate_business_story(df, profile, quality, insights)

    # Descriptive stats for all numeric columns
    numeric_df = df.select_dtypes(include=[np.number])
    descriptive_stats = {}
    for col in numeric_df.columns:
        s = numeric_df[col].dropna()
        if len(s) < 2:
            continue
        vals = s.values.astype(float)
        descriptive_stats[col] = {
            "count": int(len(vals)),
            "mean": round(float(np.mean(vals)), 4),
            "median": round(float(np.median(vals)), 4),
            "min": round(float(np.min(vals)), 4),
            "max": round(float(np.max(vals)), 4),
            "std": round(float(np.std(vals, ddof=1)), 4),
            "variance": round(float(np.var(vals, ddof=1)), 4),
            "skewness": round(float(sp_stats.skew(vals, bias=False)), 4),
            "kurtosis": round(float(sp_stats.kurtosis(vals, bias=False)), 4),
            "q1": round(float(np.percentile(vals, 25)), 4),
            "q2": round(float(np.percentile(vals, 50)), 4),
            "q3": round(float(np.percentile(vals, 75)), 4),
            "iqr": round(float(np.percentile(vals, 75) - np.percentile(vals, 25)), 4),
        }

    # Column details
    column_details = []
    for c in profile["columns"]:
        detail = {
            "name": c["name"],
            "type": c["type"],
            "non_null": c.get("non_null", 0),
            "null_count": c.get("null_count", 0),
            "null_pct": c.get("null_pct", 0),
            "unique_count": c.get("unique_count", 0),
        }
        # Match intelligence
        intel = next((i for i in col_intel if i["name"] == c["name"]), None)
        if intel:
            detail["tags"] = intel["tags"]
            detail["semantic"] = intel["semantic"]
        column_details.append(detail)

    return {
        "report_type": report_type,
        "generated_at": now.isoformat(),
        "filename": filename,
        "branding": {
            "title": brand.get("title", f"EDA Report — {filename}"),
            "author": brand.get("author", "Data Drop"),
            "logo_url": brand.get("logo_url", ""),
            "footer": brand.get("footer", "Generated by Data Drop"),
        },
        "dataset_overview": {
            "rows": profile["n_rows"],
            "columns": profile["n_cols"],
            "memory_kb": profile["memory_kb"],
            "memory_mb": round(profile["memory_kb"] / 1024, 2),
            "numeric_columns": len([c for c in profile["columns"] if c["type"] == "numeric"]),
            "categorical_columns": len([c for c in profile["columns"] if c["type"] == "categorical"]),
            "datetime_columns": len([c for c in profile["columns"] if c["type"] == "datetime"]),
            "boolean_columns": sum(1 for c in df.columns if df[c].dtype == bool),
            "missing_pct": quality.get("missing_value_analysis", {}).get("overall_null_pct", 0),
            "duplicate_pct": quality.get("duplicate_analysis", {}).get("duplicate_pct", 0),
        },
        "quality": quality,
        "descriptive_stats": descriptive_stats,
        "correlation": corr_report if "error" not in corr_report else {"error": corr_report.get("error")},
        "distribution": dist_report if "error" not in dist_report else {"error": dist_report.get("error")},
        "outliers": outliers,
        "column_intelligence": col_intel,
        "ml_readiness": ml,
        "insights": insights,
        "business_story": business,
        "column_details": column_details,
    }


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_json(report: dict) -> str:
    return json.dumps(report, indent=2, default=str)


def export_markdown(report: dict) -> str:
    lines = []
    b = report.get("branding", {})
    lines.append(f"# {b.get('title', 'EDA Report')}")
    lines.append(f"**Author:** {b.get('author', 'N/A')}  ")
    lines.append(f"**Generated:** {report.get('generated_at', 'N/A')}  ")
    lines.append(f"**Dataset:** {report.get('filename', 'N/A')}")
    lines.append("")

    ov = report.get("dataset_overview", {})
    lines.append("## Dataset Overview")
    lines.append(f"| Metric | Value |")
    lines.append(f"|---|---|")
    lines.append(f"| Rows | {ov.get('rows', 0):,} |")
    lines.append(f"| Columns | {ov.get('columns', 0)} |")
    lines.append(f"| Memory | {ov.get('memory_mb', 0)} MB |")
    lines.append(f"| Numeric | {ov.get('numeric_columns', 0)} |")
    lines.append(f"| Categorical | {ov.get('categorical_columns', 0)} |")
    lines.append(f"| Missing % | {ov.get('missing_pct', 0)}% |")
    lines.append("")

    # Quality
    q = report.get("quality", {}).get("health_score", {})
    lines.append("## Data Quality")
    lines.append(f"**Score:** {q.get('score', 'N/A')}/100 — {q.get('status', 'N/A')}")
    lines.append("")

    # Stats
    stats = report.get("descriptive_stats", {})
    if stats:
        lines.append("## Descriptive Statistics")
        lines.append("| Column | Mean | Median | Std | Min | Max | Skew | Kurt |")
        lines.append("|---|---|---|---|---|---|---|---|")
        for col, s in stats.items():
            lines.append(
                f"| {col} | {s['mean']} | {s['median']} | {s['std']} | "
                f"{s['min']} | {s['max']} | {s['skewness']} | {s['kurtosis']} |"
            )
        lines.append("")

    # Insights
    insights = report.get("insights", [])
    if insights:
        lines.append("## Key Insights")
        for i, ins in enumerate(insights, 1):
            lines.append(f"{i}. {ins}")
        lines.append("")

    # ML
    ml = report.get("ml_readiness", {})
    lines.append("## ML Readiness")
    lines.append(f"**Score:** {ml.get('score', 'N/A')}/100 — {ml.get('status', 'N/A')}")
    lines.append("")

    # Business
    biz = report.get("business_story", {})
    lines.append("## Business Summary")
    lines.append(f"### Current Situation")
    lines.append(biz.get("situation", ""))
    lines.append("")
    if biz.get("risks"):
        lines.append("### Risks")
        for r in biz["risks"]:
            lines.append(f"- {r}")
        lines.append("")
    if biz.get("opportunities"):
        lines.append("### Opportunities")
        for o in biz["opportunities"]:
            lines.append(f"- {o}")
        lines.append("")
    lines.append("### Recommended Next Steps")
    for s in biz.get("next_steps", []):
        lines.append(f"- {s}")
    lines.append("")

    return "\n".join(lines)


def export_excel_summary(report: dict) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill, Alignment, Border, Side

    wb = Workbook()
    header_font = Font(bold=True, color="FFFFFF", size=11)
    header_fill = PatternFill(start_color="4472C4", end_color="4472C4", fill_type="solid")
    border = Border(
        left=Side(style="thin"), right=Side(style="thin"),
        top=Side(style="thin"), bottom=Side(style="thin"),
    )

    def style_header(ws, row=1):
        for cell in ws[row]:
            cell.font = header_font
            cell.fill = header_fill
            cell.alignment = Alignment(horizontal="center")
            cell.border = border

    # Overview sheet
    ws = wb.active
    ws.title = "Overview"
    ov = report.get("dataset_overview", {})
    ws.append(["Metric", "Value"])
    ws.append(["Rows", ov.get("rows", 0)])
    ws.append(["Columns", ov.get("columns", 0)])
    ws.append(["Memory (MB)", ov.get("memory_mb", 0)])
    ws.append(["Numeric Columns", ov.get("numeric_columns", 0)])
    ws.append(["Categorical Columns", ov.get("categorical_columns", 0)])
    ws.append(["Missing %", ov.get("missing_pct", 0)])
    ws.append(["Duplicate %", ov.get("duplicate_pct", 0)])
    style_header(ws)

    # Statistics sheet
    ws2 = wb.create_sheet("Statistics")
    stats = report.get("descriptive_stats", {})
    if stats:
        ws2.append(["Column", "Count", "Mean", "Median", "Std", "Min", "Max", "Skewness", "Kurtosis", "Q1", "Q3", "IQR"])
        style_header(ws2)
        for col, s in stats.items():
            ws2.append([col, s["count"], s["mean"], s["median"], s["std"],
                        s["min"], s["max"], s["skewness"], s["kurtosis"], s["q1"], s["q3"], s["iqr"]])

    # Quality sheet
    ws3 = wb.create_sheet("Quality")
    q = report.get("quality", {})
    hs = q.get("health_score", {})
    ws3.append(["Metric", "Value"])
    style_header(ws3)
    ws3.append(["Health Score", hs.get("score", 0)])
    ws3.append(["Status", hs.get("status", "")])
    ws3.append(["Missing %", q.get("missing_value_analysis", {}).get("overall_null_pct", 0)])
    ws3.append(["Duplicate Rows", q.get("duplicate_analysis", {}).get("duplicate_rows", 0)])

    # Insights sheet
    ws4 = wb.create_sheet("Insights")
    ws4.append(["#", "Insight"])
    style_header(ws4)
    for i, ins in enumerate(report.get("insights", []), 1):
        ws4.append([i, ins])

    # ML Readiness sheet
    ws5 = wb.create_sheet("ML Readiness")
    ml = report.get("ml_readiness", {})
    ws5.append(["Metric", "Value"])
    style_header(ws5)
    ws5.append(["Score", ml.get("score", 0)])
    ws5.append(["Status", ml.get("status", "")])
    ws5.append(["Numeric Features", ml.get("numeric_features", 0)])
    ws5.append(["Categorical Features", ml.get("categorical_features", 0)])

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.getvalue()
