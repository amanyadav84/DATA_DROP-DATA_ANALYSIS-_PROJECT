"""Advanced Distribution Analysis module."""

from __future__ import annotations

import json
import math
from typing import Any

import numpy as np
import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots
from scipy import stats as sp_stats


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


def _safe_float(val: Any) -> float | None:
    if val is None:
        return None
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return None
        return round(f, 6)
    except (TypeError, ValueError):
        return None


def _classify_shape(skew: float, kurt: float) -> str:
    abs_skew = abs(skew)
    if abs_skew <= 0.5 and abs(kurt) <= 1:
        return "Symmetric"
    if skew > 0.5:
        return "Right Skewed" if abs_skew <= 1.0 else "Highly Right Skewed"
    if skew < -0.5:
        return "Left Skewed" if abs_skew <= 1.0 else "Highly Left Skewed"
    if kurt > 1:
        return "Leptokurtic (Peaked)"
    if kurt < -1:
        return "Platykurtic (Flat)"
    return "Approximately Symmetric"


def _classify_normality(p_value: float, alpha: float = 0.05) -> str:
    return "Normally Distributed" if p_value > alpha else "Not Normally Distributed"


DARK_LAYOUT = {
    "paper_bgcolor": "rgba(0,0,0,0)",
    "plot_bgcolor": "rgba(0,0,0,0)",
    "font": {"color": "#c9d1d9", "family": "Inter, system-ui, sans-serif"},
    "margin": {"l": 48, "r": 24, "t": 40, "b": 48},
    "xaxis": {"gridcolor": "rgba(255,255,255,0.06)", "zerolinecolor": "rgba(255,255,255,0.1)"},
    "yaxis": {"gridcolor": "rgba(255,255,255,0.06)", "zerolinecolor": "rgba(255,255,255,0.1)"},
}


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

def _descriptive_stats(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna()
    n = len(clean)
    if n == 0:
        return {"count": 0}

    vals = clean.values.astype(float)
    mean = float(np.mean(vals))
    median = float(np.median(vals))

    mode_result = sp_stats.mode(vals, keepdims=True)
    mode_val = float(mode_result.mode[0]) if len(mode_result.mode) > 0 else mean

    mn, mx = float(np.min(vals)), float(np.max(vals))
    var = float(np.var(vals, ddof=1)) if n > 1 else 0.0
    std = float(np.std(vals, ddof=1)) if n > 1 else 0.0
    se = std / math.sqrt(n) if n > 0 else 0.0

    q1 = float(np.percentile(vals, 25))
    q2 = float(np.percentile(vals, 50))
    q3 = float(np.percentile(vals, 75))
    iqr = q3 - q1

    cv = (std / abs(mean) * 100) if mean != 0 else None

    return {
        "count": n,
        "mean": _safe_float(mean),
        "median": _safe_float(median),
        "mode": _safe_float(mode_val),
        "min": _safe_float(mn),
        "max": _safe_float(mx),
        "range": _safe_float(mx - mn),
        "variance": _safe_float(var),
        "std": _safe_float(std),
        "std_error": _safe_float(se),
        "q1": _safe_float(q1),
        "q2": _safe_float(q2),
        "q3": _safe_float(q3),
        "iqr": _safe_float(iqr),
        "cv": _safe_float(cv),
    }


# ---------------------------------------------------------------------------
# Distribution shape
# ---------------------------------------------------------------------------

def _shape_analysis(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna().values.astype(float)
    n = len(clean)
    if n < 8:
        return {"skewness": None, "kurtosis": None, "shape": "Insufficient data"}

    skew = float(sp_stats.skew(clean, bias=False))
    kurt = float(sp_stats.kurtosis(clean, bias=False))
    shape = _classify_shape(skew, kurt)

    return {
        "skewness": _safe_float(skew),
        "kurtosis": _safe_float(kurt),
        "shape": shape,
    }


# ---------------------------------------------------------------------------
# Normality tests
# ---------------------------------------------------------------------------

def _normality_tests(series: pd.Series) -> list[dict[str, Any]]:
    clean = series.dropna().values.astype(float)
    n = len(clean)
    tests = []

    if n >= 3:
        try:
            stat, p = sp_stats.shapiro(clean[:5000])  # Shapiro limit
            tests.append({
                "test": "Shapiro-Wilk",
                "statistic": _safe_float(stat),
                "p_value": _safe_float(p),
                "result": _classify_normality(p),
                "interpretation": f"W = {stat:.4f}, p = {p:.4f}. {'Reject H0: data is not normal.' if p <= 0.05 else 'Fail to reject H0: data is approximately normal.'}",
            })
        except Exception:
            pass

    if n >= 20:
        try:
            stat, crit, sl = sp_stats.anderson(clean, dist='norm')
            is_normal = stat < crit[2]  # 5% significance level
            tests.append({
                "test": "Anderson-Darling",
                "statistic": _safe_float(stat),
                "p_value": None,
                "result": "Normally Distributed" if is_normal else "Not Normally Distributed",
                "interpretation": f"A² = {stat:.4f}. {'Data is normal at 5% significance.' if is_normal else 'Data is not normal at 5% significance.'}",
            })
        except Exception:
            pass

    if n >= 5:
        try:
            stat, p = sp_stats.kstest(clean, 'norm', args=(np.mean(clean), np.std(clean, ddof=1)))
            tests.append({
                "test": "Kolmogorov-Smirnov",
                "statistic": _safe_float(stat),
                "p_value": _safe_float(p),
                "result": _classify_normality(p),
                "interpretation": f"D = {stat:.4f}, p = {p:.4f}. {'Reject H0: not normal.' if p <= 0.05 else 'Fail to reject H0: approximately normal.'}",
            })
        except Exception:
            pass

    if n >= 20:
        try:
            stat, p = sp_stats.normaltest(clean)
            tests.append({
                "test": "D'Agostino K²",
                "statistic": _safe_float(stat),
                "p_value": _safe_float(p),
                "result": _classify_normality(p),
                "interpretation": f"K² = {stat:.4f}, p = {p:.4f}. {'Data is not normal.' if p <= 0.05 else 'Data is approximately normal.'}",
            })
        except Exception:
            pass

    if n >= 20:
        try:
            stat, p = sp_stats.jarque_bera(clean)
            tests.append({
                "test": "Jarque-Bera",
                "statistic": _safe_float(stat),
                "p_value": _safe_float(p),
                "result": _classify_normality(p),
                "interpretation": f"JB = {stat:.4f}, p = {p:.4f}. {'Data is not normal (skew/kurtosis issue).' if p <= 0.05 else 'Data is approximately normal.'}",
            })
        except Exception:
            pass

    return tests


# ---------------------------------------------------------------------------
# Percentiles
# ---------------------------------------------------------------------------

def _percentile_analysis(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna().values.astype(float)
    if len(clean) == 0:
        return {}

    percentiles = [1, 5, 10, 25, 50, 75, 90, 95, 99]
    values = np.percentile(clean, percentiles)

    return {f"p{p}": _safe_float(v) for p, v in zip(percentiles, values)}


# ---------------------------------------------------------------------------
# Outlier detection (IQR method)
# ---------------------------------------------------------------------------

def _detect_outliers(series: pd.Series) -> dict[str, Any]:
    clean = series.dropna().values.astype(float)
    if len(clean) < 4:
        return {"count": 0, "percentage": 0, "lower_fence": None, "upper_fence": None}

    q1, q3 = float(np.percentile(clean, 25)), float(np.percentile(clean, 75))
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr
    outlier_count = int(np.sum((clean < lower) | (clean > upper)))
    pct = round(outlier_count / len(clean) * 100, 2)

    return {
        "count": outlier_count,
        "percentage": pct,
        "lower_fence": _safe_float(lower),
        "upper_fence": _safe_float(upper),
    }


# ---------------------------------------------------------------------------
# Distribution quality score
# ---------------------------------------------------------------------------

def _distribution_quality_score(shape: dict, normality: list[dict], outliers: dict,
                                  desc: dict, n_rows: int) -> dict[str, Any]:
    score = 100.0

    skew = shape.get("skewness")
    if skew is not None:
        abs_skew = abs(skew)
        if abs_skew > 2:
            score -= 25
        elif abs_skew > 1:
            score -= 15
        elif abs_skew > 0.5:
            score -= 5

    kurt = shape.get("kurtosis")
    if kurt is not None:
        abs_kurt = abs(kurt)
        if abs_kurt > 3:
            score -= 20
        elif abs_kurt > 2:
            score -= 10
        elif abs_kurt > 1:
            score -= 5

    outlier_pct = outliers.get("percentage", 0)
    if outlier_pct > 10:
        score -= 20
    elif outlier_pct > 5:
        score -= 10
    elif outlier_pct > 2:
        score -= 5

    normal_count = sum(1 for t in normality if t["result"] == "Normally Distributed")
    total_tests = len(normality) if normality else 1
    if normal_count == 0 and total_tests > 0:
        score -= 15
    elif normal_count < total_tests / 2:
        score -= 5

    cv = desc.get("cv")
    if cv is not None and cv > 100:
        score -= 10
    elif cv is not None and cv > 50:
        score -= 5

    score = max(0, min(100, round(score, 1)))

    if score >= 90:
        status = "Excellent"
    elif score >= 75:
        status = "Good"
    elif score >= 50:
        status = "Average"
    else:
        status = "Poor"

    return {"score": score, "status": status}


# ---------------------------------------------------------------------------
# AI Insights
# ---------------------------------------------------------------------------

def _generate_insights(col_name: str, desc: dict, shape: dict, normality: list[dict],
                       outliers: dict, percentiles: dict) -> list[str]:
    insights = []
    skew = shape.get("skewness")
    kurt = shape.get("kurtosis")
    shape_label = shape.get("shape", "")

    if "Skewed" in shape_label:
        direction = "right" if skew and skew > 0 else "left"
        insights.append(
            f"{col_name} is {shape_label.lower()} (skewness = {skew:.3f}), "
            f"indicating a long tail to the {direction}. "
            f"Consider a {'log' if direction == 'right' else 'square root'} transformation for normalization."
        )
    elif shape_label == "Symmetric" or shape_label == "Approximately Symmetric":
        insights.append(
            f"{col_name} follows an approximately symmetric distribution "
            f"(skewness = {skew:.3f}), which is suitable for parametric statistical tests."
        )

    if kurt is not None:
        if kurt > 3:
            insights.append(
                f"{col_name} has heavy tails (kurtosis = {kurt:.3f}), "
                f"indicating more extreme values than a normal distribution. "
                f"This may suggest the presence of outliers or a leptokurtic distribution."
            )
        elif kurt < -3:
            insights.append(
                f"{col_name} has light tails (kurtosis = {kurt:.3f}), "
                f"suggesting fewer extreme values than expected — a platykurtic distribution."
            )

    outlier_pct = outliers.get("percentage", 0)
    if outlier_pct > 5:
        insights.append(
            f"{col_name} contains {outliers['count']} outliers ({outlier_pct}% of data) "
            f"detected via IQR method (fences: [{outliers['lower_fence']:.3f}, {outliers['upper_fence']:.3f}]). "
            f"These may skew analyses and should be investigated."
        )
    elif outlier_pct > 0:
        insights.append(
            f"{col_name} has {outliers['count']} mild outlier(s) ({outlier_pct}%). "
            f"These are within acceptable range but worth monitoring."
        )

    normal_count = sum(1 for t in normality if t["result"] == "Normally Distributed")
    if normal_count == len(normality) and len(normality) > 0:
        insights.append(
            f"{col_name} passes all normality tests, confirming it follows a normal distribution."
        )
    elif normal_count == 0 and len(normality) > 0:
        insights.append(
            f"{col_name} fails all {len(normality)} normality tests, indicating a non-normal distribution."
        )

    cv = desc.get("cv")
    if cv is not None:
        if cv > 100:
            insights.append(
                f"{col_name} has very high variability (CV = {cv:.1f}%), "
                f"making it difficult to compare with other features without scaling."
            )
        elif cv < 10:
            insights.append(
                f"{col_name} is relatively stable (CV = {cv:.1f}%), "
                f"showing consistent values across the dataset."
            )

    mean = desc.get("mean")
    median = desc.get("median")
    if mean is not None and median is not None and desc.get("count", 0) > 10:
        diff_pct = abs(mean - median) / abs(median) * 100 if median != 0 else 0
        if diff_pct > 10:
            skewed_to = "right" if mean > median else "left"
            insights.append(
                f"Mean ({mean:.3f}) differs from median ({median:.3f}) by {diff_pct:.1f}%, "
                f"confirming {skewed_to}-skewed behavior."
            )

    if percentiles:
        p1 = percentiles.get("p1")
        p99 = percentiles.get("p99")
        if p1 is not None and p99 is not None:
            insights.append(
                f"99% of {col_name} values fall between {p1:.3f} and {p99:.3f} "
                f"(IQR range: {desc.get('q1', 0):.3f} to {desc.get('q3', 0):.3f})."
            )

    return insights


# ---------------------------------------------------------------------------
# AI Recommendations
# ---------------------------------------------------------------------------

def _generate_recommendations(col_name: str, shape: dict, normality: list[dict],
                               outliers: dict, desc: dict) -> list[dict[str, Any]]:
    recs = []
    skew = shape.get("skewness")
    kurt = shape.get("kurtosis")

    normal_count = sum(1 for t in normality if t["result"] == "Normally Distributed")

    if skew is not None:
        if skew > 1:
            recs.append({
                "priority": "high",
                "category": "transformation",
                "title": "Apply Log Transformation",
                "description": f"{col_name} is highly right-skewed (skewness = {skew:.3f}). "
                               f"A log transformation can reduce skewness and make the distribution more symmetric.",
                "affected_columns": [col_name],
                "action": "log_transform",
            })
        elif skew > 0.5:
            recs.append({
                "priority": "medium",
                "category": "transformation",
                "title": "Apply Square Root Transformation",
                "description": f"{col_name} is moderately right-skewed (skewness = {skew:.3f}). "
                               f"A square root transformation can help normalize the distribution.",
                "affected_columns": [col_name],
                "action": "sqrt_transform",
            })
        elif skew < -1:
            recs.append({
                "priority": "high",
                "category": "transformation",
                "title": "Apply Box-Cox or Yeo-Johnson Transformation",
                "description": f"{col_name} is highly left-skewed (skewness = {skew:.3f}). "
                               f"Box-Cox or Yeo-Johnson can handle negative values and reduce skewness.",
                "affected_columns": [col_name],
                "action": "boxcox_transform",
            })

    if normal_count == 0 and len(normality) > 0:
        recs.append({
            "priority": "medium",
            "category": "normalization",
            "title": "Normalize Distribution",
            "description": f"{col_name} is not normally distributed. "
                           f"Consider normalization for parametric statistical analyses.",
            "affected_columns": [col_name],
            "action": "normalize",
        })

    outlier_pct = outliers.get("percentage", 0)
    if outlier_pct > 5:
        recs.append({
            "priority": "high",
            "category": "outliers",
            "title": "Remove or Cap Outliers",
            "description": f"{col_name} has {outliers['count']} outliers ({outlier_pct}%). "
                           f"Consider removing or capping values beyond [{outliers['lower_fence']:.3f}, {outliers['upper_fence']:.3f}].",
            "affected_columns": [col_name],
            "action": "remove_outliers",
        })
    elif outlier_pct > 2:
        recs.append({
            "priority": "low",
            "category": "outliers",
            "title": "Monitor Outliers",
            "description": f"{col_name} has {outliers['count']} mild outliers ({outlier_pct}%). "
                           f"Review them to determine if they represent valid extreme values.",
            "affected_columns": [col_name],
            "action": "monitor_outliers",
        })

    cv = desc.get("cv")
    std = desc.get("std")
    mean = desc.get("mean")
    if std is not None and mean is not None:
        if mean != 0:
            recs.append({
                "priority": "low",
                "category": "scaling",
                "title": "Standard Scaling Recommended" if normal_count > 0 else "Robust Scaling Recommended",
                "description": f"{col_name} has std = {std:.4f}, mean = {mean:.4f}. "
                               f"{'Standard scaling (z-score) is appropriate since data is normal.' if normal_count > 0 else 'Robust scaling is recommended since data is non-normal.'}",
                "affected_columns": [col_name],
                "action": "standard_scale" if normal_count > 0 else "robust_scale",
            })

    if normal_count == len(normality) and len(normality) > 0:
        recs.append({
            "priority": "low",
            "category": "no_action",
            "title": "No Action Needed",
            "description": f"{col_name} is normally distributed with acceptable skewness and kurtosis. "
                           f"No transformation is necessary.",
            "affected_columns": [col_name],
            "action": "no_action",
        })

    return recs


# ---------------------------------------------------------------------------
# Main analysis
# ---------------------------------------------------------------------------

def compute_distribution(df: pd.DataFrame) -> dict[str, Any]:
    """Compute full distribution analysis for all numeric columns."""
    numeric_df = df.select_dtypes(include=[np.number])
    cols = numeric_df.columns.tolist()

    if not cols:
        return {"error": "No numeric columns available for distribution analysis."}

    columns_analysis = []
    normal_count = 0
    skewed_count = 0
    symmetric_count = 0
    outlier_cols = 0

    for col in cols:
        series = numeric_df[col]
        n_valid = series.notna().sum()
        if n_valid < 3:
            continue

        desc = _descriptive_stats(series)
        shape = _shape_analysis(series)
        normality = _normality_tests(series)
        outliers = _detect_outliers(series)
        percentiles = _percentile_analysis(series)
        quality = _distribution_quality_score(shape, normality, outliers, desc, n_valid)
        insights = _generate_insights(col, desc, shape, normality, outliers, percentiles)
        recs = _generate_recommendations(col, shape, normality, outliers, desc)

        is_normal = all(t["result"] == "Normally Distributed" for t in normality) if normality else False
        is_symmetric = shape["shape"] in ("Symmetric", "Approximately Symmetric")
        has_outliers = outliers["count"] > 0

        if is_normal:
            normal_count += 1
        if "Skewed" in shape["shape"]:
            skewed_count += 1
        if is_symmetric:
            symmetric_count += 1
        if has_outliers:
            outlier_cols += 1

        columns_analysis.append({
            "name": col,
            "descriptive": desc,
            "shape": shape,
            "normality": normality,
            "outliers": outliers,
            "percentiles": percentiles,
            "quality_score": quality,
            "insights": insights,
            "recommendations": recs,
        })

    analyzed_count = len(columns_analysis)
    quality_scores = [c["quality_score"]["score"] for c in columns_analysis]
    avg_quality = round(sum(quality_scores) / len(quality_scores), 1) if quality_scores else 0

    if avg_quality >= 90:
        avg_status = "Excellent"
    elif avg_quality >= 75:
        avg_status = "Good"
    elif avg_quality >= 50:
        avg_status = "Average"
    else:
        avg_status = "Poor"

    all_insights = []
    all_recs = []
    for c in columns_analysis:
        all_insights.extend(c["insights"])
        all_recs.extend(c["recommendations"])

    # Deduplicate recommendations by title
    seen_recs = set()
    unique_recs = []
    for r in all_recs:
        key = (r["title"], tuple(r.get("affected_columns", [])))
        if key not in seen_recs:
            seen_recs.add(key)
            unique_recs.append(r)

    return {
        "numeric_columns": cols,
        "num_analyzed": analyzed_count,
        "summary": {
            "total_numeric": analyzed_count,
            "normal_columns": normal_count,
            "skewed_columns": skewed_count,
            "symmetric_columns": symmetric_count,
            "columns_with_outliers": outlier_cols,
            "avg_quality_score": avg_quality,
            "avg_quality_status": avg_status,
        },
        "columns": columns_analysis,
        "insights": all_insights,
        "recommendations": unique_recs,
    }


# ---------------------------------------------------------------------------
# Chart builders
# ---------------------------------------------------------------------------

def _apply_dark_layout(fig: go.Figure, title: str, height: int = 450) -> go.Figure:
    fig.update_layout(
        title=title,
        **DARK_LAYOUT,
        legend={"bgcolor": "rgba(0,0,0,0)"},
        height=height,
    )
    return fig


def build_histogram(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna()
    fig = go.Figure()
    fig.add_trace(go.Histogram(
        x=clean.values,
        nbinsx=50,
        marker_color="#7c9cff",
        opacity=0.85,
        hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
    ))

    mean_val = float(clean.mean())
    median_val = float(clean.median())
    fig.add_vline(x=mean_val, line_dash="dash", line_color="#56d9a1",
                  annotation_text=f"Mean: {mean_val:.3f}", annotation_position="top right")
    fig.add_vline(x=median_val, line_dash="dot", line_color="#f0a35e",
                  annotation_text=f"Median: {median_val:.3f}", annotation_position="top left")

    fig.update_layout(xaxis_title=col_name, yaxis_title="Count", bargap=0.05)
    return _to_jsonable(_apply_dark_layout(fig, f"Distribution of {col_name}"))


def build_kde(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna().values.astype(float)
    if len(clean) < 2:
        fig = go.Figure()
        fig.update_layout(title="Insufficient data for KDE")
        return _to_jsonable(fig)

    kde_x = np.linspace(float(np.min(clean)), float(np.max(clean)), 200)
    kde = sp_stats.gaussian_kde(clean)
    kde_y = kde(kde_x)

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=kde_x, y=kde_y,
        mode="lines",
        fill="tozeroy",
        line=dict(color="#7c9cff", width=2),
        fillcolor="rgba(124,156,255,0.15)",
        name="KDE",
        hovertemplate="<b>x:</b> %{x:.4f}<br><b>Density:</b> %{y:.6f}<extra></extra>",
    ))

    mean_val = float(np.mean(clean))
    median_val = float(np.median(clean))
    fig.add_vline(x=mean_val, line_dash="dash", line_color="#56d9a1",
                  annotation_text=f"Mean: {mean_val:.3f}", annotation_position="top right")
    fig.add_vline(x=median_val, line_dash="dot", line_color="#f0a35e",
                  annotation_text=f"Median: {median_val:.3f}", annotation_position="top left")

    fig.update_layout(xaxis_title=col_name, yaxis_title="Density")
    return _to_jsonable(_apply_dark_layout(fig, f"KDE of {col_name}"))


def build_box_plot(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna()
    fig = go.Figure()
    fig.add_trace(go.Box(
        y=clean.values,
        name=col_name,
        boxpoints="outliers",
        marker_color="#7c9cff",
        line_color="#7c9cff",
        fillcolor="rgba(124,156,255,0.15)",
        hovertemplate="<b>%{y}</b><extra></extra>",
    ))
    fig.update_layout(yaxis_title=col_name, showlegend=False)
    return _to_jsonable(_apply_dark_layout(fig, f"Box Plot of {col_name}"))


def build_violin(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna()
    fig = go.Figure()
    fig.add_trace(go.Violin(
        y=clean.values,
        name=col_name,
        box_visible=True,
        meanline_visible=True,
        line_color="#7c9cff",
        fillcolor="rgba(124,156,255,0.15)",
        hovertemplate="<b>%{y}</b><extra></extra>",
    ))
    fig.update_layout(yaxis_title=col_name, showlegend=False)
    return _to_jsonable(_apply_dark_layout(fig, f"Violin Plot of {col_name}"))


def build_ecdf(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna().values.astype(float)
    sorted_vals = np.sort(clean)
    n = len(sorted_vals)
    ecdf_y = np.arange(1, n + 1) / n

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sorted_vals, y=ecdf_y,
        mode="lines",
        line=dict(color="#7c9cff", width=2),
        name="ECDF",
        hovertemplate="<b>x:</b> %{x:.4f}<br><b>Proportion:</b> %{y:.4f}<extra></extra>",
    ))

    for pct, color in [(0.25, "#56d9a1"), (0.50, "#f0a35e"), (0.75, "#e06c9c")]:
        val = float(np.percentile(clean, pct * 100))
        fig.add_hline(y=pct, line_dash="dot", line_color=color, opacity=0.5)
        fig.add_vline(x=val, line_dash="dot", line_color=color, opacity=0.5,
                      annotation_text=f"Q{int(pct*100)}={val:.3f}", annotation_position="top right")

    fig.update_layout(xaxis_title=col_name, yaxis_title="Proportion", yaxis_range=[0, 1.05])
    return _to_jsonable(_apply_dark_layout(fig, f"ECDF of {col_name}"))


def build_qq_plot(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna().values.astype(float)
    n = len(clean)
    if n < 5:
        fig = go.Figure()
        fig.update_layout(title="Insufficient data for QQ Plot")
        return _to_jsonable(fig)

    theoretical = sp_stats.probplot(clean, dist="norm")
    theoretical_x = theoretical[0][0]
    theoretical_y = theoretical[0][1]

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=theoretical_x, y=theoretical_y,
        mode="markers",
        marker=dict(color="#7c9cff", size=6, opacity=0.7),
        name="Data Points",
        hovertemplate="<b>Theoretical:</b> %{x:.4f}<br><b>Sample:</b> %{y:.4f}<extra></extra>",
    ))

    # Reference line
    slope, intercept, r_val = theoretical[1]
    line_x = np.array([theoretical_x.min(), theoretical_x.max()])
    line_y = slope * line_x + intercept
    fig.add_trace(go.Scatter(
        x=line_x, y=line_y,
        mode="lines",
        line=dict(color="#f87171", dash="dash", width=2),
        name="Reference Line",
    ))

    fig.add_annotation(
        text=f"R = {r_val:.4f}",
        xref="paper", yref="paper",
        x=0.02, y=0.98,
        showarrow=False,
        font=dict(size=14, color="#56d9a1"),
        bgcolor="rgba(0,0,0,0.5)",
        borderpad=4,
    )

    fig.update_layout(xaxis_title="Theoretical Quantiles", yaxis_title="Sample Quantiles")
    return _to_jsonable(_apply_dark_layout(fig, f"QQ Plot of {col_name}"))


def build_cdf(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna().values.astype(float)
    sorted_vals = np.sort(clean)
    n = len(sorted_vals)
    cdf_y = np.arange(1, n + 1) / n

    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=sorted_vals, y=cdf_y,
        mode="lines",
        line=dict(color="#7c9cff", width=2),
        fill="tozeroy",
        fillcolor="rgba(124,156,255,0.1)",
        name="CDF",
        hovertemplate="<b>x:</b> %{x:.4f}<br><b>CDF:</b> %{y:.4f}<extra></extra>",
    ))

    fig.update_layout(xaxis_title=col_name, yaxis_title="Cumulative Probability", yaxis_range=[0, 1.05])
    return _to_jsonable(_apply_dark_layout(fig, f"CDF of {col_name}"))


def build_frequency(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna()
    counts = clean.value_counts().sort_index()
    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=counts.index.astype(str),
        y=counts.values,
        marker_color="#7c9cff",
        hovertemplate="<b>%{x}</b><br>Count: %{y}<extra></extra>",
    ))
    fig.update_layout(xaxis_title=col_name, yaxis_title="Frequency", bargap=0.1)
    return _to_jsonable(_apply_dark_layout(fig, f"Frequency Distribution of {col_name}"))


def build_rug(series: pd.Series, col_name: str) -> dict:
    clean = series.dropna().values.astype(float)
    fig = go.Figure()
    fig.add_trace(go.Box(
        y=clean,
        name=col_name,
        boxpoints=False,
        marker_color="#7c9cff",
        line_color="#7c9cff",
        fillcolor="rgba(124,156,255,0.15)",
    ))
    # Rug trace (vertical lines at each data point, jittered for visibility)
    fig.add_trace(go.Scatter(
        x=np.zeros_like(clean) + 0.5,
        y=clean,
        mode="markers",
        marker=dict(symbol="line-ns", size=10, color="#f0a35e", opacity=0.3),
        name="Rug",
        hovertemplate="<b>%{y}</b><extra></extra>",
    ))
    fig.update_layout(yaxis_title=col_name, showlegend=False)
    return _to_jsonable(_apply_dark_layout(fig, f"Rug Plot of {col_name}"))


CHART_BUILDERS = {
    "histogram": build_histogram,
    "kde": build_kde,
    "box": build_box_plot,
    "violin": build_violin,
    "ecdf": build_ecdf,
    "qq": build_qq_plot,
    "cdf": build_cdf,
    "frequency": build_frequency,
    "rug": build_rug,
}


def build_distribution_chart(df: pd.DataFrame, col: str, chart_type: str) -> dict:
    if col not in df.columns:
        return {"error": f"Column '{col}' not found."}
    if chart_type not in CHART_BUILDERS:
        return {"error": f"Unknown chart type: '{chart_type}'."}

    series = pd.to_numeric(df[col], errors="coerce")
    builder = CHART_BUILDERS[chart_type]
    return builder(series, col)


# ---------------------------------------------------------------------------
# Comparison charts
# ---------------------------------------------------------------------------

def build_comparison_overlay(df: pd.DataFrame, cols: list[str], chart_type: str) -> dict:
    if not cols:
        return {"error": "No columns selected."}

    colors = ["#7c9cff", "#56d9a1", "#f0a35e", "#e06c9c", "#a78bfa"]

    if chart_type == "overlay_hist":
        fig = go.Figure()
        for i, col in enumerate(cols):
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            fig.add_trace(go.Histogram(
                x=series.values, name=col, opacity=0.5,
                marker_color=colors[i % len(colors)],
                nbinsx=40,
            ))
        fig.update_layout(barmode="overlay", xaxis_title="Value", yaxis_title="Count")
        return _to_jsonable(_apply_dark_layout(fig, "Overlay Histogram", 500))

    elif chart_type == "overlay_kde":
        fig = go.Figure()
        for i, col in enumerate(cols):
            series = pd.to_numeric(df[col], errors="coerce").dropna().values.astype(float)
            if len(series) < 2:
                continue
            kde_x = np.linspace(float(np.min(series)), float(np.max(series)), 200)
            kde = sp_stats.gaussian_kde(series)
            fig.add_trace(go.Scatter(
                x=kde_x, y=kde(kde_x), mode="lines", name=col,
                line=dict(color=colors[i % len(colors)], width=2),
            ))
        fig.update_layout(xaxis_title="Value", yaxis_title="Density")
        return _to_jsonable(_apply_dark_layout(fig, "Overlay KDE", 500))

    elif chart_type == "box_compare":
        fig = go.Figure()
        for i, col in enumerate(cols):
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            fig.add_trace(go.Box(
                y=series.values, name=col,
                marker_color=colors[i % len(colors)],
                line_color=colors[i % len(colors)],
                fillcolor=f"rgba({int(colors[i % len(colors)][1:3],16)},{int(colors[i % len(colors)][3:5],16)},{int(colors[i % len(colors)][5:7],16)},0.15)",
            ))
        fig.update_layout(yaxis_title="Value", showlegend=True)
        return _to_jsonable(_apply_dark_layout(fig, "Boxplot Comparison", 500))

    elif chart_type == "violin_compare":
        fig = go.Figure()
        for i, col in enumerate(cols):
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            fig.add_trace(go.Violin(
                y=series.values, name=col, box_visible=True, meanline_visible=True,
                line_color=colors[i % len(colors)],
                fillcolor=f"rgba({int(colors[i % len(colors)][1:3],16)},{int(colors[i % len(colors)][3:5],16)},{int(colors[i % len(colors)][5:7],16)},0.15)",
            ))
        fig.update_layout(yaxis_title="Value", showlegend=True)
        return _to_jsonable(_apply_dark_layout(fig, "Violin Comparison", 500))

    elif chart_type == "stats_compare":
        stats_data = []
        for col in cols:
            series = pd.to_numeric(df[col], errors="coerce").dropna()
            stats_data.append({
                "column": col,
                "mean": round(float(series.mean()), 4),
                "median": round(float(series.median()), 4),
                "std": round(float(series.std()), 4),
                "min": round(float(series.min()), 4),
                "max": round(float(series.max()), 4),
            })

        fig = go.Figure()
        fig.add_trace(go.Bar(
            name="Mean", x=[s["column"] for s in stats_data],
            y=[s["mean"] for s in stats_data], marker_color="#7c9cff",
        ))
        fig.add_trace(go.Bar(
            name="Median", x=[s["column"] for s in stats_data],
            y=[s["median"] for s in stats_data], marker_color="#56d9a1",
        ))
        fig.update_layout(barmode="group", yaxis_title="Value")
        return _to_jsonable(_apply_dark_layout(fig, "Summary Statistics Comparison", 500))

    return {"error": f"Unknown comparison type: {chart_type}"}


# ---------------------------------------------------------------------------
# Transformation preview
# ---------------------------------------------------------------------------

def build_transform_preview(df: pd.DataFrame, col: str, transform: str) -> dict:
    if col not in df.columns:
        return {"error": f"Column '{col}' not found."}

    series = pd.to_numeric(df[col], errors="coerce").dropna().values.astype(float)
    if len(series) < 2:
        return {"error": "Insufficient data for transformation."}

    transformed = None
    label = transform

    if transform == "log":
        if np.any(series <= 0):
            shifted = series - float(np.min(series)) + 1
            transformed = np.log(shifted)
            label = "log(x - min + 1)"
        else:
            transformed = np.log(series)
            label = "log(x)"
    elif transform == "sqrt":
        if np.any(series < 0):
            shifted = series - float(np.min(series))
            transformed = np.sqrt(shifted)
            label = "sqrt(x - min)"
        else:
            transformed = np.sqrt(series)
            label = "sqrt(x)"
    elif transform == "boxcox":
        if np.any(series <= 0):
            shifted = series - float(np.min(series)) + 1
            transformed, _ = sp_stats.boxcox(shifted)
            label = "Box-Cox(x - min + 1)"
        else:
            transformed, _ = sp_stats.boxcox(series)
            label = "Box-Cox(x)"
    elif transform == "yeojohnson":
        transformed, _ = sp_stats.yeojohnson(series)
        label = "Yeo-Johnson(x)"
    elif transform == "minmax":
        mn, mx = float(np.min(series)), float(np.max(series))
        rng = mx - mn
        transformed = (series - mn) / rng if rng > 0 else np.zeros_like(series)
        label = "Min-Max Scaling"
    elif transform == "standardize":
        mean, std = float(np.mean(series)), float(np.std(series, ddof=1))
        transformed = (series - mean) / std if std > 0 else np.zeros_like(series)
        label = "Standardization (Z-score)"
    elif transform == "robust":
        median = float(np.median(series))
        iqr = float(np.percentile(series, 75) - np.percentile(series, 25))
        transformed = (series - median) / iqr if iqr > 0 else np.zeros_like(series)
        label = "Robust Scaling"
    else:
        return {"error": f"Unknown transform: {transform}"}

    if transformed is None:
        return {"error": "Transformation failed."}

    original_skew = float(sp_stats.skew(series, bias=False))
    transformed_skew = float(sp_stats.skew(transformed, bias=False))
    original_kurt = float(sp_stats.kurtosis(series, bias=False))
    transformed_kurt = float(sp_stats.kurtosis(transformed, bias=False))

    fig = make_subplots(rows=1, cols=2, subplot_titles=[f"Original (skew={original_skew:.3f})", f"{label} (skew={transformed_skew:.3f})"])

    fig.add_trace(go.Histogram(x=series, nbinsx=40, marker_color="#7c9cff", opacity=0.85, name="Original"), row=1, col=1)
    fig.add_trace(go.Histogram(x=transformed, nbinsx=40, marker_color="#56d9a1", opacity=0.85, name="Transformed"), row=1, col=2)

    fig.update_layout(**DARK_LAYOUT, height=400, showlegend=False,
                      title=f"Transformation Preview: {col}")

    return {
        "spec": _to_jsonable(fig),
        "original_skew": _safe_float(original_skew),
        "transformed_skew": _safe_float(transformed_skew),
        "original_kurt": _safe_float(original_kurt),
        "transformed_kurt": _safe_float(transformed_kurt),
        "label": label,
    }


# ---------------------------------------------------------------------------
# Export helpers
# ---------------------------------------------------------------------------

def export_distribution_csv(columns_analysis: list[dict]) -> str:
    rows = []
    for c in columns_analysis:
        d = c["descriptive"]
        s = c["shape"]
        o = c["outliers"]
        q = c["quality_score"]
        rows.append({
            "column": c["name"],
            "count": d.get("count"),
            "mean": d.get("mean"),
            "median": d.get("median"),
            "std": d.get("std"),
            "min": d.get("min"),
            "max": d.get("max"),
            "skewness": s.get("skewness"),
            "kurtosis": s.get("kurtosis"),
            "shape": s.get("shape"),
            "outlier_count": o.get("count"),
            "outlier_pct": o.get("percentage"),
            "quality_score": q.get("score"),
            "quality_status": q.get("status"),
        })
    df = pd.DataFrame(rows)
    return df.to_csv(index=False)


def export_distribution_json(columns_analysis: list[dict]) -> str:
    return json.dumps(columns_analysis, indent=2, default=_json_default)
