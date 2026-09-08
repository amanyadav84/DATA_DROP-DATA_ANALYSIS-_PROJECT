"""Generate Plotly figure JSON specs for the frontend to render."""

from __future__ import annotations

from typing import Any

import pandas as pd
import plotly.express as px
import plotly.graph_objects as go

from processor import _try_datetime, detect_column_type

DARK_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#c9d1d9", "family": "Inter, system-ui, sans-serif"},
    "margin": {"l": 48, "r": 24, "t": 40, "b": 48},
    "xaxis": {"gridcolor": "rgba(255,255,255,0.06)", "zerolinecolor": "rgba(255,255,255,0.1)"},
    "yaxis": {"gridcolor": "rgba(255,255,255,0.06)", "zerolinecolor": "rgba(255,255,255,0.1)"},
}

COLOR_SEQ = px.colors.qualitative.Pastel


def build_chart(df: pd.DataFrame, config: dict[str, Any], chart_type: str, title: str) -> dict:
    """Build a Plotly figure as JSON-serialisable dict for the given config."""
    chart_type = chart_type.lower()

    if chart_type == "histogram":
        fig = _histogram(df, config)
    elif chart_type == "scatter":
        fig = _scatter(df, config)
    elif chart_type == "bar":
        fig = _bar(df, config)
    elif chart_type == "line":
        fig = _line(df, config)
    elif chart_type == "box":
        fig = _box(df, config)
    elif chart_type == "pie":
        fig = _pie(df, config)
    else:
        fig = go.Figure()
        fig.update_layout(title="Unsupported chart type")

    fig.update_layout(title=title, **DARK_LAYOUT)
    fig.update_layout(legend={"bgcolor": "rgba(0,0,0,0)"})
    return jsonable_fig(fig)


def _histogram(df: pd.DataFrame, config: dict) -> go.Figure:
    x = config["x"]
    series = pd.to_numeric(df[x], errors="coerce")
    fig = px.histogram(x=series, nbins=30, color_discrete_sequence=["#7c9cff"])
    fig.update_layout(xaxis_title=x, yaxis_title="Count", bargap=0.05)
    return fig


def _scatter(df: pd.DataFrame, config: dict) -> go.Figure:
    x, y = config["x"], config["y"]
    color = config.get("color")
    work = df[[x, y] + ([color] if color else [])].dropna(subset=[x, y])
    fig = px.scatter(
        work,
        x=x,
        y=y,
        color=color if color else None,
        opacity=0.7,
        color_discrete_sequence=COLOR_SEQ,
    )
    fig.update_layout(xaxis_title=x, yaxis_title=y)
    fig.update_traces(marker=dict(size=6, line=dict(width=0)))
    return fig


def _bar(df: pd.DataFrame, config: dict) -> go.Figure:
    x, y = config["x"], config["y"]
    agg = config.get("agg", "mean")
    work = df[[x, y]].dropna()
    y_num = pd.to_numeric(work[y], errors="coerce")
    work = work.assign(_y=y_num).dropna(subset=["_y"])

    # Limit categories for readability.
    top_cats = work[x].value_counts().head(25).index
    work = work[work[x].isin(top_cats)]

    grouped = work.groupby(x)["_y"].agg(agg).sort_values(ascending=False).reset_index()
    fig = px.bar(grouped, x=x, y="_y", color_discrete_sequence=["#7c9cff"])
    fig.update_layout(xaxis_title=x, yaxis_title=f"{agg} of {y}")
    return fig


def _line(df: pd.DataFrame, config: dict) -> go.Figure:
    x, y = config["x"], config["y"]
    work = df[[x, y]].copy()
    parsed = _try_datetime(work[x])
    if parsed is not None:
        work[x] = parsed
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().sort_values(x)
    fig = px.line(work, x=x, y=y, color_discrete_sequence=["#7c9cff"])
    fig.update_layout(xaxis_title=x, yaxis_title=y)
    return fig


def _box(df: pd.DataFrame, config: dict) -> go.Figure:
    x, y = config["x"], config["y"]
    work = df[[x, y]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna(subset=[y])
    top_cats = work[x].value_counts().head(15).index
    work = work[work[x].isin(top_cats)]
    fig = px.box(work, x=x, y=y, color=x, color_discrete_sequence=COLOR_SEQ)
    fig.update_layout(xaxis_title=x, yaxis_title=y, showlegend=False)
    return fig


def _pie(df: pd.DataFrame, config: dict) -> go.Figure:
    x = config["x"]
    counts = df[x].value_counts().head(12).reset_index()
    counts.columns = [x, "count"]
    fig = px.pie(counts, names=x, values="count", color_discrete_sequence=COLOR_SEQ)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


def jsonable_fig(fig: go.Figure) -> dict:
    """Convert a Plotly figure to a plain JSON dict (safe for FastAPI response)."""
    import json

    raw = fig.to_plotly_json()
    return json.loads(json.dumps(raw, default=_json_default))


def _json_default(obj: Any) -> Any:
    import numpy as np

    if isinstance(obj, (np.integer,)):
        return int(obj)
    if isinstance(obj, (np.floating,)):
        return float(obj)
    if isinstance(obj, (np.bool_,)):
        return bool(obj)
    if isinstance(obj, pd.Timestamp):
        return obj.isoformat()
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    return str(obj)
