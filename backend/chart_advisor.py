"""AI Chart Advisor — recommend the best chart type based on data characteristics."""

from __future__ import annotations

from typing import Any

import pandas as pd

from processor import detect_column_type


# ---------------------------------------------------------------------------
# Rule-based chart recommendation (no LLM needed)
# ---------------------------------------------------------------------------

def recommend_charts(df: pd.DataFrame, profile: dict) -> list[dict[str, Any]]:
    """Recommend the best chart types based on data analysis."""
    numeric_cols = [c["name"] for c in profile["columns"] if c["type"] == "numeric"]
    cat_cols = [c["name"] for c in profile["columns"] if c["type"] == "categorical"]
    date_cols = [c["name"] for c in profile["columns"] if c["type"] == "datetime"]

    recommendations = []

    # Time series → Line chart
    if date_cols and numeric_cols:
        for dt in date_cols[:2]:
            for num in numeric_cols[:2]:
                recommendations.append({
                    "chart_type": "line",
                    "config": {"x": dt, "y": num},
                    "title": f"{num} over {dt}",
                    "reason": f"DateTime column '{dt}' detected → line chart shows trends over time",
                    "confidence": 95,
                    "category": "trend",
                })

    # Single categorical → Pie or Bar
    if cat_cols:
        for cat in cat_cols[:2]:
            nunique = df[cat].nunique()
            if nunique <= 8:
                recommendations.append({
                    "chart_type": "pie",
                    "config": {"x": cat},
                    "title": f"Distribution of {cat}",
                    "reason": f"'{cat}' has {nunique} categories (≤8) → pie chart shows composition",
                    "confidence": 85,
                    "category": "composition",
                })
            recommendations.append({
                "chart_type": "bar",
                "config": {"x": cat, "y": numeric_cols[0] if numeric_cols else None, "agg": "count"},
                "title": f"Count by {cat}",
                "reason": f"Bar chart compares frequencies across '{cat}' categories",
                "confidence": 90,
                "category": "comparison",
            })

    # Categorical vs Numeric → Bar chart
    if cat_cols and numeric_cols:
        for cat in cat_cols[:2]:
            for num in numeric_cols[:2]:
                recommendations.append({
                    "chart_type": "bar",
                    "config": {"x": cat, "y": num, "agg": "mean"},
                    "title": f"Average {num} by {cat}",
                    "reason": f"Bar chart compares '{num}' across '{cat}' groups",
                    "confidence": 88,
                    "category": "comparison",
                })

    # Single numeric → Histogram
    for num in numeric_cols[:3]:
        skew = pd.to_numeric(df[num], errors="coerce").skew()
        recommendations.append({
            "chart_type": "histogram",
            "config": {"x": num},
            "title": f"Distribution of {num}",
            "reason": f"Histogram reveals the distribution shape of '{num}'" + (f" (skewness={skew:.2f})" if abs(skew) > 0.5 else ""),
            "confidence": 90,
            "category": "distribution",
        })

    # Two numeric → Scatter
    if len(numeric_cols) >= 2:
        for i in range(min(len(numeric_cols) - 1, 3)):
            x, y = numeric_cols[i], numeric_cols[i + 1]
            corr = pd.to_numeric(df[x], errors="coerce").corr(pd.to_numeric(df[y], errors="coerce"))
            recommendations.append({
                "chart_type": "scatter",
                "config": {"x": x, "y": y},
                "title": f"{y} vs {x}",
                "reason": f"Scatter plot reveals relationship between '{x}' and '{y}'" + (f" (r={corr:.2f})" if pd.notna(corr) else ""),
                "confidence": 85 if pd.notna(corr) and abs(corr) > 0.3 else 70,
                "category": "relationship",
            })

    # Categorical vs Numeric → Box plot
    if cat_cols and numeric_cols:
        cat = cat_cols[0]
        num = numeric_cols[0]
        nunique = df[cat].nunique()
        if nunique <= 15:
            recommendations.append({
                "chart_type": "box",
                "config": {"x": cat, "y": num},
                "title": f"{num} distribution by {cat}",
                "reason": f"Box plot shows spread and outliers of '{num}' across '{cat}' groups",
                "confidence": 82,
                "category": "distribution",
            })

    # Sort by confidence
    recommendations.sort(key=lambda r: r["confidence"], reverse=True)
    return recommendations
