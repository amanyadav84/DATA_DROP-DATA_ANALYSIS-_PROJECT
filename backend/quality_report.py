"""Data quality analysis and reporting."""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd

from processor import detect_column_type, _try_datetime


# ---------------------------------------------------------------------------
# Invalid data detection
# ---------------------------------------------------------------------------

def detect_empty_strings(series: pd.Series) -> int:
    """Count empty string values."""
    if series.dtype != object:
        return 0
    return int((series == "").sum())


def detect_whitespace_only(series: pd.Series) -> int:
    """Count cells with only whitespace (vectorized)."""
    if series.dtype != object:
        return 0
    mask = series.notna() & (series.astype(str).str.strip() == "") & (series.astype(str) != "")
    return int(mask.sum())


def detect_invalid_numbers(series: pd.Series) -> int:
    """Count values that cannot be coerced to numeric in a supposedly numeric column."""
    if not (series.dtype == object or series.dtype.name.startswith("float") or series.dtype.name.startswith("int")):
        return 0
    coerced = pd.to_numeric(series, errors="coerce")
    return int((series.notna() & coerced.isna()).sum())


def detect_invalid_dates(series: pd.Series) -> int:
    """Count values that cannot be parsed as dates in a datetime column."""
    if pd.api.types.is_datetime64_any_dtype(series):
        return 0  # Already parsed
    if series.dtype != object:
        return 0
    parsed = pd.to_datetime(series, errors="coerce")
    return int((series.notna() & parsed.isna()).sum())


def detect_invalid_emails(series: pd.Series) -> int:
    """Count invalid email addresses (vectorized)."""
    if series.dtype != object:
        return 0
    email_pattern = r"^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$"
    str_series = series.astype(str).str.strip()
    non_empty = series.notna() & (str_series != "") & (str_series != "nan")
    valid_format = str_series.str.match(email_pattern, na=False)
    return int((non_empty & ~valid_format).sum())


def detect_invalid_urls(series: pd.Series) -> int:
    """Count invalid URLs (vectorized)."""
    if series.dtype != object:
        return 0
    url_pattern = r"^https?://.+"
    str_series = series.astype(str).str.strip()
    non_empty = series.notna() & (str_series != "") & (str_series != "nan")
    valid_format = str_series.str.match(url_pattern, na=False, flags=re.IGNORECASE)
    return int((non_empty & ~valid_format).sum())


def detect_invalid_phones(series: pd.Series) -> int:
    """Count invalid phone numbers (vectorized)."""
    if series.dtype != object:
        return 0
    phone_pattern = r"^[\d\s\-\+()]+$"
    str_series = series.astype(str).str.strip()
    non_empty = series.notna() & (str_series != "") & (str_series != "nan")
    valid_format = str_series.str.match(phone_pattern, na=False)
    return int((non_empty & ~valid_format).sum())


def detect_negative_values(series: pd.Series) -> int:
    """Count negative values in supposedly non-negative numeric columns."""
    if not (pd.api.types.is_numeric_dtype(series)):
        return 0
    return int((series < 0).sum())


# ---------------------------------------------------------------------------
# Column-level analysis
# ---------------------------------------------------------------------------

def analyze_column_quality(series: pd.Series, col_name: str, col_type: str, n_rows: int) -> dict[str, Any]:
    """Comprehensive quality analysis for a single column."""
    null_count = int(series.isna().sum())
    null_pct = round(null_count / n_rows * 100, 2) if n_rows else 0
    
    unique_count = int(series.nunique(dropna=True))
    unique_pct = round(unique_count / n_rows * 100, 2) if n_rows else 0
    
    non_null = int(series.notna().sum())
    
    # Detect constant/near-constant columns
    is_constant = unique_count <= 1
    is_near_constant = unique_count <= max(2, int(n_rows * 0.01))  # <= 1% unique
    
    # High cardinality warning
    is_high_cardinality = unique_count > int(n_rows * 0.5)  # > 50% unique
    
    invalid_count = 0
    invalid_reason = None
    
    # Detect various invalid values based on column type
    if col_type == "numeric":
        invalid_count = detect_invalid_numbers(series)
        if invalid_count > 0:
            invalid_reason = "invalid_numbers"
    elif col_type == "datetime":
        invalid_count = detect_invalid_dates(series)
        if invalid_count > 0:
            invalid_reason = "invalid_dates"
    
    # Check for empty strings / whitespace
    empty_count = detect_empty_strings(series)
    whitespace_count = detect_whitespace_only(series)
    
    # Negative values in numeric columns
    negative_count = detect_negative_values(series) if col_type == "numeric" else 0
    
    # Suggested datatype and mixed type detection
    suggested_datatype, is_mixed_type = _detect_suggested_datatype(series, col_type)
    
    return {
        "name": col_name,
        "type": col_type,
        "null_count": null_count,
        "null_pct": null_pct,
        "unique_count": unique_count,
        "unique_pct": unique_pct,
        "is_constant": is_constant,
        "is_near_constant": is_near_constant,
        "is_high_cardinality": is_high_cardinality,
        "invalid_count": invalid_count,
        "invalid_reason": invalid_reason,
        "empty_count": empty_count,
        "whitespace_count": whitespace_count,
        "negative_count": negative_count,
        "suggested_datatype": suggested_datatype,
        "is_mixed_type": is_mixed_type,
        "quality_score": _calculate_column_quality_score(
            null_count, unique_count, invalid_count, empty_count, whitespace_count, n_rows
        ),
    }


def _calculate_column_quality_score(null_count: int, unique_count: int, invalid_count: int, 
                                     empty_count: int, whitespace_count: int, n_rows: int) -> float:
    """Calculate 0-100 quality score for a column."""
    if n_rows == 0:
        return 100.0
    
    # Start with 100
    score = 100.0
    
    # Deduct for nulls (up to -30)
    null_pct = null_count / n_rows * 100
    score -= min(30, null_pct)
    
    # Deduct for invalid values (up to -20)
    invalid_pct = (invalid_count + empty_count + whitespace_count) / n_rows * 100
    score -= min(20, invalid_pct)
    
    # Deduct for extreme cardinality (up to -15)
    if unique_count == 0 or unique_count == 1:
        score -= 15  # Constant column
    elif unique_count > n_rows * 0.8:
        score -= 10  # Too many unique values
    
    return max(0, round(score, 1))


def _detect_suggested_datatype(series: pd.Series, current_type: str) -> tuple[str, bool]:
    """Detect suggested datatype and whether column has mixed types."""
    non_null = series.dropna()
    if non_null.empty:
        return current_type, False

    is_mixed = False
    suggested = current_type

    if series.dtype == object:
        # Check for mixed types in object columns
        type_counts = non_null.map(type).value_counts()
        if len(type_counts) > 1:
            is_mixed = True

        # Try to suggest a better type
        str_vals = non_null.astype(str)

        # Try numeric
        coerced_numeric = pd.to_numeric(non_null, errors="coerce")
        numeric_success = coerced_numeric.notna().sum() / len(non_null) if len(non_null) > 0 else 0
        if numeric_success >= 0.9:
            suggested = "numeric"
            return suggested, is_mixed

        # Try datetime
        coerced_dt = pd.to_datetime(non_null, errors="coerce", format="mixed")
        dt_success = coerced_dt.notna().sum() / len(non_null) if len(non_null) > 0 else 0
        if dt_success >= 0.9:
            suggested = "datetime"
            return suggested, is_mixed

        # Try boolean
        unique_str = set(str_vals.str.lower().unique())
        bool_values = {"true", "false", "1", "0", "yes", "no"}
        if unique_str.issubset(bool_values):
            suggested = "boolean"
            return suggested, is_mixed

    elif pd.api.types.is_numeric_dtype(series):
        # Check if all values are actually integers
        if not series.dropna().empty:
            float_vals = series.dropna()
            if (float_vals == float_vals.astype(int)).all():
                suggested = "integer"

    return suggested, is_mixed


# ---------------------------------------------------------------------------
# Dataset-level analysis
# ---------------------------------------------------------------------------

def analyze_dataset_quality(df: pd.DataFrame, profile: dict) -> dict[str, Any]:
    """Comprehensive quality report for entire dataset."""
    n_rows, n_cols = df.shape
    
    # Count column types
    numeric_cols = sum(1 for c in profile["columns"] if c["type"] == "numeric")
    categorical_cols = sum(1 for c in profile["columns"] if c["type"] == "categorical")
    datetime_cols = sum(1 for c in profile["columns"] if c["type"] == "datetime")
    
    # Detect boolean columns (from actual DataFrame dtypes)
    boolean_cols = sum(1 for col in df.columns if df[col].dtype == bool)
    
    # Analyze each column
    column_analyses = []
    for col_info in profile["columns"]:
        series = df[col_info["name"]]
        analysis = analyze_column_quality(series, col_info["name"], col_info["type"], n_rows)
        column_analyses.append(analysis)
    
    # Missing value analysis
    total_cells = n_rows * n_cols
    total_nulls = profile["total_nulls"]
    null_pct_overall = round(total_nulls / total_cells * 100, 2) if total_cells else 0
    
    # Duplicate analysis
    duplicate_rows = profile["duplicate_rows"]
    duplicate_pct = round(duplicate_rows / n_rows * 100, 2) if n_rows else 0
    
    # Duplicate columns (exact duplicates)
    duplicate_cols = detect_duplicate_columns(df)
    
    # Invalid data totals
    total_invalid = sum(ca["invalid_count"] for ca in column_analyses)
    total_empty = sum(ca["empty_count"] for ca in column_analyses)
    total_whitespace = sum(ca["whitespace_count"] for ca in column_analyses)
    total_negative = sum(ca["negative_count"] for ca in column_analyses)
    
    # Constant and high-cardinality columns
    constant_cols = [ca for ca in column_analyses if ca["is_constant"]]
    near_constant_cols = [ca for ca in column_analyses if ca["is_near_constant"] and not ca["is_constant"]]
    high_cardinality_cols = [ca for ca in column_analyses if ca["is_high_cardinality"]]
    
    # Memory usage
    memory_mb = profile["memory_kb"] / 1024
    
    # Calculate overall health score
    health_score = _calculate_overall_health_score(
        n_rows, n_cols, total_nulls, total_cells,
        duplicate_rows, total_invalid, total_empty, total_whitespace,
        len(constant_cols), len(high_cardinality_cols)
    )
    
    # Generate recommendations
    recommendations = generate_recommendations(
        column_analyses, duplicate_cols, constant_cols, near_constant_cols,
        high_cardinality_cols, health_score, n_rows, df, total_negative
    )
    
    return {
        "dataset_overview": {
            "total_rows": int(n_rows),
            "total_columns": int(n_cols),
            "memory_mb": round(memory_mb, 2),
            "dataset_size": get_human_readable_size(profile["memory_kb"] * 1024),
            "numeric_columns": int(numeric_cols),
            "categorical_columns": int(categorical_cols),
            "datetime_columns": int(datetime_cols),
            "boolean_columns": int(boolean_cols),
        },
        "missing_value_analysis": {
            "total_nulls": int(total_nulls),
            "overall_null_pct": null_pct_overall,
            "columns": [
                {
                    "name": ca["name"],
                    "null_count": ca["null_count"],
                    "null_pct": ca["null_pct"],
                }
                for ca in sorted(column_analyses, key=lambda x: x["null_count"], reverse=True)
                if ca["null_count"] > 0
            ],
        },
        "duplicate_analysis": {
            "duplicate_rows": int(duplicate_rows),
            "duplicate_pct": duplicate_pct,
            "duplicate_columns": duplicate_cols,
        },
        "datatype_analysis": {
            "columns": [
                {
                    "name": ca["name"],
                    "detected_type": ca["type"],
                    "suggested_datatype": ca["suggested_datatype"],
                    "is_mixed_type": ca["is_mixed_type"],
                    "invalid_count": ca["invalid_count"],
                    "invalid_reason": ca["invalid_reason"],
                }
                for ca in column_analyses
                if ca["invalid_count"] > 0 or ca["type"] in ["numeric", "datetime"] or ca["is_mixed_type"]
            ],
        },
        "unique_value_analysis": {
            "constant_columns": [
                {
                    "name": ca["name"],
                    "type": ca["type"],
                    "unique_count": ca["unique_count"],
                }
                for ca in constant_cols
            ],
            "near_constant_columns": [
                {
                    "name": ca["name"],
                    "type": ca["type"],
                    "unique_count": ca["unique_count"],
                    "unique_pct": ca["unique_pct"],
                }
                for ca in near_constant_cols
            ],
            "high_cardinality_columns": [
                {
                    "name": ca["name"],
                    "type": ca["type"],
                    "unique_count": ca["unique_count"],
                    "unique_pct": ca["unique_pct"],
                }
                for ca in high_cardinality_cols
            ],
            "columns": [
                {
                    "name": ca["name"],
                    "type": ca["type"],
                    "unique_count": ca["unique_count"],
                    "unique_pct": ca["unique_pct"],
                    "quality_score": ca["quality_score"],
                }
                for ca in sorted(column_analyses, key=lambda x: x["quality_score"])
            ],
        },
        "invalid_data_detection": {
            "total_invalid": int(total_invalid),
            "total_empty": int(total_empty),
            "total_whitespace": int(total_whitespace),
            "total_negative": int(total_negative),
            "columns": [
                {
                    "name": ca["name"],
                    "type": ca["type"],
                    "invalid_count": ca["invalid_count"],
                    "empty_count": ca["empty_count"],
                    "whitespace_count": ca["whitespace_count"],
                    "negative_count": ca["negative_count"],
                }
                for ca in column_analyses
                if ca["invalid_count"] > 0 or ca["empty_count"] > 0 or ca["whitespace_count"] > 0 or ca["negative_count"] > 0
            ],
        },
        "health_score": {
            "score": round(health_score, 1),
            "status": get_health_status(health_score),
            "breakdown": {
                "completeness": round(_calculate_completeness_score(total_nulls, total_cells), 1),
                "validity": round(_calculate_validity_score(total_invalid, total_empty, total_whitespace, total_cells), 1),
                "consistency": round(_calculate_consistency_score(duplicate_rows, len(constant_cols), n_rows), 1),
                "accuracy": round(_calculate_accuracy_score(column_analyses), 1),
            },
        },
        "recommendations": recommendations,
    }


def detect_duplicate_columns(df: pd.DataFrame) -> list[dict]:
    """Find duplicate columns (completely identical)."""
    duplicates = []
    cols = df.columns.tolist()
    seen_hashes = {}
    
    for col in cols:
        col_hash = hash(tuple(df[col].astype(str).values))
        if col_hash in seen_hashes:
            duplicates.append({
                "column1": seen_hashes[col_hash],
                "column2": col,
            })
        else:
            seen_hashes[col_hash] = col
    
    return duplicates


def _calculate_overall_health_score(n_rows: int, n_cols: int, total_nulls: int, total_cells: int,
                                     duplicate_rows: int, total_invalid: int, total_empty: int,
                                     total_whitespace: int, constant_col_count: int, 
                                     high_cardinality_count: int) -> float:
    """Calculate 0-100 overall dataset health score."""
    if total_cells == 0 or n_rows == 0:
        return 100.0
    
    score = 100.0
    
    # Completeness (up to -30): measure nulls
    null_pct = total_nulls / total_cells * 100
    score -= min(30, null_pct * 0.3)
    
    # Validity (up to -20): measure invalid/empty/whitespace
    invalid_total = total_invalid + total_empty + total_whitespace
    invalid_pct = invalid_total / total_cells * 100
    score -= min(20, invalid_pct * 0.5)
    
    # Consistency (up to -15): measure duplicates and constant columns
    dup_pct = duplicate_rows / n_rows * 100 if n_rows else 0
    score -= min(15, dup_pct * 0.2 + constant_col_count * 2)
    
    # Uniqueness (up to -10): measure high-cardinality columns
    score -= min(10, high_cardinality_count * 1.5)
    
    return max(0, round(score, 1))


def _calculate_completeness_score(total_nulls: int, total_cells: int) -> float:
    """Score for completeness (0-100, higher is better)."""
    if total_cells == 0:
        return 100.0
    null_pct = total_nulls / total_cells * 100
    return max(0, 100 - null_pct)


def _calculate_validity_score(total_invalid: int, total_empty: int, total_whitespace: int, total_cells: int) -> float:
    """Score for data validity (0-100, higher is better)."""
    if total_cells == 0:
        return 100.0
    invalid_total = total_invalid + total_empty + total_whitespace
    invalid_pct = invalid_total / total_cells * 100
    return max(0, 100 - invalid_pct * 2)


def _calculate_consistency_score(duplicate_rows: int, constant_cols: int, n_rows: int) -> float:
    """Score for consistency (0-100, higher is better)."""
    if n_rows == 0:
        return 100.0
    dup_pct = duplicate_rows / n_rows * 100
    consistency = max(0, 100 - dup_pct - constant_cols * 3)
    return min(100, consistency)


def _calculate_accuracy_score(column_analyses: list[dict]) -> float:
    """Average quality score across all columns."""
    if not column_analyses:
        return 100.0
    total_score = sum(ca["quality_score"] for ca in column_analyses)
    return total_score / len(column_analyses)


def get_health_status(score: float) -> str:
    """Convert health score to status string."""
    if score >= 90:
        return "Excellent"
    elif score >= 75:
        return "Good"
    elif score >= 50:
        return "Average"
    else:
        return "Poor"


def get_human_readable_size(bytes_size: float) -> str:
    """Convert bytes to human readable format."""
    for unit in ["B", "KB", "MB", "GB"]:
        if bytes_size < 1024:
            return f"{bytes_size:.1f} {unit}"
        bytes_size /= 1024
    return f"{bytes_size:.1f} TB"


# ---------------------------------------------------------------------------
# Recommendations
# ---------------------------------------------------------------------------

def generate_recommendations(column_analyses: list[dict], duplicate_cols: list[dict],
                           constant_cols: list[dict], near_constant_cols: list[dict],
                           high_cardinality_cols: list[dict], health_score: float,
                           n_rows: int, df: pd.DataFrame, total_negative: int = 0) -> list[dict[str, Any]]:
    """Generate actionable recommendations based on quality analysis."""
    recommendations = []
    
    # Recommendation 1: Handle missing values
    cols_with_nulls = [ca for ca in column_analyses if ca["null_count"] > 0]
    if cols_with_nulls and len(cols_with_nulls) >= (len(column_analyses) * 0.3):
        recommendations.append({
            "priority": "high",
            "category": "missing_values",
            "title": "Handle missing values",
            "description": f"{len(cols_with_nulls)} columns have missing values. Consider filling or removing these rows.",
            "affected_columns": [ca["name"] for ca in cols_with_nulls[:5]],
        })
    
    # Recommendation 2: Remove duplicates
    duplicate_pct = (column_analyses[0]["null_count"] if column_analyses else 0)  # Reuse logic
    # Note: Using profile data from backend
    recommendations.append({
        "priority": "medium",
        "category": "duplicates",
        "title": "Check for duplicate rows",
        "description": "Review and remove duplicate rows to improve data consistency.",
        "action": "drop_duplicates",
    })
    
    # Recommendation 3: Remove constant columns
    if constant_cols:
        recommendations.append({
            "priority": "high",
            "category": "constant_columns",
            "title": "Remove constant columns",
            "description": f"{len(constant_cols)} column(s) contain only one unique value and don't add information.",
            "affected_columns": [c["name"] for c in constant_cols],
        })
    
    # Recommendation 4: Review high-cardinality columns
    if high_cardinality_cols:
        recommendations.append({
            "priority": "medium",
            "category": "high_cardinality",
            "title": "Review high-cardinality columns",
            "description": f"{len(high_cardinality_cols)} column(s) have very high cardinality. Consider if they should be categorical.",
            "affected_columns": [c["name"] for c in high_cardinality_cols[:5]],
        })
    
    # Recommendation 5: Remove duplicate columns
    if duplicate_cols:
        recommendations.append({
            "priority": "high",
            "category": "duplicate_columns",
            "title": "Remove duplicate columns",
            "description": f"{len(duplicate_cols)} column(s) are exact duplicates.",
            "affected_columns": [d["column1"] for d in duplicate_cols],
        })
    
    # Recommendation 6: Check data types
    wrong_type_cols = [ca for ca in column_analyses if ca["invalid_count"] > 0]
    if wrong_type_cols:
        recommendations.append({
            "priority": "high",
            "category": "datatype",
            "title": "Fix data type issues",
            "description": f"{len(wrong_type_cols)} column(s) have invalid values for their detected type.",
            "affected_columns": [ca["name"] for ca in wrong_type_cols],
        })
    
    # Recommendation 7: Strip whitespace
    whitespace_cols = [ca for ca in column_analyses if ca["whitespace_count"] > 0]
    if whitespace_cols:
        recommendations.append({
            "priority": "low",
            "category": "whitespace",
            "title": "Strip whitespace from text columns",
            "description": f"{len(whitespace_cols)} column(s) contain leading/trailing whitespace.",
            "affected_columns": [ca["name"] for ca in whitespace_cols],
        })
    
    # Recommendation 8: Handle invalid values
    invalid_cols = [ca for ca in column_analyses if ca["empty_count"] > 0 or ca["whitespace_count"] > 0]
    if invalid_cols:
        recommendations.append({
            "priority": "medium",
            "category": "invalid_values",
            "title": "Handle invalid values",
            "description": f"{len(invalid_cols)} column(s) contain empty strings or whitespace-only values. Consider cleaning or removing these.",
            "affected_columns": [ca["name"] for ca in invalid_cols[:5]],
        })
    
    # Recommendation 9: Normalize data
    numeric_cols = [ca for ca in column_analyses if ca["type"] == "numeric" and ca["unique_count"] > 1]
    if len(numeric_cols) > 1:
        recommendations.append({
            "priority": "low",
            "category": "normalize",
            "title": "Normalize numeric data",
            "description": f"{len(numeric_cols)} numeric columns found. Consider normalizing or standardizing for better analysis.",
            "affected_columns": [ca["name"] for ca in numeric_cols[:5]],
        })
    
    # Recommendation 10: Overall data quality
    if health_score < 50:
        recommendations.append({
            "priority": "critical",
            "category": "overall_quality",
            "title": "Dataset quality is poor",
            "description": "Overall data quality score is low. Consider reviewing the data source and applying multiple cleaning operations.",
        })
    
    return recommendations
