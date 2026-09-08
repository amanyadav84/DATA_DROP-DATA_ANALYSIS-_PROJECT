"""SQL Generator — natural language to SQL queries."""

from __future__ import annotations

from typing import Any

from ai_service import ai_analyze
from processor import profile_dataframe


def _build_sql_prompt(profile: dict, question: str, dialect: str) -> str:
    """Build prompt for SQL generation."""
    col_info = []
    for c in profile["columns"]:
        info = f'{c["name"]} {c["type"].upper()}'
        if c["type"] == "numeric":
            info += f' (min={c.get("min")}, max={c.get("max")})'
        col_info.append(info)

    return f"""You are a SQL expert. Write a SQL query to answer the user's question.

TABLE: data (the uploaded dataset)
COLUMNS:
{chr(10).join('  - ' + info for info in col_info)}

SQL DIALECT: {dialect}

RULES:
1. Write ONLY the SQL query. No explanation before or after.
2. Use the table name "data".
3. Use actual column names from the dataset.
4. For aggregations, use appropriate GROUP BY.
5. Use ORDER BY for ranking queries.
6. Use LIMIT for top N queries (default 100).
7. Handle NULLs appropriately.
8. Use double quotes for column names if they contain spaces.

Return ONLY valid JSON:
{{
  "sql": "SELECT ...",
  "explanation": "brief explanation"
}}"""


def generate_sql(df, profile: dict, question: str, dialect: str = "MySQL") -> dict[str, Any]:
    """Generate SQL from natural language question."""
    prompt = _build_sql_prompt(profile, question, dialect)

    try:
        raw = ai_analyze(prompt, temperature=0.1, max_tokens=1024)
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
            "sql": parsed.get("sql", ""),
            "explanation": parsed.get("explanation", ""),
            "dialect": dialect,
        }
    except json.JSONDecodeError:
        start = raw.find("{")
        end = raw.rfind("}") + 1
        if start >= 0 and end > start:
            try:
                parsed = json.loads(raw[start:end])
                return {"success": True, "sql": parsed.get("sql", ""), "explanation": parsed.get("explanation", ""), "dialect": dialect}
            except json.JSONDecodeError:
                pass
        return {"success": False, "error": "Could not parse AI response", "raw": raw}
