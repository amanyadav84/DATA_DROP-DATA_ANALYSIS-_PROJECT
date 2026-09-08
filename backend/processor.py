"""Data processing: column-type detection, profiling, and summary statistics."""

from __future__ import annotations

import json
from typing import Any

import numpy as np
import pandas as pd


# ---------------------------------------------------------------------------
# Column-type detection
# ---------------------------------------------------------------------------

def _try_datetime(series: pd.Series) -> pd.Series | None:
    """Attempt to parse a series as datetime; return parsed series or None."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return series
    # Don't try to parse purely numeric columns as datetime.
    if pd.api.types.is_numeric_dtype(series):
        return None
    try:
        parsed = pd.to_datetime(series, errors="coerce")
    except (ValueError, TypeError):
        return None
    if parsed.isna().all():
        return None
    # Require at least 70 % successful parses to call it a datetime.
    if parsed.notna().mean() >= 0.7:
        return parsed
    return None


def detect_column_type(series: pd.Series) -> str:
    """Classify a column as numeric / categorical / datetime."""
    if pd.api.types.is_bool_dtype(series):
        return "categorical"
    if pd.api.types.is_numeric_dtype(series):
        return "numeric"
    if pd.api.types.is_datetime64_any_dtype(series):
        return "datetime"
    # Try datetime on object columns.
    parsed = _try_datetime(series)
    if parsed is not None:
        return "datetime"
    return "categorical"


def profile_dataframe(df: pd.DataFrame) -> dict[str, Any]:
    """Build a full profile of the dataframe: rows, columns, per-column stats."""
    n_rows, n_cols = df.shape
    total_nulls = int(df.isna().sum().sum())
    duplicate_rows = int(df.duplicated().sum())

    columns = []
    for col in df.columns:
        series = df[col]
        col_type = detect_column_type(series)
        null_count = int(series.isna().sum())
        unique_count = int(series.nunique(dropna=True))
        non_null = int(series.notna().sum())

        info: dict[str, Any] = {
            "name": str(col),
            "type": col_type,
            "null_count": null_count,
            "null_pct": round(null_count / n_rows * 100, 2) if n_rows else 0,
            "unique_count": unique_count,
            "non_null": non_null,
        }

        if col_type == "numeric":
            coerced = pd.to_numeric(series, errors="coerce")
            info["min"] = _safe_number(coerced.min())
            info["max"] = _safe_number(coerced.max())
            info["mean"] = _safe_number(coerced.mean())
            info["median"] = _safe_number(coerced.median())
            info["std"] = _safe_number(coerced.std())
            info["q25"] = _safe_number(coerced.quantile(0.25))
            info["q75"] = _safe_number(coerced.quantile(0.75))
        elif col_type == "datetime":
            parsed = _try_datetime(series)
            if parsed is None:
                parsed = series
            info["min"] = _safe_dt(parsed.min())
            info["max"] = _safe_dt(parsed.max())
        else:  # categorical
            vc = series.value_counts().head(10)
            info["top_values"] = [
                {"value": _safe_str(v), "count": int(c)} for v, c in vc.items()
            ]

        columns.append(info)

    return {
        "n_rows": int(n_rows),
        "n_cols": int(n_cols),
        "total_nulls": total_nulls,
        "duplicate_rows": duplicate_rows,
        "memory_kb": round(df.memory_usage(deep=True).sum() / 1024, 2),
        "columns": columns,
    }


def preview_dataframe(df: pd.DataFrame, n: int = 20) -> dict[str, Any]:
    """Return first *n* rows as JSON-serialisable dict with column order."""
    head = df.head(n)
    records = head.to_dict(orient="records")
    cleaned = [_clean_record(r) for r in records]
    return {
        "columns": [str(c) for c in df.columns],
        "rows": cleaned,
        "shown": len(cleaned),
        "total": int(len(df)),
    }


# ---------------------------------------------------------------------------
# Smart chart suggestions
# ---------------------------------------------------------------------------

def suggest_charts(df: pd.DataFrame, profile: dict) -> list[dict[str, Any]]:
    """Return a list of suggested charts based on column types."""
    suggestions: list[dict[str, Any]] = []
    cols = profile["columns"]
    numeric_cols = [c["name"] for c in cols if c["type"] == "numeric"]
    categorical_cols = [c["name"] for c in cols if c["type"] == "categorical"]
    datetime_cols = [c["name"] for c in cols if c["type"] == "datetime"]

    # 1. Histogram — single numeric
    for nc in numeric_cols[:4]:
        suggestions.append(
            {
                "id": f"hist_{nc}",
                "chart_type": "histogram",
                "title": f"Distribution of {nc}",
                "description": f"Histogram showing the distribution of {nc}.",
                "config": {"x": nc},
                "priority": 3,
            }
        )

    # 2. Scatter — two numeric
    if len(numeric_cols) >= 2:
        for i in range(min(len(numeric_cols) - 1, 3)):
            x, y = numeric_cols[i], numeric_cols[i + 1]
            suggestions.append(
                {
                    "id": f"scatter_{x}_{y}",
                    "chart_type": "scatter",
                    "title": f"{y} vs {x}",
                    "description": f"Scatter plot of {y} against {x}.",
                    "config": {"x": x, "y": y},
                    "priority": 1,
                }
            )

    # 3. Bar — categorical vs numeric
    if categorical_cols and numeric_cols:
        cat = categorical_cols[0]
        num = numeric_cols[0]
        suggestions.append(
            {
                "id": f"bar_{cat}_{num}",
                "chart_type": "bar",
                "title": f"{num} by {cat}",
                "description": f"Bar chart of mean {num} grouped by {cat}.",
                "config": {"x": cat, "y": num, "agg": "mean"},
                "priority": 2,
            }
        )

    # 4. Line — datetime vs numeric
    if datetime_cols and numeric_cols:
        dt = datetime_cols[0]
        num = numeric_cols[0]
        suggestions.append(
            {
                "id": f"line_{dt}_{num}",
                "chart_type": "line",
                "title": f"{num} over time",
                "description": f"Line chart of {num} over {dt}.",
                "config": {"x": dt, "y": num},
                "priority": 1,
            }
        )

    # 5. Box — categorical vs numeric (bonus)
    if categorical_cols and numeric_cols and len(numeric_cols) >= 1:
        cat = categorical_cols[0] if len(categorical_cols) > 1 else categorical_cols[0]
        num = numeric_cols[0]
        suggestions.append(
            {
                "id": f"box_{cat}_{num}",
                "chart_type": "box",
                "title": f"{num} distribution by {cat}",
                "description": f"Box plot of {num} across {cat} groups.",
                "config": {"x": cat, "y": num},
                "priority": 4,
            }
        )

    suggestions.sort(key=lambda s: s["priority"])
    return suggestions


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _safe_number(val: Any) -> float | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        if np.isinf(val):
            return None
        return round(float(val), 4)
    except (TypeError, ValueError):
        return None


def _safe_dt(val: Any) -> str | None:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return None
    try:
        if pd.isna(val):
            return None
        return pd.Timestamp(val).isoformat()
    except (TypeError, ValueError):
        return None


def _safe_str(val: Any) -> str:
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return ""
    if isinstance(val, (np.integer, np.floating)):
        return val.item()
    if isinstance(val, np.bool_):
        return bool(val)
    return str(val)


def _clean_record(record: dict) -> dict:
    cleaned = {}
    for k, v in record.items():
        if v is None or (isinstance(v, float) and np.isnan(v)):
            cleaned[str(k)] = None
        elif isinstance(v, (np.integer,)):
            cleaned[str(k)] = int(v)
        elif isinstance(v, (np.floating,)):
            cleaned[str(k)] = round(float(v), 6)
        elif isinstance(v, (np.bool_,)):
            cleaned[str(k)] = bool(v)
        elif isinstance(v, pd.Timestamp):
            cleaned[str(k)] = v.isoformat()
        else:
            cleaned[str(k)] = v
    return cleaned
