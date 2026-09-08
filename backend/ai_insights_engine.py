"""Smart AI Insights Engine — builds optimized prompts, calls LLM, returns structured insights."""

from __future__ import annotations

import json
import hashlib
from typing import Any
from datetime import datetime, timezone

import numpy as np
import pandas as pd

from ai_service import ai_analyze_json
from processor import profile_dataframe
from quality_report import analyze_dataset_quality
from correlation import compute_correlation
from distribution import compute_distribution


# ---------------------------------------------------------------------------
# Cache
# ---------------------------------------------------------------------------
_insight_cache: dict[str, dict] = {}

def _cache_key(session_id: str, extra: str = "") -> str:
    return hashlib.md5(f"{session_id}:{extra}".encode()).hexdigest()

def get_cached_insights(session_id: str) -> dict | None:
    return _insight_cache.get(_cache_key(session_id))

def set_cached_insights(session_id: str, data: dict) -> None:
    _insight_cache[_cache_key(session_id)] = data

def clear_cache(session_id: str) -> None:
    _insight_cache.pop(_cache_key(session_id), None)


# ---------------------------------------------------------------------------
# Statistical pre-analysis (no LLM needed)
# ---------------------------------------------------------------------------

def _compute_dataset_stats(df: pd.DataFrame, profile: dict) -> dict:
    """Aggregate all statistical summaries into a compact dict for the LLM."""
    stats: dict[str, Any] = {}

    # Basic info
    stats["rows"] = len(df)
    stats["columns"] = len(df.columns)
    stats["memory_mb"] = round(df.memory_usage(deep=True).sum() / 1048576, 2)

    # Column types
    numeric_cols = df.select_dtypes(include=[np.number]).columns.tolist()
    cat_cols = df.select_dtypes(include=["object", "category"]).columns.tolist()
    date_cols = df.select_dtypes(include=["datetime64"]).columns.tolist()
    bool_cols = [c for c in df.columns if df[c].dtype == bool or (
        df[c].nunique() == 2 and set(df[c].dropna().unique()).issubset({True, False, "True", "False", "yes", "no", "Yes", "No", 0, 1})
    )]

    stats["numeric_columns"] = numeric_cols
    stats["categorical_columns"] = cat_cols
    stats["datetime_columns"] = date_cols
    stats["boolean_columns"] = bool_cols

    # Missing values
    missing = df.isnull().sum()
    missing_pct = (missing / len(df) * 100).round(2)
    stats["missing_summary"] = {
        col: {"count": int(missing[col]), "pct": float(missing_pct[col])}
        for col in df.columns if missing[col] > 0
    }
    stats["total_missing_pct"] = round(float(missing.sum() / (len(df) * len(df.columns)) * 100), 2)

    # Duplicates
    stats["duplicate_rows"] = int(df.duplicated().sum())
    stats["duplicate_pct"] = round(float(df.duplicated().sum() / len(df) * 100), 2)

    # Numeric stats (top 15 most variable)
    numeric_stats = {}
    for col in numeric_cols[:30]:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        q1 = float(s.quantile(0.25))
        q3 = float(s.quantile(0.75))
        iqr = q3 - q1
        lower = q1 - 1.5 * iqr
        upper = q3 + 1.5 * iqr
        outliers = int(((s < lower) | (s > upper)).sum())
        numeric_stats[col] = {
            "mean": round(float(s.mean()), 4),
            "median": round(float(s.median()), 4),
            "std": round(float(s.std()), 4),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
            "skewness": round(float(s.skew()), 4),
            "kurtosis": round(float(s.kurtosis()), 4),
            "q1": round(q1, 4),
            "q3": round(q3, 4),
            "iqr": round(iqr, 4),
            "outlier_count": outliers,
            "outlier_pct": round(outliers / len(s) * 100, 2) if len(s) > 0 else 0,
            "zeros": int((s == 0).sum()),
            "negatives": int((s < 0).sum()),
        }
    stats["numeric_stats"] = numeric_stats

    # Categorical stats (top values)
    cat_stats = {}
    for col in cat_cols[:20]:
        vc = df[col].value_counts()
        unique_count = int(df[col].nunique())
        top_values = vc.head(5).to_dict()
        cat_stats[col] = {
            "unique_count": unique_count,
            "top_values": {str(k): int(v) for k, v in top_values.items()},
            "concentration": round(float(vc.iloc[0] / len(df) * 100), 2) if len(vc) > 0 else 0,
            "null_count": int(df[col].isnull().sum()),
        }
    stats["categorical_stats"] = cat_stats

    # Date stats
    date_stats = {}
    for col in date_cols:
        s = df[col].dropna()
        if len(s) == 0:
            continue
        date_stats[col] = {
            "min": str(s.min()),
            "max": str(s.max()),
            "range_days": (s.max() - s.min()).days if hasattr(s.max() - s.min(), 'days') else 0,
        }
    stats["date_stats"] = date_stats

    # Correlations (top pairs)
    try:
        corr_report = compute_correlation(df, "pearson")
        top_pairs = corr_report.get("pairs", [])[:10]
        stats["top_correlations"] = top_pairs
        stats["multicollinearity"] = corr_report.get("multicollinearity", [])
    except Exception:
        stats["top_correlations"] = []
        stats["multicollinearity"] = []

    # Distribution summary
    try:
        dist_report = compute_distribution(df)
        dist_cols = dist_report.get("columns", [])[:10]
        stats["distribution_summary"] = [
            {
                "name": c.get("name"),
                "shape": c.get("shape", {}),
                "quality_score": c.get("quality_score", {}).get("score", 0),
                "normality_tests": c.get("normality_tests", {}),
            }
            for c in dist_cols
        ]
    except Exception:
        stats["distribution_summary"] = []

    # Potential target candidates
    target_candidates = []
    for col in numeric_cols:
        nunique = df[col].nunique()
        if 2 <= nunique <= min(20, len(df) * 0.05):
            target_candidates.append({"column": col, "unique_values": int(nunique), "type": "classification"})
        elif nunique > 20 and nunique > len(df) * 0.05:
            target_candidates.append({"column": col, "unique_values": int(nunique), "type": "regression"})
    stats["target_candidates"] = target_candidates

    # KPI detection
    kpi_candidates = []
    kpi_keywords = {
        "revenue": ["revenue", "sales", "amount", "total", "income"],
        "profit": ["profit", "margin", "gain", "net"],
        "cost": ["cost", "expense", "spend", "price"],
        "count": ["count", "quantity", "orders", "transactions", "units"],
        "rate": ["rate", "ratio", "percent", "conversion", "growth"],
        "customer": ["customer", "user", "client", "subscriber"],
        "date": ["date", "time", "period", "month", "year", "day"],
    }
    for col in df.columns:
        col_lower = col.lower()
        for kpi_type, keywords in kpi_keywords.items():
            if any(kw in col_lower for kw in keywords):
                kpi_candidates.append({"column": col, "detected_type": kpi_type})
                break
    stats["kpi_candidates"] = kpi_candidates

    return stats


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

_SYSTEM_PROMPT = """You are a world-class Senior Business Analyst and Data Scientist.
You analyze datasets and produce actionable, data-driven insights.

RULES:
- Every insight MUST reference actual numbers, column names, or values from the dataset.
- Never produce generic statements like "the data shows" or "there are trends".
- Use precise language: "Revenue declined 18% after March" not "there was a decline".
- Rank each insight by priority: critical, high, medium, low.
- Include impact scores (1-10).
- Organize insights into categories.
- Use natural language that a CEO can understand.
- Always end with specific, actionable recommendations.

OUTPUT FORMAT:
Return a JSON object with this EXACT structure:
{
  "dataset_understanding": {
    "purpose": "string - what this dataset represents",
    "domain": "string - business domain",
    "confidence": number 0-100,
    "key_columns": ["col1", "col2"],
    "use_cases": ["use case 1", "use case 2"]
  },
  "executive_summary": {
    "situation": "string - current situation in 2-3 sentences",
    "key_findings": ["finding1", "finding2"],
    "risks": ["risk1", "risk2"],
    "opportunities": ["opportunity1", "opportunity2"],
    "recommendations": ["recommendation1", "recommendation2"]
  },
  "insights": [
    {
      "id": "unique_id",
      "category": "business|quality|correlation|outlier|distribution|kpi|ml|forecast|risk",
      "title": "Short insight title",
      "detail": "Full insight with actual numbers",
      "priority": "critical|high|medium|low",
      "impact_score": number 1-10,
      "evidence": "Which data supports this",
      "action": "What to do about it"
    }
  ],
  "kpis": [
    {
      "name": "KPI name",
      "value": "actual value from data",
      "description": "what this means",
      "trend": "increasing|decreasing|stable|volatile",
      "status": "good|warning|critical"
    }
  ],
  "risks": [
    {
      "title": "Risk title",
      "severity": "critical|high|medium|low",
      "description": "Detailed risk description",
      "impact": "Business impact",
      "mitigation": "How to address"
    }
  ],
  "ml_recommendations": {
    "target_candidates": ["col1"],
    "recommended_tasks": ["classification", "regression", "clustering"],
    "feature_engineering": ["suggestion1"],
    "algorithms": ["Random Forest", "XGBoost"]
  },
  "forecast_suggestions": [
    {
      "column": "date_column",
      "metric": "what to forecast",
      "method": "recommended method",
      "reason": "why"
    }
  ],
  "data_quality_assessment": {
    "score": number 0-100,
    "status": "excellent|good|fair|poor",
    "issues": ["issue1"],
    "treatment_recommendations": ["rec1"]
  }
}

Return ONLY valid JSON. No markdown, no code blocks, no extra text."""


def _build_prompt(df: pd.DataFrame, profile: dict, stats: dict, extra_context: str = "") -> str:
    """Build an optimized prompt with dataset metadata and statistics."""
    parts = [
        "Analyze this dataset and generate comprehensive business insights.\n",
        "=== DATASET METADATA ===",
        f"Rows: {stats['rows']:,}",
        f"Columns: {stats['columns']}",
        f"Numeric columns: {', '.join(stats['numeric_columns'][:15]) or 'None'}",
        f"Categorical columns: {', '.join(stats['categorical_columns'][:15]) or 'None'}",
        f"Date columns: {', '.join(stats['datetime_columns'][:5]) or 'None'}",
        f"Boolean columns: {', '.join(stats['boolean_columns'][:5]) or 'None'}",
        f"Total missing: {stats['total_missing_pct']}%",
        f"Duplicate rows: {stats['duplicate_rows']:,} ({stats['duplicate_pct']}%)",
        "",
    ]

    # Numeric stats
    if stats.get("numeric_stats"):
        parts.append("=== NUMERIC COLUMN STATISTICS ===")
        for col, s in stats["numeric_stats"].items():
            parts.append(
                f"{col}: mean={s['mean']}, median={s['median']}, std={s['std']}, "
                f"range=[{s['min']}, {s['max']}], skew={s['skewness']}, kurt={s['kurtosis']}, "
                f"outliers={s['outlier_count']} ({s['outlier_pct']}%), zeros={s['zeros']}, negatives={s['negatives']}"
            )
        parts.append("")

    # Categorical stats
    if stats.get("categorical_stats"):
        parts.append("=== CATEGORICAL COLUMN STATISTICS ===")
        for col, s in stats["categorical_stats"].items():
            top = list(s["top_values"].items())[:3]
            parts.append(
                f"{col}: unique={s['unique_count']}, "
                f"top={top}, concentration={s['concentration']}%"
            )
        parts.append("")

    # Date stats
    if stats.get("date_stats"):
        parts.append("=== DATE COLUMN STATISTICS ===")
        for col, s in stats["date_stats"].items():
            parts.append(f"{col}: range={s['min']} to {s['max']}, span={s['range_days']} days")
        parts.append("")

    # Correlations
    if stats.get("top_correlations"):
        parts.append("=== TOP CORRELATIONS ===")
        for p in stats["top_correlations"][:10]:
            parts.append(f"{p['feature_a']} <-> {p['feature_b']}: r={p['value']:.4f} ({p['strength']})")
        parts.append("")

    if stats.get("multicollinearity"):
        parts.append("=== MULTICOLLINEARITY WARNINGS ===")
        for m in stats["multicollinearity"][:5]:
            parts.append(f"{m['feature_a']} <-> {m['feature_b']}: r={m['value']:.4f} (HIGH)")
        parts.append("")

    # Distribution summary
    if stats.get("distribution_summary"):
        parts.append("=== DISTRIBUTION SUMMARY ===")
        for d in stats["distribution_summary"][:10]:
            shape = d.get("shape", {})
            parts.append(
                f"{d['name']}: skew={shape.get('skewness', 'N/A')}, "
                f"kurt={shape.get('kurtosis', 'N/A')}, shape={shape.get('shape', 'N/A')}, "
                f"quality={d.get('quality_score', 'N/A')}"
            )
        parts.append("")

    # Target candidates
    if stats.get("target_candidates"):
        parts.append("=== POTENTIAL TARGET COLUMNS ===")
        for t in stats["target_candidates"][:10]:
            parts.append(f"{t['column']}: {t['type']} ({t['unique_values']} unique values)")
        parts.append("")

    # KPI candidates
    if stats.get("kpi_candidates"):
        parts.append("=== KPI CANDIDATES ===")
        for k in stats["kpi_candidates"][:10]:
            parts.append(f"{k['column']}: detected as {k['detected_type']}")
        parts.append("")

    # Sample values for categorical columns
    parts.append("=== SAMPLE VALUES (first 5 per categorical column) ===")
    for col in stats["categorical_columns"][:8]:
        try:
            sample = df[col].dropna().head(5).tolist()
            parts.append(f"{col}: {sample}")
        except Exception:
            pass
    parts.append("")

    if extra_context:
        parts.append(f"=== USER CONTEXT ===\n{extra_context}\n")

    return "\n".join(parts)


# ---------------------------------------------------------------------------
# Main engine
# ---------------------------------------------------------------------------

def generate_ai_insights(
    df: pd.DataFrame,
    profile: dict,
    session_id: str,
    extra_context: str = "",
    force_refresh: bool = False,
) -> dict[str, Any]:
    """Generate comprehensive AI insights for a dataset.

    Steps:
    1. Compute all statistical summaries (fast, no LLM)
    2. Build optimized prompt (metadata only, no raw data)
    3. Call LLM for structured JSON insights
    4. Parse and validate response
    5. Cache and return
    """
    # Check cache
    if not force_refresh:
        cached = get_cached_insights(session_id)
        if cached:
            return cached

    # Step 1: Compute statistical summary
    stats = _compute_dataset_stats(df, profile)

    # Step 2: Build optimized prompt
    prompt = _build_prompt(df, profile, stats, extra_context)

    # Step 3: Call LLM
    try:
        raw = ai_analyze_json(
            f"{_SYSTEM_PROMPT}\n\n{prompt}\n\nReturn ONLY a valid JSON object. No markdown code blocks."
        )
    except Exception as exc:
        # Fallback: generate insights purely from statistics without LLM
        raw = None
        fallback = _build_fallback_insights(df, profile, stats, str(exc))
        set_cached_insights(session_id, fallback)
        return fallback

    # Step 4: Parse and validate
    insights = _parse_insights(raw, stats)

    # Merge statistical data into insights
    insights["raw_stats"] = stats
    insights["generated_at"] = datetime.now(timezone.utc).isoformat()

    # Step 5: Cache
    set_cached_insights(session_id, insights)

    return insights


def _parse_insights(raw: Any, stats: dict) -> dict[str, Any]:
    """Parse LLM response into structured insights dict."""
    if isinstance(raw, str):
        # Try to clean JSON
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        try:
            raw = json.loads(cleaned)
        except json.JSONDecodeError:
            # Try to find JSON in the response
            start = cleaned.find("{")
            end = cleaned.rfind("}") + 1
            if start >= 0 and end > start:
                try:
                    raw = json.loads(cleaned[start:end])
                except json.JSONDecodeError:
                    raw = {}
            else:
                raw = {}

    if not isinstance(raw, dict):
        raw = {}

    # Validate required fields
    defaults = {
        "dataset_understanding": {
            "purpose": "Dataset analysis",
            "domain": "General",
            "confidence": 50,
            "key_columns": stats.get("numeric_columns", [])[:5],
            "use_cases": ["Data analysis", "Reporting"],
        },
        "executive_summary": {
            "situation": "Dataset loaded and ready for analysis.",
            "key_findings": [],
            "risks": [],
            "opportunities": [],
            "recommendations": [],
        },
        "insights": [],
        "kpis": [],
        "risks": [],
        "ml_recommendations": {
            "target_candidates": [],
            "recommended_tasks": [],
            "feature_engineering": [],
            "algorithms": [],
        },
        "forecast_suggestions": [],
        "data_quality_assessment": {
            "score": 0,
            "status": "unknown",
            "issues": [],
            "treatment_recommendations": [],
        },
    }

    for key, default_val in defaults.items():
        if key not in raw:
            raw[key] = default_val

    # Ensure insights have required fields
    for i, insight in enumerate(raw.get("insights", [])):
        insight.setdefault("id", f"insight_{i+1}")
        insight.setdefault("category", "business")
        insight.setdefault("title", "Insight")
        insight.setdefault("detail", "")
        insight.setdefault("priority", "medium")
        insight.setdefault("impact_score", 5)
        insight.setdefault("evidence", "")
        insight.setdefault("action", "")

    # Ensure KPIs have required fields
    for kpi in raw.get("kpis", []):
        kpi.setdefault("name", "KPI")
        kpi.setdefault("value", "N/A")
        kpi.setdefault("description", "")
        kpi.setdefault("trend", "stable")
        kpi.setdefault("status", "good")

    # Ensure risks have required fields
    for risk in raw.get("risks", []):
        risk.setdefault("title", "Risk")
        risk.setdefault("severity", "medium")
        risk.setdefault("description", "")
        risk.setdefault("impact", "")
        risk.setdefault("mitigation", "")

    return raw


def _build_fallback_insights(df: pd.DataFrame, profile: dict, stats: dict, error: str) -> dict:
    """Build insights purely from statistical analysis when LLM is unavailable."""
    insights_list = []

    # Missing data insights
    if stats["total_missing_pct"] > 10:
        insights_list.append({
            "id": "quality_missing",
            "category": "quality",
            "title": f"High Missing Data: {stats['total_missing_pct']}% overall",
            "detail": f"The dataset has {stats['total_missing_pct']}% missing values across all columns. This significantly impacts analysis reliability.",
            "priority": "critical" if stats["total_missing_pct"] > 30 else "high",
            "impact_score": min(10, int(stats["total_missing_pct"] / 5)),
            "evidence": f"Missing data report shows {len(stats['missing_summary'])} columns affected.",
            "action": "Investigate missing data patterns. Consider imputation or removal strategies.",
        })

    # Duplicate insights
    if stats["duplicate_pct"] > 5:
        insights_list.append({
            "id": "quality_duplicates",
            "category": "quality",
            "title": f"Duplicate Records: {stats['duplicate_rows']:,} ({stats['duplicate_pct']}%)",
            "detail": f"{stats['duplicate_rows']:,} exact duplicate rows found. This inflates counts and skews aggregates.",
            "priority": "high" if stats["duplicate_pct"] > 10 else "medium",
            "impact_score": min(10, int(stats["duplicate_pct"])),
            "evidence": f"{stats['duplicate_rows']:,} rows are exact duplicates.",
            "action": "Review duplicates to determine if they are errors or legitimate repeated records.",
        })

    # Outlier insights
    for col, s in stats.get("numeric_stats", {}).items():
        if s["outlier_count"] > 0 and s["outlier_pct"] > 5:
            insights_list.append({
                "id": f"outlier_{col}",
                "category": "outlier",
                "title": f"Outliers Detected in {col}",
                "detail": f"{col} has {s['outlier_count']:,} outliers ({s['outlier_pct']}%). Range: [{s['min']}, {s['max']}]. IQR: {s['iqr']:.2f}.",
                "priority": "high" if s["outlier_pct"] > 10 else "medium",
                "impact_score": min(10, int(s["outlier_pct"])),
                "evidence": f"IQR method: {s['outlier_count']} values outside [{s['q1'] - 1.5*s['iqr']:.2f}, {s['q3'] + 1.5*s['iqr']:.2f}]",
                "action": f"Investigate {col} outliers. May represent legitimate extreme values or data errors.",
            })

    # Correlation insights
    for p in stats.get("top_correlations", [])[:5]:
        if abs(p["value"]) > 0.7:
            direction = "positive" if p["value"] > 0 else "negative"
            insights_list.append({
                "id": f"corr_{p['feature_a']}_{p['feature_b']}",
                "category": "correlation",
                "title": f"Strong {direction.title()} Correlation: {p['feature_a']} ↔ {p['feature_b']}",
                "detail": f"{p['feature_a']} and {p['feature_b']} have a {p['strength']} {direction} correlation (r={p['value']:.4f}).",
                "priority": "high",
                "impact_score": 7,
                "evidence": f"Pearson correlation coefficient: {p['value']:.4f}",
                "action": f"Analyze the relationship between {p['feature_a']} and {p['feature_b']} for potential causal insights.",
            })

    # Distribution insights
    for d in stats.get("distribution_summary", [])[:5]:
        shape = d.get("shape", {})
        skew = shape.get("skewness", 0)
        if skew and abs(skew) > 1:
            direction = "right" if skew > 0 else "left"
            insights_list.append({
                "id": f"dist_{d['name']}",
                "category": "distribution",
                "title": f"Heavily Skewed Distribution: {d['name']}",
                "detail": f"{d['name']} is heavily {direction}-skewed (skewness={skew:.2f}). Consider transformation for modeling.",
                "priority": "medium",
                "impact_score": 5,
                "evidence": f"Skewness: {skew:.4f}, Kurtosis: {shape.get('kurtosis', 'N/A')}",
                "action": f"Apply log or Box-Cox transformation to {d['name']} to improve normality.",
            })

    # KPI insights
    for k in stats.get("kpi_candidates", [])[:5]:
        col = k["column"]
        ns = stats.get("numeric_stats", {}).get(col, {})
        if ns:
            insights_list.append({
                "id": f"kpi_{col}",
                "category": "kpi",
                "title": f"Key Metric Detected: {col}",
                "detail": f"{col} ({k['detected_type']}) ranges from {ns.get('min', 'N/A')} to {ns.get('max', 'N/A')} with mean {ns.get('mean', 'N/A')}.",
                "priority": "medium",
                "impact_score": 6,
                "evidence": f"Column name matches {k['detected_type']} pattern.",
                "action": f"Monitor {col} as a key performance indicator.",
            })

    # ML readiness
    ml_tasks = []
    if stats["target_candidates"]:
        for t in stats["target_candidates"][:3]:
            ml_tasks.append(f"{t['type']}: {t['column']}")

    quality_score = max(0, 100 - stats["total_missing_pct"] * 2 - stats["duplicate_pct"])

    return {
        "dataset_understanding": {
            "purpose": f"Dataset with {stats['rows']:,} rows and {stats['columns']} columns containing {len(stats['numeric_columns'])} numeric, {len(stats['categorical_columns'])} categorical, and {len(stats['datetime_columns'])} date columns.",
            "domain": "General",
            "confidence": 40,
            "key_columns": stats["numeric_columns"][:5],
            "use_cases": ["Statistical analysis", "Data quality assessment", "Reporting"],
        },
        "executive_summary": {
            "situation": f"Dataset contains {stats['rows']:,} records across {stats['columns']} columns. {stats['total_missing_pct']}% of data is missing. {stats['duplicate_rows']:,} duplicate rows detected.",
            "key_findings": [
                f"{len(stats['numeric_columns'])} numeric and {len(stats['categorical_columns'])} categorical columns detected",
                f"Overall data quality score: {quality_score}/100",
                f"{len(insights_list)} insights generated from statistical analysis",
            ],
            "risks": [
                f"High missing data ({stats['total_missing_pct']}%)" if stats['total_missing_pct'] > 10 else None,
                f"Duplicate records ({stats['duplicate_rows']:,})" if stats['duplicate_rows'] > 0 else None,
            ],
            "opportunities": [
                f"Strong correlations found in {len(stats.get('top_correlations', []))} pairs" if stats.get('top_correlations') else None,
                f"Potential ML targets identified: {', '.join(t['column'] for t in stats['target_candidates'][:3])}" if stats['target_candidates'] else None,
            ],
            "recommendations": [
                "Address missing data before analysis" if stats['total_missing_pct'] > 5 else None,
                "Remove or investigate duplicate records" if stats['duplicate_rows'] > 0 else None,
                "Explore correlations for business insights" if stats.get('top_correlations') else None,
            ],
        },
        "insights": insights_list,
        "kpis": [
            {
                "name": k["column"],
                "value": stats.get("numeric_stats", {}).get(k["column"], {}).get("mean", "N/A"),
                "description": f"Detected as {k['detected_type']} metric",
                "trend": "stable",
                "status": "good",
            }
            for k in stats.get("kpi_candidates", [])[:5]
        ],
        "risks": [
            {
                "title": "High Missing Data",
                "severity": "critical" if stats["total_missing_pct"] > 30 else "high" if stats["total_missing_pct"] > 10 else "medium",
                "description": f"{stats['total_missing_pct']}% of values are missing across the dataset.",
                "impact": "Reduces data reliability and may introduce bias in analysis.",
                "mitigation": "Impute missing values or remove affected columns/rows based on analysis requirements.",
            }
        ] if stats["total_missing_pct"] > 5 else [],
        "ml_recommendations": {
            "target_candidates": [t["column"] for t in stats["target_candidates"][:5]],
            "recommended_tasks": list(set(t["type"] for t in stats["target_candidates"][:5])),
            "feature_engineering": [
                f"Encode {col} ({stats['categorical_stats'].get(col, {}).get('unique_count', 0)} categories)"
                for col in stats["categorical_columns"][:5]
            ],
            "algorithms": ["Random Forest", "XGBoost", "Logistic Regression"],
        },
        "forecast_suggestions": [
            {
                "column": col,
                "metric": "Any numeric column",
                "method": "ARIMA / Prophet",
                "reason": f"Date column '{col}' spans {stats['date_stats'][col]['range_days']} days",
            }
            for col in list(stats.get("date_stats", {}).keys())[:3]
        ],
        "data_quality_assessment": {
            "score": quality_score,
            "status": "excellent" if quality_score >= 90 else "good" if quality_score >= 70 else "fair" if quality_score >= 50 else "poor",
            "issues": (
                [f"{stats['total_missing_pct']}% missing data"] if stats['total_missing_pct'] > 5 else []
            ) + (
                [f"{stats['duplicate_rows']:,} duplicate rows"] if stats['duplicate_rows'] > 0 else []
            ),
            "treatment_recommendations": (
                ["Impute or remove missing values"] if stats['total_missing_pct'] > 5 else []
            ) + (
                ["Review and remove duplicates"] if stats['duplicate_rows'] > 0 else []
            ),
        },
        "raw_stats": stats,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "fallback_mode": True,
        "fallback_reason": error,
    }
