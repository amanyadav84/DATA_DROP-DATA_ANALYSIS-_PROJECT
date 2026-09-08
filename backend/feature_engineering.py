"""Feature Engineering Studio — encoding, scaling, binning, transforms, feature creation."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from sklearn.preprocessing import (
    LabelEncoder, OneHotEncoder, OrdinalEncoder,
    StandardScaler, MinMaxScaler, RobustScaler, MaxAbsScaler,
    PolynomialFeatures, PowerTransformer, QuantileTransformer,
)

from processor import detect_column_type


# ---------------------------------------------------------------------------
# Encoding
# ---------------------------------------------------------------------------

def encode_onehot(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """One-hot encode specified columns."""
    return pd.get_dummies(df, columns=columns, drop_first=False, dtype=int)


def encode_label(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Label encode specified columns."""
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        le = LabelEncoder()
        non_null = out[col].dropna()
        if len(non_null) > 0:
            out.loc[non_null.index, col] = le.fit_transform(non_null.astype(str))
    return out


def encode_ordinal(df: pd.DataFrame, columns: list[str], order: dict[str, list[str]] | None = None) -> pd.DataFrame:
    """Ordinal encode specified columns."""
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        if order and col in order:
            cats = order[col]
        else:
            cats = sorted(out[col].dropna().astype(str).unique().tolist())
        mapping = {v: i for i, v in enumerate(cats)}
        out[col] = out[col].astype(str).map(mapping)
    return out


def encode_frequency(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Frequency encode — replace each value with its frequency."""
    out = df.copy()
    for col in columns:
        if col not in out.columns:
            continue
        freq = out[col].value_counts(normalize=True)
        out[col] = out[col].map(freq)
    return out


def encode_target(df: pd.DataFrame, columns: list[str], target: str) -> pd.DataFrame:
    """Target encode — replace each value with the mean of the target."""
    out = df.copy()
    if target not in out.columns:
        return out
    target_num = pd.to_numeric(out[target], errors="coerce")
    for col in columns:
        if col not in out.columns:
            continue
        means = out.groupby(col)[target].apply(lambda x: pd.to_numeric(x, errors="coerce").mean())
        out[col] = out[col].map(means)
    return out


# ---------------------------------------------------------------------------
# Scaling
# ---------------------------------------------------------------------------

def scale_standard(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """StandardScaler: zero mean, unit variance."""
    out = df.copy()
    cols = columns or [c for c in out.columns if detect_column_type(out[c]) == "numeric"]
    if not cols:
        return out
    scaler = StandardScaler()
    out[cols] = scaler.fit_transform(out[cols].apply(pd.to_numeric, errors="coerce").fillna(0))
    return out


def scale_minmax(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """MinMaxScaler: scale to [0, 1]."""
    out = df.copy()
    cols = columns or [c for c in out.columns if detect_column_type(out[c]) == "numeric"]
    if not cols:
        return out
    scaler = MinMaxScaler()
    out[cols] = scaler.fit_transform(out[cols].apply(pd.to_numeric, errors="coerce").fillna(0))
    return out


def scale_robust(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """RobustScaler: scale using median and IQR (robust to outliers)."""
    out = df.copy()
    cols = columns or [c for c in out.columns if detect_column_type(out[c]) == "numeric"]
    if not cols:
        return out
    scaler = RobustScaler()
    out[cols] = scaler.fit_transform(out[cols].apply(pd.to_numeric, errors="coerce").fillna(0))
    return out


# ---------------------------------------------------------------------------
# Transforms
# ---------------------------------------------------------------------------

def transform_log(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Log transform (log1p for safety)."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").apply(lambda x: np.log1p(max(0, x)) if pd.notna(x) else x)
    return out


def transform_sqrt(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Square root transform."""
    out = df.copy()
    for col in columns:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce").apply(lambda x: np.sqrt(max(0, x)) if pd.notna(x) else x)
    return out


def transform_power(df: pd.DataFrame, columns: list[str], method: str = "yeojohnson") -> pd.DataFrame:
    """Power transform (yeojohnson or boxcox)."""
    out = df.copy()
    numeric_cols = [c for c in columns if c in out.columns]
    if not numeric_cols:
        return out
    for col in numeric_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
    clean = out[numeric_cols].fillna(0)
    pt = PowerTransformer(method=method)
    try:
        out[numeric_cols] = pt.fit_transform(clean)
    except Exception:
        pass
    return out


# ---------------------------------------------------------------------------
# Feature creation
# ---------------------------------------------------------------------------

def create_date_features(df: pd.DataFrame, date_column: str) -> pd.DataFrame:
    """Extract date features: year, month, day, dayofweek, quarter, is_weekend."""
    out = df.copy()
    if date_column not in out.columns:
        return out
    parsed = pd.to_datetime(out[date_column], errors="coerce")
    out[f"{date_column}_year"] = parsed.dt.year
    out[f"{date_column}_month"] = parsed.dt.month
    out[f"{date_column}_day"] = parsed.dt.day
    out[f"{date_column}_dayofweek"] = parsed.dt.dayofweek
    out[f"{date_column}_quarter"] = parsed.dt.quarter
    out[f"{date_column}_is_weekend"] = parsed.dt.dayofweek.isin([5, 6]).astype(int)
    out[f"{date_column}_week"] = parsed.dt.isocalendar().week.astype(int)
    return out


def create_polynomial(df: pd.DataFrame, columns: list[str], degree: int = 2) -> pd.DataFrame:
    """Create polynomial features."""
    out = df.copy()
    cols = [c for c in columns if c in out.columns]
    if not cols:
        return out
    poly = PolynomialFeatures(degree=degree, include_bias=False, interaction_only=False)
    poly_data = poly.fit_transform(out[cols].fillna(0))
    poly_names = poly.get_feature_names_out(cols)
    new_cols = [n for n in poly_names if n not in out.columns]
    if new_cols:
        poly_df = pd.DataFrame(poly_data, columns=poly_names, index=out.index)
        out[new_cols] = poly_df[new_cols]
    return out


def create_interactions(df: pd.DataFrame, columns: list[str]) -> pd.DataFrame:
    """Create pairwise interaction features (multiply)."""
    out = df.copy()
    cols = [c for c in columns if c in out.columns and detect_column_type(out[c]) == "numeric"]
    for i in range(len(cols)):
        for j in range(i + 1, len(cols)):
            out[f"{cols[i]}_x_{cols[j]}"] = pd.to_numeric(out[cols[i]], errors="coerce") * pd.to_numeric(out[cols[j]], errors="coerce")
    return out


def create_binning(df: pd.DataFrame, column: str, bins: int = 5, labels: list[str] | None = None) -> pd.DataFrame:
    """Create binned categories from numeric column."""
    out = df.copy()
    if column not in out.columns:
        return out
    out[f"{column}_binned"] = pd.cut(
        pd.to_numeric(out[column], errors="coerce"),
        bins=bins,
        labels=labels or [f"Bin_{i+1}" for i in range(bins)],
    )
    return out


def create_missing_indicator(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Create boolean indicator columns for missing values."""
    out = df.copy()
    target_cols = columns or [c for c in out.columns if out[c].isna().any()]
    for col in target_cols:
        if col in out.columns and out[col].isna().any():
            out[f"{col}_is_missing"] = out[col].isna().astype(int)
    return out


# ---------------------------------------------------------------------------
# Feature recommendations
# ---------------------------------------------------------------------------

def recommend_features(df: pd.DataFrame, profile: dict) -> list[dict[str, Any]]:
    """Recommend feature engineering operations based on data analysis."""
    recommendations = []
    numeric_cols = [c["name"] for c in profile["columns"] if c["type"] == "numeric"]
    cat_cols = [c["name"] for c in profile["columns"] if c["type"] == "categorical"]
    date_cols = [c["name"] for c in profile["columns"] if c["type"] == "datetime"]

    # Encoding recommendations
    for col in cat_cols:
        nunique = df[col].nunique()
        if nunique <= 10:
            recommendations.append({
                "operation": "onehot",
                "column": col,
                "reason": f"{col} has {nunique} unique values — ideal for one-hot encoding",
                "priority": "medium",
            })
        elif nunique <= 50:
            recommendations.append({
                "operation": "label",
                "column": col,
                "reason": f"{col} has {nunique} unique values — use label encoding",
                "priority": "low",
            })

    # Scaling recommendations
    if numeric_cols:
        recommendations.append({
            "operation": "standardize",
            "columns": numeric_cols[:5],
            "reason": "Standardize numeric features for ML algorithms",
            "priority": "medium",
        })

    # Date feature extraction
    for col in date_cols:
        recommendations.append({
            "operation": "date_features",
            "column": col,
            "reason": f"Extract year, month, day, quarter from {col}",
            "priority": "high",
        })

    # Missing indicator
    for col in numeric_cols:
        if df[col].isna().any():
            recommendations.append({
                "operation": "missing_indicator",
                "column": col,
                "reason": f"{col} has missing values — create indicator feature",
                "priority": "low",
            })

    # Binning
    for col in numeric_cols[:3]:
        recommendations.append({
            "operation": "binning",
            "column": col,
            "reason": f"Create age/value groups from {col}",
            "priority": "low",
        })

    return recommendations
