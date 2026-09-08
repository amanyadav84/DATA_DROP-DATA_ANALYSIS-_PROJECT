"""Statistical analysis — hypothesis testing, normality tests, significance tests."""

from __future__ import annotations

from typing import Any

import numpy as np
import pandas as pd
from scipy import stats as sp_stats

from processor import detect_column_type


# ---------------------------------------------------------------------------
# Normality tests
# ---------------------------------------------------------------------------

def test_shapiro_wilk(series: pd.Series) -> dict[str, Any]:
    """Shapiro-Wilk test for normality (best for n < 5000)."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 3 or len(clean) > 5000:
        clean = clean.sample(min(5000, len(clean)), random_state=42)
    stat, p = sp_stats.shapiro(clean)
    return {
        "test": "Shapiro-Wilk",
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "is_normal": p > 0.05,
        "interpretation": "Data appears normally distributed" if p > 0.05 else "Data is NOT normally distributed",
        "sample_size": len(clean),
    }


def test_ks_normal(series: pd.Series) -> dict[str, Any]:
    """Kolmogorov-Smirnov test against normal distribution."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 5:
        return {"test": "Kolmogorov-Smirnov", "error": "Insufficient data"}
    stat, p = sp_stats.kstest(clean, "args", args=(clean.mean(), clean.std()))
    return {
        "test": "Kolmogorov-Smirnov",
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "is_normal": p > 0.05,
        "interpretation": "Data appears normally distributed" if p > 0.05 else "Data is NOT normally distributed",
        "sample_size": len(clean),
    }


def test_anderson_darling(series: pd.Series) -> dict[str, Any]:
    """Anderson-Darling test for normality."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 8:
        return {"test": "Anderson-Darling", "error": "Insufficient data"}
    result = sp_stats.anderson(clean, dist="norm")
    # Compare against 5% significance level (index 2)
    is_normal = result.statistic < result.critical_values[2]
    return {
        "test": "Anderson-Darling",
        "statistic": round(float(result.statistic), 6),
        "critical_values": {
            "15%": round(float(result.critical_values[0]), 4),
            "10%": round(float(result.critical_values[1]), 4),
            "5%": round(float(result.critical_values[2]), 4),
            "2.5%": round(float(result.critical_values[3]), 4),
            "1%": round(float(result.critical_values[4]), 4),
        },
        "is_normal": is_normal,
        "interpretation": "Data appears normally distributed" if is_normal else "Data is NOT normally distributed",
        "sample_size": len(clean),
    }


def test_jarque_bera(series: pd.Series) -> dict[str, Any]:
    """Jarque-Bera test for normality based on skewness and kurtosis."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) < 8:
        return {"test": "Jarque-Bera", "error": "Insufficient data"}
    stat, p = sp_stats.jarque_bera(clean)
    return {
        "test": "Jarque-Bera",
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "skewness": round(float(sp_stats.skew(clean)), 4),
        "kurtosis": round(float(sp_stats.kurtosis(clean)), 4),
        "is_normal": p > 0.05,
        "interpretation": "Data appears normally distributed" if p > 0.05 else "Data is NOT normally distributed (skew/kurtosis issue)",
        "sample_size": len(clean),
    }


def run_all_normality_tests(series: pd.Series) -> list[dict[str, Any]]:
    """Run all normality tests on a numeric series."""
    return [
        test_shapiro_wilk(series),
        test_ks_normal(series),
        test_anderson_darling(series),
        test_jarque_bera(series),
    ]


# ---------------------------------------------------------------------------
# Hypothesis tests
# ---------------------------------------------------------------------------

def ttest_ind(series_a: pd.Series, series_b: pd.Series,
              equal_var: bool = False) -> dict[str, Any]:
    """Independent two-sample t-test (Welch's by default)."""
    a = pd.to_numeric(series_a, errors="coerce").dropna()
    b = pd.to_numeric(series_b, errors="coerce").dropna()
    if len(a) < 2 or len(b) < 2:
        return {"test": "Independent t-test", "error": "Insufficient data in one or both groups"}
    stat, p = sp_stats.ttest_ind(a, b, equal_var=equal_var)
    cohens_d = (a.mean() - b.mean()) / np.sqrt((a.std()**2 + b.std()**2) / 2)
    return {
        "test": "Independent t-test" + (" (Student's)" if equal_var else " (Welch's)"),
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "significant": p < 0.05,
        "cohens_d": round(float(cohens_d), 4),
        "effect_size": "large" if abs(cohens_d) > 0.8 else "medium" if abs(cohens_d) > 0.5 else "small",
        "group_a": {"mean": round(float(a.mean()), 4), "std": round(float(a.std()), 4), "n": len(a)},
        "group_b": {"mean": round(float(b.mean()), 4), "std": round(float(b.std()), 4), "n": len(b)},
        "interpretation": f"Groups {'differ significantly' if p < 0.05 else 'are NOT significantly different'} (p={p:.4f})",
    }


def ttest_paired(series_a: pd.Series, series_b: pd.Series) -> dict[str, Any]:
    """Paired sample t-test (before/after)."""
    a = pd.to_numeric(series_a, errors="coerce").dropna()
    b = pd.to_numeric(series_b, errors="coerce").dropna()
    min_len = min(len(a), len(b))
    if min_len < 2:
        return {"test": "Paired t-test", "error": "Insufficient paired data"}
    a, b = a.iloc[:min_len], b.iloc[:min_len]
    stat, p = sp_stats.ttest_rel(a, b)
    return {
        "test": "Paired t-test",
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "significant": p < 0.05,
        "mean_difference": round(float((a - b).mean()), 4),
        "interpretation": f"Paired values {'differ significantly' if p < 0.05 else 'are NOT significantly different'} (p={p:.4f})",
    }


def anova_one_way(groups: list[pd.Series]) -> dict[str, Any]:
    """One-way ANOVA — compare means across 3+ groups."""
    clean_groups = []
    for g in groups:
        clean = pd.to_numeric(g, errors="coerce").dropna()
        if len(clean) >= 2:
            clean_groups.append(clean)
    if len(clean_groups) < 2:
        return {"test": "One-way ANOVA", "error": "Need at least 2 valid groups"}
    stat, p = sp_stats.f_oneway(*clean_groups)
    group_stats = [{"n": len(g), "mean": round(float(g.mean()), 4), "std": round(float(g.std()), 4)} for g in clean_groups]
    return {
        "test": "One-way ANOVA",
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "significant": p < 0.05,
        "n_groups": len(clean_groups),
        "groups": group_stats,
        "interpretation": f"Group means {'differ significantly' if p < 0.05 else 'are NOT significantly different'} (p={p:.4f})",
    }


def chi_square_test(df: pd.DataFrame, col_a: str, col_b: str) -> dict[str, Any]:
    """Chi-square test of independence between two categorical variables."""
    if col_a not in df.columns or col_b not in df.columns:
        return {"test": "Chi-Square", "error": "Column(s) not found"}
    contingency = pd.crosstab(df[col_a], df[col_b])
    if contingency.shape[0] < 2 or contingency.shape[1] < 2:
        return {"test": "Chi-Square", "error": "Need at least 2x2 contingency table"}
    stat, p, dof, expected = sp_stats.chi2_contingency(contingency)
    cramers_v = np.sqrt(stat / (len(df) * (min(contingency.shape) - 1)))
    return {
        "test": "Chi-Square Test of Independence",
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "degrees_of_freedom": int(dof),
        "cramers_v": round(float(cramers_v), 4),
        "significant": p < 0.05,
        "contingency_table": contingency.to_dict(),
        "interpretation": f"{col_a} and {col_b} are {'independently associated' if p < 0.05 else 'NOT significantly associated'} (p={p:.4f})",
    }


def mann_whitney_u(series_a: pd.Series, series_b: pd.Series) -> dict[str, Any]:
    """Mann-Whitney U test — non-parametric alternative to independent t-test."""
    a = pd.to_numeric(series_a, errors="coerce").dropna()
    b = pd.to_numeric(series_b, errors="coerce").dropna()
    if len(a) < 5 or len(b) < 5:
        return {"test": "Mann-Whitney U", "error": "Insufficient data"}
    stat, p = sp_stats.mannwhitneyu(a, b, alternative="two-sided")
    return {
        "test": "Mann-Whitney U",
        "statistic": round(float(stat), 6),
        "p_value": round(float(p), 6),
        "significant": p < 0.05,
        "group_a": {"median": round(float(a.median()), 4), "n": len(a)},
        "group_b": {"median": round(float(b.median()), 4), "n": len(b)},
        "interpretation": f"Distributions {'differ significantly' if p < 0.05 else 'are NOT significantly different'} (p={p:.4f})",
    }


# ---------------------------------------------------------------------------
# Descriptive statistics
# ---------------------------------------------------------------------------

def descriptive_stats(series: pd.Series) -> dict[str, Any]:
    """Comprehensive descriptive statistics for a numeric series."""
    clean = pd.to_numeric(series, errors="coerce").dropna()
    if len(clean) == 0:
        return {"error": "No valid numeric data"}
    return {
        "count": len(clean),
        "mean": round(float(clean.mean()), 4),
        "median": round(float(clean.median()), 4),
        "std": round(float(clean.std()), 4),
        "variance": round(float(clean.var()), 4),
        "min": round(float(clean.min()), 4),
        "max": round(float(clean.max()), 4),
        "range": round(float(clean.max() - clean.min()), 4),
        "q1": round(float(clean.quantile(0.25)), 4),
        "q3": round(float(clean.quantile(0.75)), 4),
        "iqr": round(float(clean.quantile(0.75) - clean.quantile(0.25)), 4),
        "skewness": round(float(clean.skew()), 4),
        "kurtosis": round(float(clean.kurtosis()), 4),
        "cv": round(float(clean.std() / clean.mean()), 4) if clean.mean() != 0 else None,
        "sem": round(float(clean.sem()), 4),
        "mode": round(float(clean.mode().iloc[0]), 4) if not clean.mode().empty else None,
    }


# ---------------------------------------------------------------------------
# Correlation tests
# ---------------------------------------------------------------------------

def pearson_test(series_a: pd.Series, series_b: pd.Series) -> dict[str, Any]:
    """Pearson correlation with significance test."""
    a = pd.to_numeric(series_a, errors="coerce").dropna()
    b = pd.to_numeric(series_b, errors="coerce").dropna()
    min_len = min(len(a), len(b))
    if min_len < 3:
        return {"test": "Pearson", "error": "Insufficient data"}
    a, b = a.iloc[:min_len], b.iloc[:min_len]
    r, p = sp_stats.pearsonr(a, b)
    return {
        "test": "Pearson Correlation",
        "r": round(float(r), 6),
        "r_squared": round(float(r**2), 6),
        "p_value": round(float(p), 6),
        "significant": p < 0.05,
        "strength": "very strong" if abs(r) > 0.9 else "strong" if abs(r) > 0.7 else "moderate" if abs(r) > 0.5 else "weak" if abs(r) > 0.3 else "very weak",
        "interpretation": f"{'Significant' if p < 0.05 else 'NOT significant'} {('positive' if r > 0 else 'negative')} correlation (r={r:.4f}, p={p:.4f})",
    }


def spearman_test(series_a: pd.Series, series_b: pd.Series) -> dict[str, Any]:
    """Spearman rank correlation with significance test."""
    a = pd.to_numeric(series_a, errors="coerce").dropna()
    b = pd.to_numeric(series_b, errors="coerce").dropna()
    min_len = min(len(a), len(b))
    if min_len < 3:
        return {"test": "Spearman", "error": "Insufficient data"}
    a, b = a.iloc[:min_len], b.iloc[:min_len]
    r, p = sp_stats.spearmanr(a, b)
    return {
        "test": "Spearman Rank Correlation",
        "rho": round(float(r), 6),
        "p_value": round(float(p), 6),
        "significant": p < 0.05,
        "strength": "very strong" if abs(r) > 0.9 else "strong" if abs(r) > 0.7 else "moderate" if abs(r) > 0.5 else "weak" if abs(r) > 0.3 else "very weak",
        "interpretation": f"{'Significant' if p < 0.05 else 'NOT significant'} monotonic relationship (rho={r:.4f}, p={p:.4f})",
    }
