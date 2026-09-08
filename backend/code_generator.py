"""Python Code Generator — natural language to production-ready Pandas/NumPy code."""

from __future__ import annotations

from typing import Any

from ai_service import ai_analyze
from processor import profile_dataframe


def _build_code_prompt(profile: dict, question: str) -> str:
    """Build prompt for Python code generation."""
    numeric_cols = [c["name"] for c in profile["columns"] if c["type"] == "numeric"]
    cat_cols = [c["name"] for c in profile["columns"] if c["type"] == "categorical"]
    date_cols = [c["name"] for c in profile["columns"] if c["type"] == "datetime"]

    col_info = []
    for c in profile["columns"]:
        info = f'{c["name"]} ({c["type"]}'
        if c["type"] == "numeric":
            info += f', min={c.get("min")}, max={c.get("max")}, mean={c.get("mean")}'
        col_info.append(info)

    return f"""You are a senior Python data scientist. Write production-ready code to answer the user's question.

DATASET: `df` is a pandas DataFrame with {profile['n_rows']} rows and {profile['n_cols']} columns.
COLUMNS: {', '.join(col_info)}

AVAILABLE LIBRARIES:
- pandas (as pd)
- numpy (as np)
- matplotlib.pyplot (as plt)
- seaborn (as sns)
- plotly.express (as px)
- plotly.graph_objects (as go)
- scipy.stats (as sp_stats)
- sklearn.preprocessing (StandardScaler, MinMaxScaler, LabelEncoder, OneHotEncoder)

RULES:
1. Write clean, well-structured code with proper variable names.
2. Include comments explaining key steps.
3. Store the DataFrame result in `result` variable.
4. For charts, create a Plotly figure and store in `chart_spec`.
5. For text answers, store in `answer`.
6. Use actual column names from the dataset.
7. Handle edge cases (empty data, type errors, etc.).
8. Production-ready: handle warnings, use context managers where appropriate.

Return ONLY valid JSON:
{{
  "code": "the Python code",
  "explanation": "what the code does step by step",
  "imports_needed": ["list", "of", "extra", "imports"]
}}"""


def generate_code(df, profile: dict, question: str) -> dict[str, Any]:
    """Generate Python code from natural language question."""
    prompt = _build_code_prompt(profile, question)

    try:
        raw = ai_analyze(prompt, temperature=0.1, max_tokens=3000)
    except Exception as exc:
        return {"success": False, "error": f"AI service unavailable: {exc}"}

    import json
    try:
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            cleaned = cleaned.split("\n", 1)[-1]
        if cleaned.endswith("```"):
            cleaned = cleaned.rsplit("```", 1)[0]
        parsed = json.loads(cleaned.strip())
        return {
            "success": True,
            "code": parsed.get("code", ""),
            "explanation": parsed.get("explanation", ""),
            "imports_needed": parsed.get("imports_needed", []),
        }
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start:end])
                return {"success": True, "code": parsed.get("code", ""), "explanation": parsed.get("explanation", ""), "imports_needed": parsed.get("imports_needed", [])}
            except json.JSONDecodeError:
                pass
        return {"success": False, "error": "Could not parse AI response", "raw": raw}
