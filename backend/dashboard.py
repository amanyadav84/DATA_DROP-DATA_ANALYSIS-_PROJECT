"""Dashboard persistence, AI generation, templates, and extended chart building."""

from __future__ import annotations

import io
import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from threading import Lock
from typing import Any

import numpy as np
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from plotly.subplots import make_subplots

from processor import detect_column_type, _safe_number, _safe_str, _try_datetime


# ---------------------------------------------------------------------------
# In-memory dashboard store
# ---------------------------------------------------------------------------

class DashboardStore:
    def __init__(self) -> None:
        self._store: dict[str, dict] = {}
        self._lock = Lock()

    def save(self, session_id: str, dashboard: dict) -> str:
        dash_id = dashboard.get("id") or uuid.uuid4().hex[:12]
        dashboard["id"] = dash_id
        dashboard["session_id"] = session_id
        dashboard["updated_at"] = datetime.now(timezone.utc).isoformat()
        if "created_at" not in dashboard:
            dashboard["created_at"] = dashboard["updated_at"]
        if "version" not in dashboard:
            dashboard["version"] = 1
        else:
            dashboard["version"] = dashboard.get("version", 1) + 1

        with self._lock:
            key = f"{session_id}:{dash_id}"
            if key not in self._store:
                self._store[key] = {"current": dashboard, "versions": []}
            entry = self._store[key]
            entry["versions"].append(entry["current"].copy())
            entry["current"] = dashboard
        return dash_id

    def get(self, session_id: str, dash_id: str) -> dict | None:
        with self._lock:
            entry = self._store.get(f"{session_id}:{dash_id}")
            if entry is None:
                return None
            return entry["current"].copy()

    def list_dashboards(self, session_id: str) -> list[dict]:
        with self._lock:
            results = []
            for key, entry in self._store.items():
                if key.startswith(f"{session_id}:"):
                    d = entry["current"]
                    results.append({
                        "id": d.get("id"),
                        "title": d.get("title", "Untitled Dashboard"),
                        "created_at": d.get("created_at"),
                        "updated_at": d.get("updated_at"),
                        "version": d.get("version", 1),
                        "pages": len(d.get("pages", [])),
                    })
            return results

    def delete(self, session_id: str, dash_id: str) -> bool:
        with self._lock:
            key = f"{session_id}:{dash_id}"
            if key in self._store:
                del self._store[key]
                return True
            return False

    def duplicate(self, session_id: str, dash_id: str) -> str | None:
        with self._lock:
            entry = self._store.get(f"{session_id}:{dash_id}")
            if entry is None:
                return None
            new_dash = entry["current"].copy()
            new_dash["id"] = uuid.uuid4().hex[:12]
            new_dash["title"] = new_dash.get("title", "Untitled") + " (Copy)"
            new_dash["created_at"] = datetime.now(timezone.utc).isoformat()
            new_dash["updated_at"] = new_dash["created_at"]
            new_dash["version"] = 1
            new_key = f"{session_id}:{new_dash['id']}"
            self._store[new_key] = {"current": new_dash, "versions": []}
            return new_dash["id"]

    def get_versions(self, session_id: str, dash_id: str) -> list[dict]:
        with self._lock:
            entry = self._store.get(f"{session_id}:{dash_id}")
            if entry is None:
                return []
            versions = []
            for i, v in enumerate(entry["versions"]):
                versions.append({
                    "version": v.get("version", i + 1),
                    "updated_at": v.get("updated_at"),
                    "title": v.get("title"),
                })
            return versions

    def restore_version(self, session_id: str, dash_id: str, version: int) -> dict | None:
        with self._lock:
            entry = self._store.get(f"{session_id}:{dash_id}")
            if entry is None:
                return None
            for v in entry["versions"]:
                if v.get("version") == version:
                    restored = v.copy()
                    restored["updated_at"] = datetime.now(timezone.utc).isoformat()
                    restored["version"] = entry["current"].get("version", 1) + 1
                    entry["versions"].append(entry["current"].copy())
                    entry["current"] = restored
                    return restored
        return None


dashboard_store = DashboardStore()


# ---------------------------------------------------------------------------
# Extended chart types
# ---------------------------------------------------------------------------

DARK_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#c9d1d9", "family": "Inter, system-ui, sans-serif"},
    "margin": {"l": 48, "r": 24, "t": 40, "b": 48},
    "xaxis": {"gridcolor": "rgba(255,255,255,0.06)", "zerolinecolor": "rgba(255,255,255,0.1)"},
    "yaxis": {"gridcolor": "rgba(255,255,255,0.06)", "zerolinecolor": "rgba(255,255,255,0.1)"},
}

COLOR_SEQ = px.colors.qualitative.Pastel + px.colors.qualitative.Set2


def build_dashboard_chart(df: pd.DataFrame, widget: dict) -> dict:
    chart_type = widget.get("chart_type", "bar")
    config = widget.get("config", {})
    title = widget.get("title", "")

    builders = {
        "bar": _db_bar, "stacked_bar": _db_stacked_bar,
        "horizontal_bar": _db_hbar, "grouped_bar": _db_grouped_bar,
        "line": _db_line, "area": _db_area, "spline": _db_spline,
        "pie": _db_pie, "donut": _db_donut,
        "scatter": _db_scatter, "bubble": _db_bubble,
        "histogram": _db_histogram, "heatmap": _db_heatmap,
        "treemap": _db_treemap, "sunburst": _db_sunburst,
        "box": _db_box, "violin": _db_violin, "density": _db_density,
        "radar": _db_radar, "waterfall": _db_waterfall,
        "funnel": _db_funnel, "gauge": _db_gauge,
        "kpi": _db_kpi, "data_table": _db_data_table,
        "correlation_heatmap": _db_corr_heatmap,
        "time_series": _db_time_series, "forecast": _db_forecast,
        "distribution": _db_distribution, "outlier": _db_outlier,
    }

    builder = builders.get(chart_type, _db_bar)
    try:
        fig = builder(df, config)
    except Exception as exc:
        fig = go.Figure()
        fig.update_layout(title=f"Error: {exc}")

    fig.update_layout(title=title, **DARK_LAYOUT)
    fig.update_layout(legend={"bgcolor": "rgba(0,0,0,0)"})
    return jsonable_fig(fig)


def _db_bar(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna()
    top = work[x].value_counts().head(25).index
    work = work[work[x].isin(top)]
    agg = c.get("agg", "mean")
    grouped = work.groupby(x)[y].agg(agg).sort_values(ascending=False).reset_index()
    fig = px.bar(grouped, x=x, y=y, color_discrete_sequence=["#7c9cff"])
    return fig


def _db_stacked_bar(df, c):
    x, y, color = c["x"], c["y"], c.get("color")
    if not color:
        return _db_bar(df, c)
    work = df[[x, y, color]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna()
    top = work[x].value_counts().head(15).index
    work = work[work[x].isin(top)]
    grouped = work.groupby([x, color])[y].mean().reset_index()
    fig = px.bar(grouped, x=x, y=y, color=color, barmode="stack", color_discrete_sequence=COLOR_SEQ)
    return fig


def _db_hbar(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna()
    top = work[x].value_counts().head(20).index
    work = work[work[x].isin(top)]
    agg = c.get("agg", "mean")
    grouped = work.groupby(x)[y].agg(agg).sort_values(ascending=True).reset_index()
    fig = px.bar(grouped, x=y, y=x, orientation="h", color_discrete_sequence=["#7c9cff"])
    return fig


def _db_grouped_bar(df, c):
    x, y, color = c["x"], c["y"], c.get("color")
    if not color:
        return _db_bar(df, c)
    work = df[[x, y, color]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna()
    top_x = work[x].value_counts().head(12).index
    top_c = work[color].value_counts().head(8).index
    work = work[work[x].isin(top_x) & work[color].isin(top_c)]
    grouped = work.groupby([x, color])[y].mean().reset_index()
    fig = px.bar(grouped, x=x, y=y, color=color, barmode="group", color_discrete_sequence=COLOR_SEQ)
    return fig


def _db_line(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].copy()
    parsed = _try_datetime(work[x])
    if parsed is not None:
        work[x] = parsed
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().sort_values(x)
    color = c.get("color")
    if color and color in df.columns:
        work = df[[x, y, color]].copy()
        if parsed is not None:
            work[x] = parsed
        work[y] = pd.to_numeric(work[y], errors="coerce")
        work = work.dropna().sort_values(x)
        fig = px.line(work, x=x, y=y, color=color, color_discrete_sequence=COLOR_SEQ)
    else:
        fig = px.line(work, x=x, y=y, color_discrete_sequence=["#7c9cff"])
    return fig


def _db_area(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].copy()
    parsed = _try_datetime(work[x])
    if parsed is not None:
        work[x] = parsed
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().sort_values(x)
    fig = px.area(work, x=x, y=y, color_discrete_sequence=["#7c9cff"])
    return fig


def _db_spline(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].copy()
    parsed = _try_datetime(work[x])
    if parsed is not None:
        work[x] = parsed
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().sort_values(x)
    fig = px.line(work, x=x, y=y, color_discrete_sequence=["#7c9cff"])
    fig.update_traces(line_shape="spline")
    return fig


def _db_pie(df, c):
    x = c["x"]
    counts = df[x].value_counts().head(12).reset_index()
    counts.columns = [x, "count"]
    fig = px.pie(counts, names=x, values="count", color_discrete_sequence=COLOR_SEQ)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


def _db_donut(df, c):
    x = c["x"]
    counts = df[x].value_counts().head(12).reset_index()
    counts.columns = [x, "count"]
    fig = px.pie(counts, names=x, values="count", color_discrete_sequence=COLOR_SEQ, hole=0.5)
    fig.update_traces(textposition="inside", textinfo="percent+label")
    return fig


def _db_scatter(df, c):
    x, y = c["x"], c["y"]
    color = c.get("color")
    cols = [x, y] + ([color] if color and color in df.columns else [])
    work = df[cols].dropna(subset=[x, y])
    fig = px.scatter(work, x=x, y=y, color=color if color and color in df.columns else None,
                     opacity=0.7, color_discrete_sequence=COLOR_SEQ)
    fig.update_traces(marker=dict(size=6))
    return fig


def _db_bubble(df, c):
    x, y, size = c["x"], c["y"], c.get("size")
    color = c.get("color")
    cols = [x, y]
    if size and size in df.columns:
        cols.append(size)
    if color and color in df.columns:
        cols.append(color)
    work = df[cols].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    if size and size in work.columns:
        work[size] = pd.to_numeric(work[size], errors="coerce")
    work = work.dropna()
    fig = px.scatter(work, x=x, y=y,
                     size=size if size and size in work.columns else None,
                     color=color if color and color in work.columns else None,
                     opacity=0.7, color_discrete_sequence=COLOR_SEQ)
    return fig


def _db_histogram(df, c):
    x = c["x"]
    series = pd.to_numeric(df[x], errors="coerce").dropna()
    fig = px.histogram(x=series, nbins=c.get("bins", 30), color_discrete_sequence=["#7c9cff"])
    return fig


def _db_heatmap(df, c):
    cols = c.get("columns")
    if not cols:
        num_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
        cols = num_cols[:8]
    if len(cols) < 2:
        fig = go.Figure()
        fig.update_layout(title="Need at least 2 numeric columns")
        return fig
    corr = df[cols].corr()
    fig = go.Figure(data=go.Heatmap(
        z=corr.values, x=corr.columns.tolist(), y=corr.index.tolist(),
        colorscale="RdBu_r", zmin=-1, zmax=1,
        text=np.round(corr.values, 2), texttemplate="%{text}",
        textfont={"size": 10, "color": "#c9d1d9"},
    ))
    fig.update_layout(margin=dict(l=100, b=100))
    return fig


def _db_treemap(df, c):
    path = c.get("path") or c.get("x")
    value = c.get("y") or c.get("value")
    if not path:
        fig = go.Figure()
        fig.update_layout(title="path is required for treemap")
        return fig
    if value:
        work = df[[path, value]].dropna()
        work[value] = pd.to_numeric(work[value], errors="coerce")
        work = work.dropna()
        grouped = work.groupby(path)[value].sum().reset_index()
        fig = px.treemap(grouped, path=[path], values=value, color_discrete_sequence=COLOR_SEQ)
    else:
        counts = df[path].value_counts().reset_index()
        counts.columns = [path, "count"]
        fig = px.treemap(counts, path=[path], values="count", color_discrete_sequence=COLOR_SEQ)
    return fig


def _db_sunburst(df, c):
    path = c.get("path") or c.get("x")
    value = c.get("y") or c.get("value")
    if not path:
        fig = go.Figure()
        fig.update_layout(title="path is required for sunburst")
        return fig
    if value:
        work = df[[path, value]].dropna()
        work[value] = pd.to_numeric(work[value], errors="coerce")
        work = work.dropna()
        grouped = work.groupby(path)[value].sum().reset_index()
        fig = px.sunburst(grouped, path=[path], values=value, color_discrete_sequence=COLOR_SEQ)
    else:
        counts = df[path].value_counts().reset_index()
        counts.columns = [path, "count"]
        fig = px.sunburst(counts, path=[path], values="count", color_discrete_sequence=COLOR_SEQ)
    return fig


def _db_box(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna()
    top = work[x].value_counts().head(15).index
    work = work[work[x].isin(top)]
    fig = px.box(work, x=x, y=y, color=x, color_discrete_sequence=COLOR_SEQ)
    return fig


def _db_violin(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna()
    top = work[x].value_counts().head(15).index
    work = work[work[x].isin(top)]
    fig = px.violin(work, x=x, y=y, color=x, color_discrete_sequence=COLOR_SEQ, box=True)
    return fig


def _db_density(df, c):
    x = c["x"]
    series = pd.to_numeric(df[x], errors="coerce").dropna()
    fig = go.Figure()
    fig.add_trace(go.Violin(y=series, box_visible=True, meanline_visible=True, name=x,
                            line_color="#7c9cff", fillcolor="rgba(124,156,255,0.3)"))
    fig.update_layout(xaxis_title=x)
    return fig


def _db_radar(df, c):
    categories_key = c.get("x") or c.get("categories")
    if not categories_key:
        fig = go.Figure()
        fig.update_layout(title="categories column required for radar")
        return fig
    num_cols = c.get("values") or [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])][:6]
    if not num_cols:
        fig = go.Figure()
        fig.update_layout(title="No numeric values for radar")
        return fig

    agg = df.groupby(categories_key)[num_cols].mean().head(10)
    categories = agg.index.tolist()
    fig = go.Figure()
    for col in num_cols:
        values = agg[col].tolist()
        values.append(values[0])
        cats = categories + [categories[0]]
        fig.add_trace(go.Scatterpolar(r=values, theta=cats, fill="toself", name=col))
    fig.update_layout(polar=dict(radialaxis=dict(visible=True)))
    return fig


def _db_waterfall(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().head(20)
    fig = go.Figure(go.Waterfall(
        name="Waterfall", orientation="v",
        measure=work.get("measure", ["relative"] * len(work)).tolist() if "measure" in work.columns else ["relative"] * len(work),
        x=work[x].tolist(), y=work[y].tolist(),
        textposition="outside", text=work[y].round(2).tolist(),
        connector={"line": {"color": "rgba(255,255,255,0.1)"}},
        increasing={"marker": {"color": "#56d9a1"}},
        decreasing={"marker": {"color": "#f87171"}},
        totals={"marker": {"color": "#7c9cff"}},
    ))
    return fig


def _db_funnel(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].dropna()
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().sort_values(y, ascending=False)
    fig = go.Figure(go.Funnel(y=work[x].tolist(), x=work[y].tolist(),
                               textinfo="value+percent initial",
                               marker_color=COLOR_SEQ[:len(work)]))
    return fig


def _db_gauge(df, c):
    value = c.get("value")
    if value is not None:
        val = float(value)
    else:
        col = c.get("y") or c.get("x")
        if col:
            val = pd.to_numeric(df[col], errors="coerce").mean()
        else:
            val = 0
    max_val = c.get("max", 100)
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta", value=val,
        gauge=dict(axis=dict(range=[0, max_val]),
                   bar=dict(color="#7c9cff"),
                   steps=[dict(range=[0, max_val * 0.5], color="rgba(86,217,161,0.15)"),
                          dict(range=[max_val * 0.5, max_val * 0.8, ], color="rgba(240,163,94,0.15)"),
                          dict(range=[max_val * 0.8, max_val], color="rgba(248,113,113,0.15)")]),
    ))
    return fig


def _db_kpi(df, c):
    col = c.get("y") or c.get("x")
    agg = c.get("agg", "mean")
    if col:
        val = pd.to_numeric(df[col], errors="coerce").agg(agg)
    else:
        val = len(df)
    fig = go.Figure()
    fig.update_layout(
        annotations=[dict(text=f"{val:,.2f}" if isinstance(val, float) else f"{val:,}",
                          xref="paper", yref="paper", x=0.5, y=0.5,
                          showarrow=False, font=dict(size=48, color="#e6edf3", family="Inter"))],
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def _db_data_table(df, c):
    cols = c.get("columns") or list(df.columns[:10])
    limit = c.get("limit", 50)
    work = df[cols].head(limit)
    header = dict(values=cols, fill_color="#161b22", font=dict(color="#c9d1d9", size=11), align="left")
    cell = dict(values=[work[col].tolist() for col in cols], fill_color="#0d1117",
                font=dict(color="#8b949e", size=10, family="JetBrains Mono"), align="left")
    fig = go.Figure(go.Table(header=header, cells=cell))
    return fig


def _db_corr_heatmap(df, c):
    num_cols = [col for col in df.columns if pd.api.types.is_numeric_dtype(df[col])]
    cols = c.get("columns") or num_cols[:10]
    if len(cols) < 2:
        fig = go.Figure()
        fig.update_layout(title="Need 2+ numeric columns")
        return fig
    corr = df[cols].corr()
    mask = np.triu(np.ones_like(corr, dtype=bool))
    z = corr.values.copy()
    z[mask] = np.nan
    fig = go.Figure(data=go.Heatmap(
        z=z, x=corr.columns.tolist(), y=corr.index.tolist(),
        colorscale="RdBu_r", zmin=-1, zmax=1,
        text=np.round(corr.values, 2), texttemplate="%{text}",
        textfont={"size": 9, "color": "#c9d1d9"},
    ))
    fig.update_layout(margin=dict(l=100, b=100))
    return fig


def _db_time_series(df, c):
    x, y = c["x"], c["y"]
    work = df[[x, y]].copy()
    parsed = _try_datetime(work[x])
    if parsed is not None:
        work[x] = parsed
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().sort_values(x)
    color = c.get("color")
    if color and color in df.columns:
        work = df[[x, y, color]].copy()
        if parsed is not None:
            work[x] = parsed
        work[y] = pd.to_numeric(work[y], errors="coerce")
        work = work.dropna().sort_values(x)
        fig = px.line(work, x=x, y=y, color=color, color_discrete_sequence=COLOR_SEQ)
    else:
        fig = px.line(work, x=x, y=y, color_discrete_sequence=["#7c9cff"])
    fig.update_traces(line=dict(width=2))
    if len(work) > 2:
        fig.add_trace(go.Scatter(x=work[x], y=work[y].rolling(min(10, len(work)//3+1)).mean(),
                                  mode="lines", name="Trend", line=dict(color="#f0a35e", dash="dash", width=1)))
    return fig


def _db_forecast(df, c):
    x, y = c["x"], c["y"]
    periods = c.get("periods", 10)
    work = df[[x, y]].copy()
    parsed = _try_datetime(work[x])
    if parsed is not None:
        work[x] = parsed
    work[y] = pd.to_numeric(work[y], errors="coerce")
    work = work.dropna().sort_values(x)
    if len(work) < 4:
        return _db_line(df, c)
    vals = work[y].values
    n = len(vals)
    avg_last = max(1, n // 3)
    trend = (vals[-1] - vals[-avg_last]) / avg_last
    forecast_vals = [vals[-1] + trend * (i + 1) for i in range(periods)]
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=work[x].tolist(), y=vals.tolist(), mode="lines", name="Actual",
                             line=dict(color="#7c9cff", width=2)))
    fig.add_trace(go.Scatter(y=forecast_vals, mode="lines", name="Forecast",
                             line=dict(color="#f0a35e", dash="dash", width=2)))
    return fig


def _db_distribution(df, c):
    x = c["x"]
    series = pd.to_numeric(df[x], errors="coerce").dropna()
    fig = go.Figure()
    fig.add_trace(go.Histogram(x=series, nbinsx=c.get("bins", 30), name="Histogram",
                                marker_color="rgba(124,156,255,0.6)"))
    fig.update_layout(barmode="overlay")
    return fig


def _db_outlier(df, c):
    x = c["x"]
    series = pd.to_numeric(df[x], errors="coerce").dropna()
    q1, q3 = series.quantile(0.25), series.quantile(0.75)
    iqr = q3 - q1
    lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr
    outliers = series[(series < lower) | (series > upper)]
    normal = series[(series >= lower) & (series <= upper)]
    fig = go.Figure()
    fig.add_trace(go.Box(y=normal.tolist(), name="Normal", marker_color="#7c9cff", boxpoints=False))
    if len(outliers) > 0:
        fig.add_trace(go.Scatter(y=outliers.tolist(), mode="markers", name="Outliers",
                                  marker=dict(color="#f87171", size=6)))
    return fig


def jsonable_fig(fig: go.Figure) -> dict:
    raw = fig.to_plotly_json()
    return json.loads(json.dumps(raw, default=_json_default))


def _json_default(obj: Any) -> Any:
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


# ---------------------------------------------------------------------------
# AI Dashboard Generator
# ---------------------------------------------------------------------------

def generate_ai_dashboard(df: pd.DataFrame, profile: dict) -> dict:
    numeric_cols = [c["name"] for c in profile["columns"] if c["type"] == "numeric"]
    cat_cols = [c["name"] for c in profile["columns"] if c["type"] == "categorical"]
    date_cols = [c["name"] for c in profile["columns"] if c["type"] == "datetime"]

    widgets = []
    y_pos = 0

    def add_widget(wtype, title, config, w=6, h=4):
        nonlocal y_pos
        col = 0 if len([x for x in widgets if x["y"] == y_pos]) == 0 else 6
        if len([x for x in widgets if x["y"] == y_pos]) >= 2:
            y_pos += 4
            col = 0
        widgets.append({
            "id": uuid.uuid4().hex[:8],
            "chart_type": wtype, "title": title, "config": config,
            "x": col, "y": y_pos, "w": w, "h": h,
        })
        if col == 6:
            y_pos += h

    # KPIs
    for num in numeric_cols[:4]:
        add_widget("kpi", f"Average {num}", {"x": num, "agg": "mean"}, w=3, h=3)

    y_pos = max(y_pos, 3) + 1

    # Time series
    if date_cols and numeric_cols:
        add_widget("time_series", f"{numeric_cols[0]} Over Time",
                   {"x": date_cols[0], "y": numeric_cols[0]}, w=12, h=5)
    elif numeric_cols:
        add_widget("histogram", f"Distribution of {numeric_cols[0]}",
                   {"x": numeric_cols[0]}, w=6, h=5)

    # Categorical vs Numeric
    if cat_cols and numeric_cols:
        add_widget("bar", f"{numeric_cols[0]} by {cat_cols[0]}",
                   {"x": cat_cols[0], "y": numeric_cols[0]}, w=6, h=5)
        if len(cat_cols) > 1:
            add_widget("pie", f"Distribution of {cat_cols[1]}",
                       {"x": cat_cols[1]}, w=6, h=5)
        elif len(numeric_cols) > 1:
            add_widget("scatter", f"{numeric_cols[1]} vs {numeric_cols[0]}",
                       {"x": numeric_cols[0], "y": numeric_cols[1]}, w=6, h=5)

    # Correlation
    if len(numeric_cols) >= 3:
        add_widget("correlation_heatmap", "Correlation Matrix",
                   {"columns": numeric_cols[:8]}, w=6, h=5)
    if len(numeric_cols) >= 2:
        add_widget("box", f"{numeric_cols[0]} Distribution by {cat_cols[0] if cat_cols else numeric_cols[1]}",
                   {"x": cat_cols[0] if cat_cols else numeric_cols[1], "y": numeric_cols[0]}, w=6, h=5)

    title = f"Auto-Generated Dashboard — {profile.get('n_rows', 0):,} rows"

    return {
        "title": title,
        "pages": [{
            "id": uuid.uuid4().hex[:8],
            "name": "Overview",
            "widgets": widgets,
        }],
        "filters": [],
        "settings": {
            "theme": "dark",
            "gridColumns": 12,
            "gridRowHeight": 60,
        },
    }


# ---------------------------------------------------------------------------
# Dashboard Templates
# ---------------------------------------------------------------------------

DASHBOARD_TEMPLATES = {
    "sales": {
        "title": "Sales Dashboard",
        "pages": [{"id": "p1", "name": "Sales Overview", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Total Revenue", "config": {"x": "Revenue", "agg": "sum"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "kpi", "title": "Total Orders", "config": {"x": "Orders", "agg": "count"}, "x": 3, "y": 0, "w": 3, "h": 3},
            {"id": "w3", "chart_type": "kpi", "title": "Avg Order Value", "config": {"x": "Revenue", "agg": "mean"}, "x": 6, "y": 0, "w": 3, "h": 3},
            {"id": "w4", "chart_type": "kpi", "title": "Profit Margin", "config": {"x": "Profit", "agg": "mean"}, "x": 9, "y": 0, "w": 3, "h": 3},
            {"id": "w5", "chart_type": "bar", "title": "Revenue by Category", "config": {"x": "Category", "y": "Revenue"}, "x": 0, "y": 4, "w": 6, "h": 5},
            {"id": "w6", "chart_type": "line", "title": "Revenue Trend", "config": {"x": "Date", "y": "Revenue"}, "x": 6, "y": 4, "w": 6, "h": 5},
            {"id": "w7", "chart_type": "pie", "title": "Sales by Region", "config": {"x": "Region"}, "x": 0, "y": 10, "w": 4, "h": 5},
            {"id": "w8", "chart_type": "heatmap", "title": "Correlation", "config": {}, "x": 4, "y": 10, "w": 4, "h": 5},
            {"id": "w9", "chart_type": "bar", "title": "Top Products", "config": {"x": "Product", "y": "Revenue"}, "x": 8, "y": 10, "w": 4, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "finance": {
        "title": "Financial Dashboard",
        "pages": [{"id": "p1", "name": "Finance Overview", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Revenue", "config": {"x": "Revenue", "agg": "sum"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "kpi", "title": "Expenses", "config": {"x": "Expenses", "agg": "sum"}, "x": 3, "y": 0, "w": 3, "h": 3},
            {"id": "w3", "chart_type": "kpi", "title": "Net Income", "config": {"x": "NetIncome", "agg": "sum"}, "x": 6, "y": 0, "w": 3, "h": 3},
            {"id": "w4", "chart_type": "kpi", "title": "Cash Flow", "config": {"x": "CashFlow", "agg": "sum"}, "x": 9, "y": 0, "w": 3, "h": 3},
            {"id": "w5", "chart_type": "area", "title": "Revenue vs Expenses", "config": {"x": "Date", "y": "Revenue"}, "x": 0, "y": 4, "w": 12, "h": 5},
            {"id": "w6", "chart_type": "waterfall", "title": "Income Waterfall", "config": {"x": "Category", "y": "Amount"}, "x": 0, "y": 10, "w": 6, "h": 5},
            {"id": "w7", "chart_type": "gauge", "title": "Budget Utilization", "config": {"y": "Utilization", "max": 100}, "x": 6, "y": 10, "w": 6, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "hr": {
        "title": "HR Dashboard",
        "pages": [{"id": "p1", "name": "HR Overview", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Total Employees", "config": {"x": "ID", "agg": "count"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "pie", "title": "Department Distribution", "config": {"x": "Department"}, "x": 0, "y": 4, "w": 6, "h": 5},
            {"id": "w3", "chart_type": "bar", "title": "Avg Salary by Dept", "config": {"x": "Department", "y": "Salary"}, "x": 6, "y": 4, "w": 6, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "healthcare": {
        "title": "Healthcare Dashboard",
        "pages": [{"id": "p1", "name": "Patient Overview", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Total Patients", "config": {"x": "ID", "agg": "count"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "bar", "title": "Diagnoses", "config": {"x": "Diagnosis", "y": "ID", "agg": "count"}, "x": 0, "y": 4, "w": 6, "h": 5},
            {"id": "w3", "chart_type": "histogram", "title": "Age Distribution", "config": {"x": "Age"}, "x": 6, "y": 4, "w": 6, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "retail": {
        "title": "Retail Dashboard",
        "pages": [{"id": "p1", "name": "Retail Overview", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Total Sales", "config": {"x": "Sales", "agg": "sum"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "kpi", "title": "Units Sold", "config": {"x": "Quantity", "agg": "sum"}, "x": 3, "y": 0, "w": 3, "h": 3},
            {"id": "w3", "chart_type": "bar", "title": "Sales by Product", "config": {"x": "Product", "y": "Sales"}, "x": 0, "y": 4, "w": 6, "h": 5},
            {"id": "w4", "chart_type": "donut", "title": "Sales Mix", "config": {"x": "Category"}, "x": 6, "y": 4, "w": 6, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "inventory": {
        "title": "Inventory Dashboard",
        "pages": [{"id": "p1", "name": "Inventory", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Total Items", "config": {"x": "Quantity", "agg": "sum"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "bar", "title": "Stock by Category", "config": {"x": "Category", "y": "Quantity"}, "x": 0, "y": 4, "w": 12, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "marketing": {
        "title": "Marketing Dashboard",
        "pages": [{"id": "p1", "name": "Marketing", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Total Campaigns", "config": {"x": "ID", "agg": "count"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "funnel", "title": "Conversion Funnel", "config": {"x": "Stage", "y": "Count"}, "x": 0, "y": 4, "w": 6, "h": 5},
            {"id": "w3", "chart_type": "bar", "title": "ROI by Channel", "config": {"x": "Channel", "y": "ROI"}, "x": 6, "y": 4, "w": 6, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "education": {
        "title": "Education Dashboard",
        "pages": [{"id": "p1", "name": "Education", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Students", "config": {"x": "ID", "agg": "count"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "bar", "title": "Grades by Subject", "config": {"x": "Subject", "y": "Score"}, "x": 0, "y": 4, "w": 6, "h": 5},
            {"id": "w3", "chart_type": "histogram", "title": "Score Distribution", "config": {"x": "Score"}, "x": 6, "y": 4, "w": 6, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "manufacturing": {
        "title": "Manufacturing Dashboard",
        "pages": [{"id": "p1", "name": "Production", "widgets": [
            {"id": "w1", "chart_type": "kpi", "title": "Units Produced", "config": {"x": "Quantity", "agg": "sum"}, "x": 0, "y": 0, "w": 3, "h": 3},
            {"id": "w2", "chart_type": "gauge", "title": "Efficiency", "config": {"y": "Efficiency", "max": 100}, "x": 0, "y": 4, "w": 6, "h": 5},
            {"id": "w3", "chart_type": "line", "title": "Production Trend", "config": {"x": "Date", "y": "Quantity"}, "x": 6, "y": 4, "w": 6, "h": 5},
        ]}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
    "general": {
        "title": "General Analytics Dashboard",
        "pages": [{"id": "p1", "name": "Overview", "widgets": []}],
        "settings": {"theme": "dark", "gridColumns": 12, "gridRowHeight": 60},
    },
}


# ---------------------------------------------------------------------------
# AI Insight per chart
# ---------------------------------------------------------------------------

def generate_chart_insight(df: pd.DataFrame, widget: dict) -> dict:
    chart_type = widget.get("chart_type", "bar")
    config = widget.get("config", {})
    x = config.get("x")
    y = config.get("y")

    summary = f"Chart type: {chart_type}"
    findings = []
    recommendations = []

    if x and x in df.columns:
        series = df[x]
        if pd.api.types.is_numeric_dtype(series):
            summary = f"Numeric column '{x}' — mean={series.mean():.2f}, std={series.std():.2f}"
            findings.append(f"Range: {series.min():.2f} to {series.max():.2f}")
            skew = series.skew()
            if abs(skew) > 1:
                findings.append(f"Distribution is skewed (skewness={skew:.2f})")
                recommendations.append("Consider log transformation for skewed data")
        else:
            vc = series.value_counts()
            summary = f"Categorical column '{x}' — {series.nunique()} unique values"
            findings.append(f"Most common: '{vc.index[0]}' ({vc.iloc[0]} occurrences)")
            if vc.iloc[0] / len(df) > 0.5:
                recommendations.append("Dominant category — consider grouping rare values")

    if y and y in df.columns:
        num_y = pd.to_numeric(df[y], errors="coerce")
        if num_y.notna().sum() > 0:
            findings.append(f"'{y}': mean={num_y.mean():.2f}, median={num_y.median():.2f}")

    if chart_type in ("scatter", "bubble") and x and y:
        corr = pd.to_numeric(df[x], errors="coerce").corr(pd.to_numeric(df[y], errors="coerce"))
        if pd.notna(corr):
            strength = "strong" if abs(corr) > 0.7 else "moderate" if abs(corr) > 0.3 else "weak"
            findings.append(f"Correlation between '{x}' and '{y}': {corr:.3f} ({strength})")

    confidence = min(95, 70 + len(findings) * 5)

    return {
        "summary": summary,
        "findings": findings,
        "recommendations": recommendations,
        "confidence": confidence,
    }
