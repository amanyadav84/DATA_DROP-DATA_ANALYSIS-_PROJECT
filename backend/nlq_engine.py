"""Natural Language Query engine — understand questions, generate Pandas code, execute safely."""

from __future__ import annotations

import traceback
from typing import Any

import numpy as np
import pandas as pd

from ai_service import ai_analyze
from processor import detect_column_type, profile_dataframe


# ---------------------------------------------------------------------------
# Prompt builder
# ---------------------------------------------------------------------------

def _build_nlq_prompt(df: pd.DataFrame, profile: dict, question: str) -> str:
    """Build an optimized prompt for natural language to Pandas conversion."""
    numeric_cols = [c["name"] for c in profile["columns"] if c["type"] == "numeric"]
    cat_cols = [c["name"] for c in profile["columns"] if c["type"] == "categorical"]
    date_cols = [c["name"] for c in profile["columns"] if c["type"] == "datetime"]

    col_info = []
    for c in profile["columns"]:
        info = f'{c["name"]} ({c["type"]}'
        if c["type"] == "numeric":
            info += f', min={c.get("min")}, max={c.get("max")}, mean={c.get("mean")}'
        elif c["type"] == "categorical":
            top = c.get("top_values", [])[:3]
            info += f', top={top}'
        info += ')'
        col_info.append(info)

    return f"""You are a Python Pandas expert. Given a dataset, write Python code to answer the user's question.

DATASET INFO:
- Shape: {df.shape[0]} rows x {df.shape[1]} columns
- Columns: {', '.join(col_info)}

COLUMN TYPES:
- Numeric: {', '.join(numeric_cols) or 'None'}
- Categorical: {', '.join(cat_cols) or 'None'}
- DateTime: {', '.join(date_cols) or 'None'}

RULES:
1. Write ONLY the Pandas code. No imports needed (pandas as pd, numpy as np are available).
2. The variable `df` is already loaded as a DataFrame.
3. Store the result in a variable called `result`.
4. For charts, create a Plotly figure and store in `chart_spec` as a dict.
5. For text answers, store in `answer` as a string.
6. Use actual column names from the dataset.
7. Never hallucinate column names.
8. For aggregations, always show the actual computed values.
9. Handle edge cases (empty results, division by zero, etc.).

OUTPUT FORMAT — return a JSON object:
{{
  "code": "the pandas code",
  "explanation": "brief explanation of what the code does",
  "answer_hint": "what type of result to expect: table, chart, number, text"
}}

Return ONLY valid JSON. No markdown code blocks."""


# ---------------------------------------------------------------------------
# Code executor
# ---------------------------------------------------------------------------

def _execute_code(df: pd.DataFrame, code: str) -> dict[str, Any]:
    """Safely execute generated Pandas code."""
    local_vars = {"df": df.copy(), "pd": pd, "np": np}
    result = {"success": False, "output": None, "chart_spec": None, "error": None}

    try:
        exec(code, {"__builtins__": {}}, local_vars)

        if "result" in local_vars:
            r = local_vars["result"]
            if isinstance(r, pd.DataFrame):
                result["output"] = {
                    "type": "dataframe",
                    "columns": list(r.columns),
                    "rows": r.head(50).to_dict(orient="records"),
                    "shape": list(r.shape),
                }
            elif isinstance(r, pd.Series):
                result["output"] = {
                    "type": "series",
                    "name": str(r.name),
                    "data": r.head(50).to_dict(),
                }
            elif isinstance(r, (int, float, np.integer, np.floating)):
                result["output"] = {"type": "number", "value": float(r)}
            elif isinstance(r, str):
                result["output"] = {"type": "text", "value": r}
            elif isinstance(r, dict):
                result["output"] = {"type": "dict", "data": r}
            elif isinstance(r, list):
                result["output"] = {"type": "list", "data": r}
            else:
                result["output"] = {"type": "text", "value": str(r)}

        if "chart_spec" in local_vars:
            chart = local_vars["chart_spec"]
            if isinstance(chart, dict):
                result["chart_spec"] = chart

        if "answer" in local_vars:
            if result["output"] is None:
                result["output"] = {"type": "text", "value": str(local_vars["answer"])}

        result["success"] = True

    except Exception as exc:
        result["error"] = f"{type(exc).__name__}: {exc}"
        result["traceback"] = traceback.format_exc()

    return result


# ---------------------------------------------------------------------------
# Main NLQ engine
# ---------------------------------------------------------------------------

def process_question(df: pd.DataFrame, profile: dict, question: str) -> dict[str, Any]:
    """Process a natural language question about the dataset."""
    prompt = _build_nlq_prompt(df, profile, question)

    try:
        raw = ai_analyze(prompt, temperature=0.1, max_tokens=2048)
    except Exception as exc:
        return {
            "success": False,
            "question": question,
            "error": f"AI service unavailable: {exc}",
            "code": None,
            "explanation": None,
            "output": None,
            "chart_spec": None,
        }

    # Parse AI response
    import json
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        cleaned = cleaned.strip()
        parsed = json.loads(cleaned)
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start:end])
            except json.JSONDecodeError:
                return {
                    "success": False,
                    "question": question,
                    "error": "Could not parse AI response",
                    "raw_response": raw,
                    "code": None,
                    "explanation": None,
                    "output": None,
                    "chart_spec": None,
                }
        else:
            return {
                "success": False,
                "question": question,
                "error": "AI response was not valid JSON",
                "raw_response": raw,
                "code": None,
                "explanation": None,
                "output": None,
                "chart_spec": None,
            }

    code = parsed.get("code", "")
    explanation = parsed.get("explanation", "")

    if not code:
        return {
            "success": False,
            "question": question,
            "error": "AI did not generate code",
            "code": None,
            "explanation": explanation,
            "output": None,
            "chart_spec": None,
        }

    # Execute the code
    exec_result = _execute_code(df, code)

    return {
        "success": exec_result["success"],
        "question": question,
        "code": code,
        "explanation": explanation,
        "output": exec_result.get("output"),
        "chart_spec": exec_result.get("chart_spec"),
        "error": exec_result.get("error"),
    }


# ---------------------------------------------------------------------------
# Query suggestions
# ---------------------------------------------------------------------------

def suggest_questions(profile: dict) -> list[str]:
    """Suggest relevant questions based on dataset structure."""
    numeric_cols = [c["name"] for c in profile["columns"] if c["type"] == "numeric"]
    cat_cols = [c["name"] for c in profile["columns"] if c["type"] == "categorical"]
    date_cols = [c["name"] for c in profile["columns"] if c["type"] == "datetime"]

    suggestions = []

    if numeric_cols:
        suggestions.extend([
            f"What is the average of {numeric_cols[0]}?",
            f"What is the distribution of {numeric_cols[0]}?",
            f"What are the top 10 values of {numeric_cols[0]}?",
        ])
    if cat_cols:
        suggestions.extend([
            f"What are the unique values in {cat_cols[0]}?",
            f"How many records per {cat_cols[0]}?",
            f"Show the top 5 {cat_cols[0]} by count",
        ])
    if date_cols and numeric_cols:
        suggestions.extend([
            f"Show {numeric_cols[0]} over time by {date_cols[0]}",
            f"What is the monthly trend of {numeric_cols[0]}?",
        ])
    if len(numeric_cols) >= 2:
        suggestions.append(f"Show correlation between {numeric_cols[0]} and {numeric_cols[1]}")
    if cat_cols and numeric_cols:
        suggestions.append(f"What is the average {numeric_cols[0]} by {cat_cols[0]}?")

    return suggestions[:8]
