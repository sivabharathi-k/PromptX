"""Delete service — natural language driven deletes (MVP)."""

from __future__ import annotations

from typing import Any

from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.utils.active_dataset_store import get_active_connection


_client = Groq(api_key=GROQ_API_KEY)


_SYSTEM = """
You convert user natural language into a strict JSON delete spec.
Rules:
- Output ONLY valid JSON.
- Include either:
  1) "where" clause object: {"column": EXISTING_COL, "op": one of [ '=', '!=', '<', '<=', '>', '>=', 'like' ], "value": value}
  2) or "dedupe": {"column": EXISTING_COL} to remove duplicates.
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


def preview_delete(*, question: str, schema: str, limit: int = 50) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)

    conn = get_active_connection()
    try:
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(dataset)").fetchall()]

        if "where" not in spec:
            raise ValueError("MVP preview supports only where-based deletes.")

        where = spec["where"]
        where_col = where["column"]
        where_op = where["op"]
        where_val = where.get("value")

        set_check = where_col in cols
        if not set_check:
            raise ValueError(f"Unknown where column: {where_col}")

        if where_op == "like":
            sql = f"SELECT * FROM dataset WHERE LOWER(\"{where_col}\") LIKE LOWER(?) LIMIT {int(limit)}"
            params = [str(where_val)]
        else:
            sql = f"SELECT * FROM dataset WHERE \"{where_col}\" {where_op} ? LIMIT {int(limit)}"
            params = [where_val]

        rows = cur.execute(sql, params).fetchall()
        # Need column order for dicts
        col_names = cols
        row_dicts = [dict(zip(col_names, r)) for r in rows]

        # total count
        if where_op == "like":
            count_sql = f"SELECT COUNT(*) FROM dataset WHERE LOWER(\"{where_col}\") LIKE LOWER(?)"
        else:
            count_sql = f"SELECT COUNT(*) FROM dataset WHERE \"{where_col}\" {where_op} ?"

        total = cur.execute(count_sql, params).fetchone()[0]

        return {"affectedRows": int(total), "previewRows": row_dicts}
    finally:
        conn.close()


def delete_rows(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)

    conn = get_active_connection()
    try:
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(dataset)").fetchall()]

        if "where" not in spec:
            raise ValueError("MVP delete supports only where-based deletes.")

        where = spec["where"]
        where_col = where["column"]
        where_op = where["op"]
        where_val = where.get("value")

        if where_col not in cols:
            raise ValueError(f"Unknown where column: {where_col}")

        if where_op == "like":
            sql = f"DELETE FROM dataset WHERE LOWER(\"{where_col}\") LIKE LOWER(?)"
            params = [str(where_val)]
        else:
            sql = f"DELETE FROM dataset WHERE \"{where_col}\" {where_op} ?"
            params = [where_val]

        cur.execute(sql, params)
        affected = int(cur.rowcount or 0)
        conn.commit()
        return {"deletedRows": affected}
    finally:
        conn.close()

