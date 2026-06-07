"""Transformation service — MVP subset of AI spreadsheet operations.

Supports:
- find & replace (string / literal)
- bulk numeric/text updates (set via Groq spec)

For MVP, we implement a structured spec with controlled SQL where possible.
Advanced calculated columns and filter+save can be added following the same
pattern.
"""

from __future__ import annotations

from typing import Any

from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.utils.active_dataset_store import get_active_connection


_client = Groq(api_key=GROQ_API_KEY)


_SYSTEM = """
Convert user transformation request into strict JSON.
Output ONLY JSON.
Supported operations:
1) findReplace:
   {"operation":"findReplace", "column": EXISTING_COL_OR_ANY_TEXT, "from": OLD, "to": NEW}
   - If column is "*" then apply across all TEXT columns.
2) bulkTransform:
   {"operation":"bulkTransform", "column": EXISTING_COL, "expression": "ADD","SUB","MUL","DIV" or "UPPER" or "LOWER" , "value": number_or_string }
3) calculatedColumn:
   {"operation":"calculatedColumn", "newColumnName": NEW_COL, "type": "TEXT"|"INTEGER"|"REAL", "expression": SQL_EXPRESSION}
   - The expression must be a valid SQLite expression using existing column names wrapped in double quotes.
   - Example: "Create a Full_Name column using First_Name + Last_Name" -> {"operation": "calculatedColumn", "newColumnName": "Full_Name", "type": "TEXT", "expression": "\"First_Name\" || ' ' || \"Last_Name\""}
   - Example: "Create Profit = Revenue - Cost" -> {"operation": "calculatedColumn", "newColumnName": "Profit", "type": "REAL", "expression": "\"Revenue\" - \"Cost\""}

Only use existing columns from ACTIVE SCHEMA.
For safety, keep transformations limited to these operations.
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


def transform(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)
    op = spec.get("operation")

    conn = get_active_connection()
    try:
        cols = conn.execute("PRAGMA table_info(dataset)").fetchall()
        col_names = [r[1] for r in cols]
        col_types = {r[1]: (r[2] or "TEXT").upper() for r in cols}

        if op == "findReplace":
            column = spec.get("column")
            from_v = spec.get("from")
            to_v = spec.get("to")
            if column in ("*", "ALL", "all"):
                targets = [c for c in col_names if col_types[c] not in {"INTEGER", "REAL"}]
            else:
                if column not in col_names:
                    raise ValueError(f"Unknown column: {column}")
                targets = [column]

            total_updated = 0
            for c in targets:
                # Replace exact match first
                cur = conn.execute(
                    f'UPDATE dataset SET "{c}" = ? WHERE "{c}" = ?'
                    ,(to_v, from_v)
                )
                total_updated += int(conn.total_changes)
            conn.commit()
            return {"transformed": True, "operation": op, "updatedCellsApprox": total_updated}

        if op == "bulkTransform":
            column = spec.get("column")
            expression = str(spec.get("expression") or "").upper()
            value = spec.get("value")

            if column not in col_names:
                raise ValueError(f"Unknown column: {column}")

            if expression == "UPPER":
                conn.execute(f'UPDATE dataset SET "{column}" = UPPER(CAST("{column}" AS TEXT))')
            elif expression == "LOWER":
                conn.execute(f'UPDATE dataset SET "{column}" = LOWER(CAST("{column}" AS TEXT))')
            else:
                # numeric ops
                if expression not in {"ADD", "SUB", "MUL", "DIV"}:
                    raise ValueError("Unsupported bulk transform expression")
                if expression == "ADD":
                    conn.execute(f'UPDATE dataset SET "{column}" = "{column}" + ?',(value,))
                elif expression == "SUB":
                    conn.execute(f'UPDATE dataset SET "{column}" = "{column}" - ?',(value,))
                elif expression == "MUL":
                    conn.execute(f'UPDATE dataset SET "{column}" = "{column}" * ?',(value,))
                elif expression == "DIV":
                    conn.execute(f'UPDATE dataset SET "{column}" = "{column}" / ?',(value,))

            conn.commit()
            return {"transformed": True, "operation": op}

        if op == "calculatedColumn":
            new_col = spec.get("newColumnName")
            col_type = (spec.get("type") or "TEXT").upper()
            expression = spec.get("expression")

            if not new_col or not expression:
                raise ValueError("Missing newColumnName or expression for calculatedColumn")

            # 1. Add column if it doesn't exist
            if new_col not in col_names:
                conn.execute(f'ALTER TABLE dataset ADD COLUMN "{new_col}" {col_type}')

            # 2. Update it using the expression
            conn.execute(f'UPDATE dataset SET "{new_col}" = {expression}')
            conn.commit()
            return {"transformed": True, "operation": op, "column": new_col}

        raise ValueError(f"Unsupported transform operation: {op}")

    finally:
        conn.close()

