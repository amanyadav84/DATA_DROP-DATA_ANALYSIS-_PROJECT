"""Advanced Correlation Analysis module."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _json_default(obj: Any) -> Any:
    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    return str(obj)


def _to_jsonable(fig: go.Figure) -> dict:
    raw = fig.to_plotly_json()
    return json.loads(json.dumps(raw, default=_json_default))


def _classify_strength(val: float) -> str:
    val = abs(val)
    if val >= 0.90:
        return "Very Strong"
    if val >= 0.70:
        return "Strong"
    if val >= 0.50:
        return "Moderate"
    if val >= 0.30:
        return "Weak"
    return "Very Weak"


def _direction(val: float) -> str:
    if val > 0:
        return "Positive"
    if val < 0:
        return "Negative"
    return "None"


def _strength_badge_color(strength: str) -> str:
    return {
        "Very Strong": "#56d9a1",
        "Strong": "#7c9cff",
        "Moderate": "#f0a35e",
        "Weak": "#e06c9c",
        "Very Weak": "#6e7681",
    }.get(strength, "#6e7681")


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def compute_correlation(df: pd.DataFrame, method: str = "pearson") -> dict[str, Any]:
    """Compute full correlation analysis for all numeric columns."""
    numeric_df = df.select_dtypes(include=[np.number])
    cols = numeric_df.columns.tolist()

    if len(cols) < 2:
        return {"error": "Correlation analysis requires at least two numeric columns."}

    # Drop rows where all numeric values are NaN, then fill remaining NaNs
    clean = numeric_df.dropna(how="all").fillna(0)

    # Compute correlation matrix
    corr_matrix = clean.corr(method=method)

    # Build pairwise list (upper triangle only, skip self-correlations)
    pairs = []
    for i, a in enumerate(cols):
        for j, b in enumerate(cols):
            if j <= i:
                continue
            val = float(corr_matrix.loc[a, b])
            if np.isnan(val):
                continue
            strength = _classify_strength(val)
            pairs.append({
                "feature_a": a,
                "feature_b": b,
                "value": round(val, 4),
                "abs_value": round(abs(val), 4),
                "strength": strength,
                "direction": _direction(val),
                "badge_color": _strength_badge_color(strength),
            })

    # Sort by absolute value descending
    pairs.sort(key=lambda x: x["abs_value"], reverse=True)

    # Top correlations
    top_positive = [p for p in pairs if p["direction"] == "Positive"][:10]
    top_negative = [p for p in pairs if p["direction"] == "Negative"][:10]

    # Most independent (closest to 0)
    independent = sorted(pairs, key=lambda x: x["abs_value"])[:10]

    # Most influential (highest average absolute correlation)
    influence = {}
    for p in pairs:
        for feat in [p["feature_a"], p["feature_b"]]:
            influence.setdefault(feat, []).append(p["abs_value"])
    influential_cols = [
        {"name": k, "avg_corr": round(float(np.mean(v)), 4)}
        for k, v in sorted(influence.items(), key=lambda x: -np.mean(x[1]))
    ]

    # Multicollinearity detection
    multicollinear = [p for p in pairs if p["abs_value"] > 0.90]

    # Generate insights
    insights = _generate_insights(pairs, cols, influential_cols, multicollinear)

    # Generate recommendations
    recommendations = _generate_recommendations(pairs, multicollinear, influential_cols, cols)

    # Build matrix data for heatmap
    matrix = _build_matrix(corr_matrix, cols)

    # Network graph data
    network = _build_network(pairs, cols)

    return {
        "method": method,
        "numeric_columns": cols,
        "num_numeric_columns": len(cols),
        "matrix": matrix,
        "pairs": pairs,
        "top_positive": top_positive,
        "top_negative": top_negative,
        "independent_features": independent,
        "influential_columns": influential_cols,
        "multicollinearity": multicollinear,
        "insights": insights,
        "recommendations": recommendations,
        "network": network,
    }


# ---------------------------------------------------------------------------
# Matrix & heatmap
# ---------------------------------------------------------------------------

def _build_matrix(corr_matrix: pd.DataFrame, cols: list[str]) -> dict:
    return {
        "columns": cols,
        "values": [[round(float(corr_matrix.iloc[i, j]), 4) for j in range(len(cols))] for i in range(len(cols))],
    }


def build_heatmap(spec: dict, title: str = "Correlation Heatmap") -> dict:
    """Build a Plotly heatmap figure."""
    cols = spec["columns"]
    values = spec["values"]

    fig = go.Figure(data=go.Heatmap(
        z=values,
        x=cols,
        y=cols,
        colorscale=[
            [0.0, "#f87171"],
            [0.25, "#e06c9c"],
            [0.5, "#1c232e"],
            [0.75, "#7c9cff"],
            [1.0, "#56d9a1"],
        ],
        zmin=-1,
        zmax=1,
        text=[[str(round(v, 2)) for v in row] for row in values],
        texttemplate="%{text}",
        textfont={"size": 10, "color": "#e6edf3"},
        hovertemplate="<b>%{y}</b> vs <b>%{x}</b><br>Correlation: %{z:.4f}<extra></extra>",
        colorbar=dict(title="r", tickvals=[-1, -0.5, 0, 0.5, 1]),
    ))

    fig.update_layout(
        title=title,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c9d1d9", family="Inter, system-ui, sans-serif"),
        margin=dict(l=120, r=20, t=50, b=120),
        xaxis=dict(side="bottom", tickangle=-45),
        height=max(400, len(cols) * 35 + 100),
        width=max(400, len(cols) * 35 + 100),
    )

    return _to_jsonable(fig)


# ---------------------------------------------------------------------------
# Pairwise scatter plot
# ---------------------------------------------------------------------------

def build_scatter(df: pd.DataFrame, col_a: str, col_b: str) -> dict:
    """Build scatter plot with trend line and R-squared for two columns."""
    work = df[[col_a, col_b]].dropna()
    x = work[col_a].values
    y = work[col_b].values

    fig = go.Figure()

    # Main scatter
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="markers",
        marker=dict(color="#7c9cff", opacity=0.5, size=5),
        name="Data Points",
        hovertemplate=f"<b>{col_a}</b>: %{{x}}<br><b>{col_b}</b>: %{{y}}<extra></extra>",
    ))

    # Regression line
    if len(x) > 1:
        coeffs = np.polyfit(x, y, 1)
        trend_x = np.linspace(float(x.min()), float(x.max()), 100)
        trend_y = np.polyval(coeffs, trend_x)
        fig.add_trace(go.Scatter(
            x=trend_x, y=trend_y,
            mode="lines",
            line=dict(color="#f87171", width=2, dash="dash"),
            name="Trend Line",
        ))

        # R-squared
        y_pred = np.polyval(coeffs, x)
        ss_res = float(np.sum((y - y_pred) ** 2))
        ss_tot = float(np.sum((y - np.mean(y)) ** 2))
        r_squared = 1 - (ss_res / ss_tot) if ss_tot != 0 else 0
        fig.add_annotation(
            text=f"R² = {r_squared:.4f}",
            xref="paper", yref="paper",
            x=0.98, y=0.02,
            showarrow=False,
            font=dict(size=14, color="#56d9a1"),
            bgcolor="rgba(0,0,0,0.5)",
            borderpad=4,
        )

    fig.update_layout(
        title=f"{col_a} vs {col_b}",
        xaxis_title=col_a,
        yaxis_title=col_b,
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c9d1d9", family="Inter, system-ui, sans-serif"),
        margin=dict(l=60, r=20, t=50, b=60),
        xaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        yaxis=dict(gridcolor="rgba(255,255,255,0.06)"),
        height=450,
        legend=dict(bgcolor="rgba(0,0,0,0)"),
    )

    return _to_jsonable(fig)


# ---------------------------------------------------------------------------
# Network graph
# ---------------------------------------------------------------------------

def _build_network(pairs: list[dict], cols: list[str]) -> dict:
    """Build network graph data for correlation visualization."""
    nodes = [{"id": c, "label": c} for c in cols]
    edges = []
    for p in pairs:
        if p["abs_value"] >= 0.3:
            edges.append({
                "source": p["feature_a"],
                "target": p["feature_b"],
                "value": p["value"],
                "abs_value": p["abs_value"],
                "color": "#56d9a1" if p["value"] > 0 else "#f87171",
                "width": max(1, p["abs_value"] * 5),
            })
    return {"nodes": nodes, "edges": edges}


def build_network_graph(network: dict) -> dict:
    """Build a Plotly network graph."""
    import math

    nodes = network["nodes"]
    edges = network["edges"]

    if not nodes:
        fig = go.Figure()
        fig.update_layout(title="No data for network graph")
        return _to_jsonable(fig)

    n = len(nodes)
    # Circular layout
    pos = {}
    for i, node in enumerate(nodes):
        angle = 2 * math.pi * i / n
        pos[node["id"]] = (math.cos(angle), math.sin(angle))

    # Node positions
    node_x = [pos[n["id"]][0] for n in nodes]
    node_y = [pos[n["id"]][1] for n in nodes]
    node_labels = [n["label"] for n in nodes]

    fig = go.Figure()

    # Draw edges
    for e in edges:
        x0, y0 = pos.get(e["source"], (0, 0))
        x1, y1 = pos.get(e["target"], (0, 0))
        fig.add_trace(go.Scatter(
            x=[x0, x1, None],
            y=[y0, y1, None],
            mode="lines",
            line=dict(width=e["width"], color=e["color"], dash="solid"),
            opacity=0.6,
            hoverinfo="text",
            text=f"{e['source']} ↔ {e['target']}: {e['value']:.3f}",
            showlegend=False,
        ))

    # Draw nodes
    fig.add_trace(go.Scatter(
        x=node_x, y=node_y,
        mode="markers+text",
        marker=dict(size=20, color="#7c9cff", line=dict(width=2, color="#0d1117")),
        text=node_labels,
        textposition="top center",
        textfont=dict(size=10, color="#e6edf3"),
        hovertemplate="<b>%{text}</b><extra></extra>",
        showlegend=False,
    ))

    fig.update_layout(
        title="Correlation Network Graph",
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        font=dict(color="#c9d1d9", family="Inter, system-ui, sans-serif"),
        margin=dict(l=20, r=20, t=50, b=20),
        xaxis=dict(visible=False),
        yaxis=dict(visible=False, scaleanchor="x"),
        height=max(400, n * 25 + 100),
        dragmode="pan",
    )

    return _to_jsonable(fig)


# ---------------------------------------------------------------------------
# Insights
# ---------------------------------------------------------------------------

def _generate_insights(pairs: list[dict], cols: list[str],
                       influential: list[dict], multicollinear: list[dict]) -> list[str]:
    """Generate dataset-specific insights from correlation data."""
    insights = []

    if not pairs:
        return ["No numeric column pairs found for correlation analysis."]

    # Top positive
    if pairs and pairs[0]["direction"] == "Positive":
        p = pairs[0]
        insights.append(
            f"{p['feature_a']} and {p['feature_b']} have the strongest positive correlation "
            f"({p['value']:.3f}), indicating they move together strongly."
        )

    # Top negative
    negatives = [p for p in pairs if p["direction"] == "Negative"]
    if negatives:
        p = negatives[0]
        insights.append(
            f"{p['feature_a']} and {p['feature_b']} have the strongest negative correlation "
            f"({p['value']:.3f}), meaning as one increases the other tends to decrease."
        )

    # Weakest
    if len(pairs) > 2:
        weakest = sorted(pairs, key=lambda x: x["abs_value"])[0]
        insights.append(
            f"{weakest['feature_a']} and {weakest['feature_b']} are nearly independent "
            f"(correlation: {weakest['value']:.3f}) with minimal linear relationship."
        )

    # Multicollinearity warning
    if multicollinear:
        cols_involved = set()
        for mc in multicollinear:
            cols_involved.add(mc["feature_a"])
            cols_involved.add(mc["feature_b"])
        insights.append(
            f"Warning: {len(multicollinear)} highly correlated pair(s) detected (|r| > 0.90). "
            f"Columns involved: {', '.join(sorted(cols_involved)[:5])}. "
            f"This may cause multicollinearity in regression models."
        )

    # Most influential
    if influential:
        top = influential[0]
        insights.append(
            f"'{top['name']}' is the most influential feature with an average absolute "
            f"correlation of {top['avg_corr']:.3f} across all other numeric columns."
        )

    # Most independent
    independent_cols = [p for p in pairs if p["abs_value"] < 0.1]
    if independent_cols:
        feat = independent_cols[0]
        insights.append(
            f"'{feat['feature_a']}' and '{feat['feature_b']}' are almost completely uncorrelated "
            f"({feat['value']:.3f}), suggesting they capture independent information."
        )

    # General
    n = len(pairs)
    strong_count = len([p for p in pairs if p["abs_value"] >= 0.7])
    if strong_count > 0:
        insights.append(
            f"{strong_count} out of {n} pairs ({strong_count/n*100:.0f}%) show strong or "
            f"very strong linear relationships."
        )

    return insights


def _generate_recommendations(pairs: list[dict], multicollinear: list[dict],
                              influential: list[dict], cols: list[str]) -> list[dict]:
    """Generate actionable recommendations."""
    recs = []

    # Multicollinearity
    if multicollinear:
        for mc in multicollinear[:3]:
            recs.append({
                "priority": "high",
                "category": "multicollinearity",
                "title": f"Remove redundant feature",
                "description": (
                    f"'{mc['feature_a']}' and '{mc['feature_b']}' have a correlation of "
                    f"{mc['value']:.3f}. Consider removing one to reduce multicollinearity."
                ),
                "affected_columns": [mc["feature_a"], mc["feature_b"]],
                "action": "remove_feature",
            })

    # Feature engineering
    if multicollinear:
        mc = multicollinear[0]
        recs.append({
            "priority": "medium",
            "category": "feature_engineering",
            "title": "Merge highly correlated features",
            "description": (
                f"Consider combining '{mc['feature_a']}' and '{mc['feature_b']}' "
                f"into a single feature (e.g., ratio, difference, or PCA component)."
            ),
            "affected_columns": [mc["feature_a"], mc["feature_b"]],
            "action": "merge_features",
        })

    # Good prediction candidates
    if influential:
        top_feats = [inf["name"] for inf in influential[:3]]
        recs.append({
            "priority": "medium",
            "category": "prediction",
            "title": "Best features for prediction",
            "description": (
                f"'{top_feats[0]}' has the highest average correlation with other features, "
                f"making it a strong candidate for predictive modeling."
            ),
            "affected_columns": top_feats,
            "action": "use_for_prediction",
        })

    # Low-value columns
    low_corr_cols = set()
    for p in pairs:
        if p["abs_value"] < 0.1:
            low_corr_cols.add(p["feature_a"])
            low_corr_cols.add(p["feature_b"])
    if low_corr_cols:
        recs.append({
            "priority": "low",
            "category": "feature_selection",
            "title": "Columns with little analytical value",
            "description": (
                f"{len(low_corr_cols)} column(s) have very low correlation with all other features "
                f"and may have limited analytical value: {', '.join(sorted(low_corr_cols)[:5])}."
            ),
            "affected_columns": sorted(low_corr_cols)[:5],
            "action": "review_columns",
        })

    return recs


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_correlation_csv(pairs: list[dict]) -> str:
    """Export correlation pairs as CSV."""
    if not pairs:
        return ""
    df = pd.DataFrame(pairs)
    cols = ["feature_a", "feature_b", "value", "abs_value", "strength", "direction"]
    df = df[[c for c in cols if c in df.columns]]
    return df.to_csv(index=False)


def export_correlation_json(pairs: list[dict]) -> str:
    """Export correlation pairs as JSON."""
    return json.dumps(pairs, indent=2, default=_json_default)
