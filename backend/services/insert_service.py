"""Insert service — natural language driven row inserts (MVP)."""

from __future__ import annotations

import re
import sqlite3
from typing import Any

import pandas as pd
from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.utils.active_dataset_store import get_active_connection


_client = Groq(api_key=GROQ_API_KEY)


_SYSTEM = """
You convert user natural language into a strict JSON insert spec.
Rules:
- Output ONLY valid JSON. No markdown.
- Include:
  - "values": an object mapping EXACT existing column names to values.
  - "affectedRowsHint": number the model expects to be inserted (usually 1).
- Only use column names that exist in ACTIVE SCHEMA provided.
- If user implies multiple rows, output multiple inserted rows as:
  - "rows": [ {col: value, ...}, ... ]
  - Otherwise use "rows" with length 1.
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


def insert_rows(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)
    rows = spec.get("rows")
    if not rows or not isinstance(rows, list):
        # support single-row form
        if "values" in spec:
            rows = [spec["values"]]
        else:
            raise ValueError("Insert spec missing 'rows'.")

    conn = get_active_connection()
    try:
        cur = conn.cursor()

        # Determine existing columns
        cols = [r[1] for r in cur.execute("PRAGMA table_info(dataset)").fetchall()]
        col_set = set(cols)

        inserted = 0
        for row in rows:
            if not isinstance(row, dict):
                raise ValueError("Each row must be an object of column->value")
            clean = {k: v for k, v in row.items() if k in col_set}
            if not clean:
                continue

            keys = list(clean.keys())
            placeholders = ",".join(["?"] * len(keys))
            quoted_cols = ",".join([f'"{k}"' for k in keys])
            sql = f"INSERT INTO dataset ({quoted_cols}) VALUES ({placeholders})"
            cur.execute(sql, [clean[k] for k in keys])
            inserted += 1

        conn.commit()
        return {"insertedRows": inserted}
    finally:
        conn.close()

