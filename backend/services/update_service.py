"""Update service — natural language driven row updates (MVP).

MVP approach:
- Use Groq to convert natural language to a strict JSON update spec.
- Validate referenced columns exist in SQLite schema.
- Validate target condition columns exist.
- Execute update using parameterized SQL.

This is an MVP: complex multi-condition matching is supported only if the
LLM produces a parseable spec.
"""

from __future__ import annotations

from typing import Any

from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.utils.active_dataset_store import get_active_connection


_client = Groq(api_key=GROQ_API_KEY)


_SYSTEM = """
You convert user natural language into a strict JSON update spec.
Rules:
- Output ONLY valid JSON.
- Include:
  - "set": object mapping EXACT existing column names -> new values
  - "where": object with fields:
       * "column": EXACT existing column name used for matching
       * "op": one of: "=", "!=", "<", "<=", ">", ">=", "like"
       * "value": value for comparison (JSON type)
  - "affectedRowsHint" optional integer.
- Only use columns that exist in ACTIVE SCHEMA.
"""


def _call_llm(*, question: str, schema: str) -> dict[str, Any]:
    prompt = _SYSTEM + "\nACTIVE SCHEMA:\n" + schema
    resp = _client.chat.completions.create(
        model=GROQ_MODEL,
        messages=[
            {"role": "system", "content": prompt},
            {"role": "user", "content": question},
        ],
        temperature=0.0,
    )
    txt = resp.choices[0].message.content.strip()
    return __import__("json").loads(txt)


def update_rows(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)
    set_obj = spec.get("set") or {}
    where_obj = spec.get("where") or {}

    if not isinstance(set_obj, dict) or not set_obj:
        raise ValueError("Update spec missing 'set'.")
    if not isinstance(where_obj, dict) or not where_obj:
        raise ValueError("Update spec missing 'where'.")

    where_col = where_obj.get("column")
    where_op = where_obj.get("op")
    where_val = where_obj.get("value")

    if not where_col or where_op not in {"=", "!=", "<", "<=", ">", ">=", "like"}:
        raise ValueError("Invalid where clause in update spec.")

    conn = get_active_connection()
    try:
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(dataset)").fetchall()]
        col_set = set(cols)

        for k in set_obj.keys():
            if k not in col_set:
                raise ValueError(f"Unknown column in set: {k}")
        if where_col not in col_set:
            raise ValueError(f"Unknown where column: {where_col}")

        set_keys = list(set_obj.keys())
        set_expr = ", ".join([f'"{k}" = ?' for k in set_keys])

        if where_op == "like":
            sql = f"UPDATE dataset SET {set_expr} WHERE LOWER(\"{where_col}\") LIKE LOWER(?)"
            params = [set_obj[k] for k in set_keys] + [str(where_val)]
        else:
            sql = f"UPDATE dataset SET {set_expr} WHERE \"{where_col}\" {where_op} ?"
            params = [set_obj[k] for k in set_keys] + [where_val]

        cur.execute(sql, params)
        affected = int(cur.rowcount or 0)
        conn.commit()
        return {"updatedRows": affected}
    finally:
        conn.close()

