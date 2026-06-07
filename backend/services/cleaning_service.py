"""Cleaning service — MVP cleaning operations.

Currently supports:
- fill_nulls: set NULL to a provided literal for a column OR compute average for numeric.
- trim_spaces: trim TEXT columns.
- uppercase: transform text casing.

More advanced operations (remove duplicates, remove null rows) can be
added in the same transformation approach.
"""

from __future__ import annotations

from typing import Any

from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.utils.active_dataset_store import get_active_connection


_client = Groq(api_key=GROQ_API_KEY)


_SYSTEM = """
Convert natural language to a strict JSON cleaning spec.
Output ONLY valid JSON.
Supported operations (choose one):
1) {"operation":"trimSpaces", "columns":[EXISTING_COLS_OR_EMPTY_FOR_ALL_TEXT]}
2) {"operation":"uppercase", "columns":[EXISTING_COLS_OR_EMPTY_FOR_ALL_TEXT]}
3) {"operation":"fillNulls", "column": EXISTING_COL_OR_ASTERISK_FOR_ALL, "strategy": "average"|"literal", "value": literal_if_needed, "columns": [LIST_OF_COLS_IF_MULTIPLE]}
4) {"operation":"removeNullRows"}
5) {"operation":"removeDuplicates", "subset": [EXISTING_COLS] }

Only use existing columns from ACTIVE SCHEMA.
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


def clean(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)
    op = spec.get("operation")
    if not op:
        raise ValueError("Missing operation in cleaning spec")

    conn = get_active_connection()
    try:
        cols = conn.execute("PRAGMA table_info(dataset)").fetchall()
        col_names = [r[1] for r in cols]
        col_types = {r[1]: (r[2] or "TEXT").upper() for r in cols}

        if op == "trimSpaces":
            targets = spec.get("columns") or []
            if not targets:
                targets = [c for c in col_names if col_types[c] not in {"INTEGER", "REAL"}]
            affected = 0
            for c in targets:
                conn.execute(f'UPDATE dataset SET "{c}" = TRIM(CAST("{c}" AS TEXT)) WHERE "{c}" IS NOT NULL')
                affected += conn.total_changes
            conn.commit()
            return {"cleaned": True, "operation": op}

        if op == "uppercase":
            targets = spec.get("columns") or []
            if not targets:
                targets = [c for c in col_names if col_types[c] not in {"INTEGER", "REAL"}]
            for c in targets:
                conn.execute(f'UPDATE dataset SET "{c}" = UPPER(CAST("{c}" AS TEXT)) WHERE "{c}" IS NOT NULL')
            conn.commit()
            return {"cleaned": True, "operation": op}

        if op == "fillNulls":
            column = spec.get("column")
            columns = spec.get("columns")
            strategy = spec.get("strategy")
            value = spec.get("value")

            targets = []
            if columns:
                targets = [c for c in columns if c in col_names]
            elif column in ("*", "all", "ALL", None):
                targets = col_names
            else:
                targets = [column] if column in col_names else []

            for col in targets:
                if strategy == "average":
                    if col_types[col] in {"INTEGER", "REAL"}:
                        conn.execute(
                            f'UPDATE dataset SET "{col}" = (SELECT AVG("{col}") FROM dataset) '
                            f'WHERE "{col}" IS NULL'
                        )
                else:
                    conn.execute(f'UPDATE dataset SET "{col}" = ? WHERE "{col}" IS NULL', (value,))
            conn.commit()
            return {"cleaned": True, "operation": op, "columns": targets}

        if op == "removeNullRows":
            conn.execute("DELETE FROM dataset WHERE "+" OR ".join([f'"{c}" IS NULL' for c in col_names]))
            affected = int(conn.total_changes)
            conn.commit()
            return {"cleaned": True, "operation": op, "affectedRows": affected}

        if op == "removeDuplicates":
            subset = spec.get("subset") or []
            if not subset:
                subset = col_names
            for c in subset:
                if c not in col_names:
                    raise ValueError(f"Unknown column in subset: {c}")

            tmp = "dataset__tmp__"
            conn.execute(f"DROP TABLE IF EXISTS {tmp}")
            subset_expr = ", ".join([f'"{c}"' for c in subset])
            conn.execute(f"CREATE TABLE {tmp} AS SELECT * FROM dataset")
            # MVP rebuild using DISTINCT on subset: keep first occurrence via rowid.
            conn.execute(f"DELETE FROM {tmp}")
            # Insert kept rows
            conn.execute(
                f"""
                INSERT INTO {tmp}
                SELECT * FROM dataset
                WHERE rowid IN (
                  SELECT MIN(rowid) FROM dataset GROUP BY {subset_expr}
                )
                """
            )
            conn.execute("DROP TABLE dataset")
            conn.execute(f"ALTER TABLE {tmp} RENAME TO dataset")
            conn.commit()
            return {"cleaned": True, "operation": op}

        raise ValueError(f"Unsupported cleaning operation: {op}")

    finally:
        conn.close()

