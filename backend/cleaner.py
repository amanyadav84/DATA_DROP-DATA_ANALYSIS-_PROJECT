"""Advanced data cleaning — extends basic cleaning with professional workflows."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from processor import detect_column_type, _try_datetime


# ---------------------------------------------------------------------------
# Original clean actions (backward compatible)
# ---------------------------------------------------------------------------

def apply_clean(
    df: pd.DataFrame, action: str, params: dict[str, Any] | None = None
) -> pd.DataFrame:
    """Return a cleaned copy of *df* according to *action*."""
    params = params or {}
    out = df.copy()

    if action == "fill_nulls":
        strategy = params.get("strategy", "mean")  # mean | median | mode
        columns = params.get("columns")  # list or None = all

        if columns:
            target_cols = [c for c in columns if c in out.columns]
        else:
            target_cols = list(out.columns)

        for col in target_cols:
            col_type = detect_column_type(out[col])
            if col_type == "numeric":
                coerced = pd.to_numeric(out[col], errors="coerce")
                if strategy == "mean":
                    fill = coerced.mean()
                elif strategy == "median":
                    fill = coerced.median()
                else:
                    fill = coerced.mode().iloc[0] if not coerced.mode().empty else None
                if fill is not None and not pd.isna(fill):
                    out[col] = coerced.fillna(fill)
            elif col_type == "datetime":
                parsed = _try_datetime(out[col])
                if parsed is not None:
                    mode = parsed.mode()
                    if not mode.empty:
                        out[col] = parsed.fillna(mode.iloc[0])
            else:
                mode = out[col].mode(dropna=True)
                if not mode.empty:
                    out[col] = out[col].fillna(mode.iloc[0])

    elif action == "drop_duplicates":
        out = out.drop_duplicates().reset_index(drop=True)

    elif action == "strip_whitespace":
        for col in out.columns:
            if out[col].dtype == object:
                out[col] = out[col].apply(
                    lambda v: v.strip() if isinstance(v, str) else v
                )

    elif action == "drop_nulls":
        subset = params.get("columns")
        out = out.dropna(subset=subset if subset else None).reset_index(drop=True)

    elif action == "reset":
        # Handled at route level — return unchanged.
        pass

    return out


# ---------------------------------------------------------------------------
# Missing value analysis
# ---------------------------------------------------------------------------

def analyze_missing(df: pd.DataFrame) -> dict[str, Any]:
    """Analyze missing values per column with patterns and recommendations."""
    n_rows = len(df)
    cols_info = []
    for col in df.columns:
        series = df[col]
        null_count = int(series.isna().sum())
        if null_count == 0:
            continue
        null_pct = round(null_count / n_rows * 100, 2)
        col_type = detect_column_type(series)
        # Detect pattern
        pattern = "random"
        if series.isna().all():
            pattern = "all_missing"
        elif null_count == n_rows:
            pattern = "all_missing"
        else:
            # Check if missingness is concentrated
            non_null = series.dropna()
            if len(non_null) > 0 and series.head(max(1, null_count)).isna().all():
                pattern = "top_rows"
            elif len(non_null) > 0 and series.tail(max(1, null_count)).isna().all():
                pattern = "bottom_rows"

        # Recommend strategy
        if col_type == "numeric":
            if null_pct < 5:
                recommendation = "mean"
            elif null_pct < 20:
                recommendation = "median"
            else:
                recommendation = "knn"
        else:
            recommendation = "mode"

        cols_info.append({
            "column": col,
            "type": col_type,
            "null_count": null_count,
            "null_pct": null_pct,
            "pattern": pattern,
            "recommendation": recommendation,
        })

    total_missing = int(df.isna().sum().sum())
    total_cells = n_rows * len(df.columns)
    return {
        "total_missing": total_missing,
        "total_cells": total_cells,
        "total_missing_pct": round(total_missing / total_cells * 100, 2) if total_cells else 0,
        "columns": cols_info,
    }


# ---------------------------------------------------------------------------
# Advanced imputation
# ---------------------------------------------------------------------------

def impute_knn(df: pd.DataFrame, columns: list[str] | None = None, n_neighbors: int = 5) -> pd.DataFrame:
    """KNN imputation for numeric columns."""
    from sklearn.impute import KNNImputer
    out = df.copy()
    target_cols = columns or [c for c in out.columns if detect_column_type(out[c]) == "numeric"]
    if not target_cols:
        return out
    numeric_df = out[target_cols].apply(pd.to_numeric, errors="coerce")
    imputer = KNNImputer(n_neighbors=min(n_neighbors, len(numeric_df.dropna())))
    imputed = imputer.fit_transform(numeric_df)
    out[target_cols] = pd.DataFrame(imputed, columns=target_cols, index=out.index)
    return out


def impute_interpolation(df: pd.DataFrame, columns: list[str] | None = None,
                         method: str = "linear") -> pd.DataFrame:
    """Interpolation imputation (linear, time, polynomial)."""
    out = df.copy()
    target_cols = columns or [c for c in out.columns if detect_column_type(out[c]) == "numeric"]
    for col in target_cols:
        out[col] = pd.to_numeric(out[col], errors="coerce")
        out[col] = out[col].interpolate(method=method, limit_direction="both")
    return out


def impute_forward_fill(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Forward fill imputation."""
    out = df.copy()
    target_cols = columns or list(out.columns)
    out[target_cols] = out[target_cols].ffill()
    return out


def impute_backward_fill(df: pd.DataFrame, columns: list[str] | None = None) -> pd.DataFrame:
    """Backward fill imputation."""
    out = df.copy()
    target_cols = columns or list(out.columns)
    out[target_cols] = out[target_cols].bfill()
    return out


# ---------------------------------------------------------------------------
# Datatype conversion
# ---------------------------------------------------------------------------

def convert_datatypes(df: pd.DataFrame, conversions: dict[str, str]) -> pd.DataFrame:
    """Convert column datatypes. conversions = {col_name: target_type}"""
    out = df.copy()
    for col, target in conversions.items():
        if col not in out.columns:
            continue
        try:
            if target == "numeric":
                out[col] = pd.to_numeric(out[col], errors="coerce")
            elif target == "categorical":
                out[col] = out[col].astype(str)
            elif target == "datetime":
                out[col] = pd.to_datetime(out[col], errors="coerce")
            elif target == "boolean":
                mapping = {"true": True, "false": False, "yes": True, "no": False, "1": True, "0": False}
                out[col] = out[col].astype(str).str.lower().map(mapping)
            elif target == "integer":
                out[col] = pd.to_numeric(out[col], errors="coerce").astype("Int64")
        except Exception:
            pass
    return out


# ---------------------------------------------------------------------------
# Invalid value detection
# ---------------------------------------------------------------------------

def detect_invalid_values(df: pd.DataFrame) -> dict[str, Any]:
    """Detect invalid values: empty strings, whitespace-only, inf, sentinel values."""
    issues = []
    for col in df.columns:
        series = df[col]
        col_issues = []

        if series.dtype == object:
            # Empty strings
            empty_mask = series.astype(str).str.strip() == ""
            empty_count = int(empty_mask.sum())
            if empty_count > 0:
                col_issues.append({"type": "empty_string", "count": empty_count})

            # Whitespace-only
            ws_mask = (series.astype(str).str.strip() != series.astype(str)) & series.notna()
            ws_count = int(ws_mask.sum())
            if ws_count > 0:
                col_issues.append({"type": "whitespace_only", "count": ws_count})

        if pd.api.types.is_numeric_dtype(series):
            # Inf values
            inf_mask = np.isinf(series.astype(float))
            inf_count = int(inf_mask.sum())
            if inf_count > 0:
                col_issues.append({"type": "infinite", "count": inf_count})

            # Sentinel values (e.g., -999, -1)
            sentinel_mask = series.isin([-999, -9999, -1, 0])
            sentinel_count = int(sentinel_mask.sum())
            if sentinel_count > 0 and sentinel_count < len(series) * 0.1:
                col_issues.append({"type": "sentinel_values", "count": sentinel_count, "values": series[sentinel_mask].unique().tolist()[:5]})

        if col_issues:
            issues.append({"column": col, "issues": col_issues})

    return {"columns": issues, "total_issues": sum(len(i["issues"]) for i in issues)}


# ---------------------------------------------------------------------------
# Outlier treatment
# ---------------------------------------------------------------------------

def detect_outliers(df: pd.DataFrame) -> dict[str, Any]:
    """Detect outliers using IQR and Z-score methods."""
    results = []
    numeric_cols = [c for c in df.columns if detect_column_type(df[c]) == "numeric"]

    for col in numeric_cols:
        series = pd.to_numeric(df[col], errors="coerce").dropna()
        if len(series) < 10:
            continue

        q1 = float(series.quantile(0.25))
        q3 = float(series.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        iqr_outliers = int(((series < lower) | (series > upper)).sum())

        z_scores = np.abs(sp_stats.zscore(series))
        z_outliers = int((z_scores > 3).sum())

        if iqr_outliers > 0 or z_outliers > 0:
            results.append({
                "column": col,
                "iqr_outliers": iqr_outliers,
                "zscore_outliers": z_outliers,
                "lower_fence": round(lower, 4),
                "upper_fence": round(upper, 4),
                "min": round(float(series.min()), 4),
                "max": round(float(series.max()), 4),
            })

    return {"columns": results, "total_outliers": sum(r["iqr_outliers"] for r in results)}


def treat_outliers(df: pd.DataFrame, columns: list[str] | None = None,
                   method: str = "clip") -> pd.DataFrame:
    """Treat outliers: clip (winsorize), remove, or replace with NaN."""
    out = df.copy()
    target_cols = columns or [c for c in out.columns if detect_column_type(out[c]) == "numeric"]

    for col in target_cols:
        series = pd.to_numeric(out[col], errors="coerce")
        q1 = series.quantile(0.25)
        q3 = series.quantile(0.75)
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr

        if method == "clip":
            out[col] = series.clip(lower=lower, upper=upper)
        elif method == "remove":
            mask = (series >= lower) & (series <= upper) | series.isna()
            out = out[mask]
        elif method == "nan":
            mask = (series < lower) | (series > upper)
            out.loc[mask, col] = np.nan

    return out.reset_index(drop=True) if method == "remove" else out


# ---------------------------------------------------------------------------
# Text normalization
# ---------------------------------------------------------------------------

def normalize_text(df: pd.DataFrame, columns: list[str] | None = None,
                   operations: list[str] | None = None) -> pd.DataFrame:
    """Normalize text columns: lowercase, strip, remove special chars, etc."""
    out = df.copy()
    target_cols = columns or [c for c in out.columns if out[c].dtype == object]
    ops = operations or ["lowercase", "strip"]

    for col in target_cols:
        if col not in out.columns or out[col].dtype != object:
            continue
        series = out[col].astype(str)
        for op in ops:
            if op == "lowercase":
                series = series.str.lower()
            elif op == "uppercase":
                series = series.str.upper()
            elif op == "title":
                series = series.str.title()
            elif op == "strip":
                series = series.str.strip()
            elif op == "remove_special":
                series = series.str.replace(r"[^a-zA-Z0-9\s]", "", regex=True)
            elif op == "collapse_whitespace":
                series = series.str.replace(r"\s+", " ", regex=True).str.strip()
            elif op == "capitalize_first":
                series = series.str[0].str.upper() + series.str[1:]
        out[col] = series
    return out


# ---------------------------------------------------------------------------
# Duplicate analysis
# ---------------------------------------------------------------------------

def analyze_duplicates(df: pd.DataFrame) -> dict[str, Any]:
    """Analyze duplicate rows in detail."""
    dup_mask = df.duplicated(keep=False)
    dup_rows = df[dup_mask]
    n_dup = int(df.duplicated().sum())
    n_total = len(df)

    # Find which columns contribute most to duplicates
    col_dup_scores = []
    if n_dup > 0:
        for col in df.columns:
            partial_dups = int(df.duplicated(subset=[col]).sum())
            col_dup_scores.append({
                "column": col,
                "duplicate_contribution": round(partial_dups / n_total * 100, 2) if n_total else 0,
            })
        col_dup_scores.sort(key=lambda x: x["duplicate_contribution"], reverse=True)

    return {
        "total_rows": n_total,
        "duplicate_rows": n_dup,
        "duplicate_pct": round(n_dup / n_total * 100, 2) if n_total else 0,
        "unique_rows": n_total - n_dup,
        "column_contributions": col_dup_scores[:10],
    }


# ---------------------------------------------------------------------------
# Cleaning report
# ---------------------------------------------------------------------------

def generate_cleaning_report(df_original: pd.DataFrame, df_cleaned: pd.DataFrame) -> dict[str, Any]:
    """Generate before/after comparison report."""
    before = {
        "rows": len(df_original),
        "columns": len(df_original.columns),
        "missing": int(df_original.isna().sum().sum()),
        "duplicates": int(df_original.duplicated().sum()),
        "memory_kb": round(df_original.memory_usage(deep=True).sum() / 1024, 2),
    }
    after = {
        "rows": len(df_cleaned),
        "columns": len(df_cleaned.columns),
        "missing": int(df_cleaned.isna().sum().sum()),
        "duplicates": int(df_cleaned.duplicated().sum()),
        "memory_kb": round(df_cleaned.memory_usage(deep=True).sum() / 1024, 2),
    }

    changes = {}
    for key in before:
        diff = after[key] - before[key]
        if diff != 0:
            pct = round(diff / before[key] * 100, 2) if before[key] else 0
            changes[key] = {"before": before[key], "after": after[key], "change": diff, "change_pct": pct}

    return {"before": before, "after": after, "changes": changes}


# ---------------------------------------------------------------------------
# One-click cleaning
# ---------------------------------------------------------------------------

def auto_clean(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """Apply intelligent one-click cleaning. Returns cleaned df and list of actions taken."""
    out = df.copy()
    actions = []

    # 1. Strip whitespace from text columns
    text_cols = [c for c in out.columns if out[c].dtype == object]
    if text_cols:
        out = normalize_text(out, text_cols, ["strip", "collapse_whitespace"])
        actions.append({"action": "strip_whitespace", "columns": text_cols, "description": "Stripped whitespace from text columns"})

    # 2. Drop fully duplicate rows
    n_before = len(out)
    out = out.drop_duplicates().reset_index(drop=True)
    n_removed = n_before - len(out)
    if n_removed > 0:
        actions.append({"action": "drop_duplicates", "rows_removed": n_removed, "description": f"Removed {n_removed} duplicate rows"})

    # 3. Fill missing values intelligently
    for col in out.columns:
        null_pct = out[col].isna().mean()
        if null_pct == 0:
            continue
        col_type = detect_column_type(out[col])
        if col_type == "numeric":
            out[col] = pd.to_numeric(out[col], errors="coerce")
            fill = out[col].median()
            if not pd.isna(fill):
                out[col] = out[col].fillna(fill)
                actions.append({"action": "fill_nulls", "column": col, "strategy": "median", "filled": int(null_pct * len(out))})
        else:
            mode = out[col].mode(dropna=True)
            if not mode.empty:
                out[col] = out[col].fillna(mode.iloc[0])
                actions.append({"action": "fill_nulls", "column": col, "strategy": "mode", "filled": int(null_pct * len(out))})

    return out, actions
