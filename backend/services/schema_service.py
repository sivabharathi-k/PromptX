"""Schema service — add/remove/rename columns (MVP).

SQLite ALTER TABLE limitations mean we implement schema changes via
rebuild strategy for MVP.

We support:
- add_column: add a new nullable column
- rename_column: recreate table with renamed column
- remove_column: recreate table without the removed column

Natural language is converted into a strict JSON spec via Groq.
"""

from __future__ import annotations

from typing import Any

from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.utils.active_dataset_store import get_active_connection


_client = Groq(api_key=GROQ_API_KEY)


_SYSTEM = """
You convert user natural language into a strict JSON schema edit spec.
Rules:
- Output ONLY valid JSON.
- Include one operation key:
  - "addColumn": {"name": EXISTING_OR_NEW_COL, "type": "TEXT"|"INTEGER"|"REAL"}
  - "renameColumn": {"oldName": EXISTING_COL, "newName": NEW_COL}
  - "removeColumn": {"name": EXISTING_COL}
- Only use columns that exist in ACTIVE SCHEMA for rename/remove.
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


def _get_cols(conn) -> list[tuple[str, str | None]]:
    return [(r[1], r[2]) for r in conn.execute("PRAGMA table_info(dataset)").fetchall()]


def add_column(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)
    add = spec.get("addColumn")
    if not add:
        raise ValueError("Schema spec missing addColumn")

    name = add["name"]
    col_type = (add.get("type") or "TEXT").upper()
    if col_type not in {"TEXT", "INTEGER", "REAL"}:
        col_type = "TEXT"

    conn = get_active_connection()
    try:
        cols = [c[0] for c in _get_cols(conn)]
        if name in cols:
            return {"added": False, "reason": "Column already exists", "column": name}
        # SQLite supports ADD COLUMN without rebuild.
        conn.execute(f'ALTER TABLE dataset ADD COLUMN "{name}" {col_type}')
        conn.commit()
        return {"added": True, "column": name}
    finally:
        conn.close()


def rename_column(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)
    rn = spec.get("renameColumn")
    if not rn:
        raise ValueError("Schema spec missing renameColumn")

    old = rn["oldName"]
    new = rn["newName"]

    conn = get_active_connection()
    try:
        cols = _get_cols(conn)
        col_names = [c[0] for c in cols]
        if old not in col_names:
            raise ValueError(f"Column not found: {old}")
        if new in col_names:
            raise ValueError(f"Target column already exists: {new}")

        # Rebuild table: CREATE new with renamed column then copy.
        tmp = "dataset__tmp__"
        new_cols_defs = []
        copy_select = []
        for c_name, c_type in cols:
            actual_type = (c_type or "TEXT")
            if c_name == old:
                new_cols_defs.append(f'"{new}" {actual_type}')
                copy_select.append(f'"{c_name}" AS "{new}"')
            else:
                new_cols_defs.append(f'"{c_name}" {actual_type}')
                copy_select.append(f'"{c_name}"')

        conn.execute(f'DROP TABLE IF EXISTS {tmp}')
        conn.execute(f'CREATE TABLE {tmp} ({", ".join(new_cols_defs)})')
        conn.execute(f'INSERT INTO {tmp} SELECT {", ".join(copy_select)} FROM dataset')
        conn.execute('DROP TABLE dataset')
        conn.execute(f'ALTER TABLE {tmp} RENAME TO dataset')
        conn.commit()
        return {"renamed": True, "from": old, "to": new}
    finally:
        conn.close()


def remove_column(*, question: str, schema: str) -> dict[str, Any]:
    spec = _call_llm(question=question, schema=schema)
    rm = spec.get("removeColumn")
    if not rm:
        raise ValueError("Schema spec missing removeColumn")

    name = rm["name"]

    conn = get_active_connection()
    try:
        cols = _get_cols(conn)
        col_names = [c[0] for c in cols]
        if name not in col_names:
            raise ValueError(f"Column not found: {name}")

        tmp = "dataset__tmp__"
        kept = [(c_name, c_type) for (c_name, c_type) in cols if c_name != name]
        if not kept:
            raise ValueError("Refusing to remove the last remaining column.")

        new_defs = [f'"{c}" {(t or "TEXT")}' for c, t in kept]
        copy_select = [f'"{c}"' for c, _ in kept]

        conn.execute(f'DROP TABLE IF EXISTS {tmp}')
        conn.execute(f'CREATE TABLE {tmp} ({", ".join(new_defs)})')
        conn.execute(f'INSERT INTO {tmp} SELECT {", ".join(copy_select)} FROM dataset')
        conn.execute('DROP TABLE dataset')
        conn.execute(f'ALTER TABLE {tmp} RENAME TO dataset')
        conn.commit()
        return {"removed": True, "column": name}
    finally:
        conn.close()

