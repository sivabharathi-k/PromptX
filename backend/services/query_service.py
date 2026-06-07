"""
Query service — universal natural language to SQL engine powered by Groq.
"""

import re
import sqlite3

import pandas as pd
from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL

_client = Groq(api_key=GROQ_API_KEY)

_SYSTEM_PROMPT = """You are a SQLite SQL expert. The ONLY table is "dataset".

ACTIVE SCHEMA:
{schema}

RULES:
- Return ONLY a valid SQLite SELECT query. No explanation, no markdown, no code fences.
- Use ONLY column names from the schema above. Double-quote every column name.
- Table name is always: dataset
- Never use: DROP, DELETE, UPDATE, ALTER, INSERT, TRUNCATE, ATTACH.
- LIMIT 50 for general row queries.
- Map user words to actual schema columns (e.g. "revenue" -> find the money-related column in schema).
- Handle informal/multilingual queries by inferring intent.
"""


def _clean_sql(sql: str) -> str:
    """Strip markdown fences, language tags, and surrounding whitespace."""
    sql = re.sub(r"```sql\s*", "", sql.strip())
    sql = re.sub(r"```\s*",    "", sql).strip()
    # Remove any accidental leading prose before SELECT/WITH
    match = re.search(r"(SELECT|WITH)\b", sql, re.IGNORECASE)
    if match:
        sql = sql[match.start():]
    return sql.strip()


def _validate_sql(sql: str, conn: sqlite3.Connection) -> tuple[bool, str]:
    """
    Validate SQL before execution:
    - Rejects dangerous statements
    - Confirms reference to 'dataset' table
    - Uses EXPLAIN to catch syntax errors without executing
    Returns (is_valid, error_message).
    """
    upper = sql.upper().strip()

    for keyword in ("DROP", "DELETE", "UPDATE", "ALTER", "INSERT", "TRUNCATE", "ATTACH"):
        if re.search(rf"\b{keyword}\b", upper):
            return False, f"Disallowed SQL keyword: {keyword}"

    if "DATASET" not in upper:
        return False, "SQL does not reference the 'dataset' table."

    try:
        conn.execute(f"EXPLAIN {sql}")
        return True, ""
    except sqlite3.Error as e:
        return False, str(e)


def _call_llm(messages: list) -> str:
    """Send messages to Groq and return the stripped response."""
    response = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=messages,
        temperature=0.0,
        max_tokens=300,
    )
    return response.choices[0].message.content.strip()


def generate_sql(question: str, schema: str) -> str:
    """Convert a natural language question into a valid SQLite query."""
    prompt = _SYSTEM_PROMPT.format(schema=schema)
    return _clean_sql(_call_llm([
        {"role": "system", "content": prompt},
        {"role": "user",   "content": question},
    ]))


def execute_sql(
    sql: str,
    conn: sqlite3.Connection,
    question: str = "",
    schema:   str = "",
) -> tuple[pd.DataFrame | None, str | None]:
    """
    Validate then execute SQL.
    On validation failure or runtime error, ask the LLM to self-correct once.
    Returns (DataFrame, None) on success or (None, error_message) on failure.
    """
    valid, val_err = _validate_sql(sql, conn)

    if valid:
        try:
            return pd.read_sql(sql, conn), None
        except Exception as exec_err:
            first_err = str(exec_err)
    else:
        first_err = val_err

    # ── Self-correction pass ───────────────────────────────────
    if not question or not schema:
        return None, first_err

    fix_messages = [
        {"role": "system",    "content": _SYSTEM_PROMPT.format(schema=schema)},
        {"role": "user",      "content": question},
        {"role": "assistant", "content": sql},
        {"role": "user",      "content": (
            f"That SQL failed with this error:\n{first_err}\n\n"
            "Fix the mistake. Use only column names from the ACTIVE DATASET SCHEMA. "
            "Return ONLY the corrected SQL query."
        )},
    ]
    try:
        fixed_sql        = _clean_sql(_call_llm(fix_messages))
        valid2, val_err2 = _validate_sql(fixed_sql, conn)
        if not valid2:
            return None, val_err2
        return pd.read_sql(fixed_sql, conn), None
    except Exception as second_err:
        return None, str(second_err)
