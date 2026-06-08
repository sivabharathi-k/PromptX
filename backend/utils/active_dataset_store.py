"""Active dataset store — single source of truth on disk.

We keep the existing architecture intact (query/visualize/download unchanged) by
introducing a persistent on-disk SQLite database per Flask session.

This module provides:
- Ensure a per-session DB file exists
- Load CSV into SQLite table `dataset`
- Return a live sqlite3 connection for services
- Provide helpers for schema/row inspection

SINGLE SOURCE OF TRUTH FOR SCHEMA:
- After upload, detect_schema() is called once.
- The master schema dict is stored in session['master_schema'].
- ALL modules (sidebar, chatbot, SQL engine, profile, insights, viz, export)
  use session['master_schema'] as the single source of truth.
- Schema is a dict: {column_name: "NUM"|"TEXT"|"DATE"}

NOTE: We intentionally do NOT alter the current query pipeline that uses
session["csv_data"]. New editing APIs will operate on this persistent SQLite.
"""

from __future__ import annotations

import hashlib
import os
import sqlite3
import uuid
from dataclasses import dataclass
from typing import Dict, Optional

from flask import session

from backend.config.settings import DATA_DIR, SESSIONS_DIR
from backend.utils.file_utils import read_csv

TABLE_NAME = "dataset"

# Master schema key in Flask session
MASTER_SCHEMA_KEY = "master_schema"


@dataclass(frozen=True)
class ActiveDatasetInfo:
    db_path: str


def _ensure_session_id() -> str:
    sid = session.get("active_dataset_session_id")
    if not sid:
        sid = uuid.uuid4().hex
        session["active_dataset_session_id"] = sid
        session.modified = True
    return sid


def get_active_dataset_info() -> ActiveDatasetInfo:
    sid = _ensure_session_id()

    # Per-session sqlite file to avoid cross-user leakage.
    # Store under backend/data/sessions/ with a stable filename.
    # (flask-session already uses this directory, but we keep our own subfolder/file.)
    # Use hash to keep filename short.
    hashed = hashlib.sha256(sid.encode("utf-8")).hexdigest()[:16]

    db_dir = os.path.join(SESSIONS_DIR, "active_datasets")
    os.makedirs(db_dir, exist_ok=True)

    db_path = os.path.join(db_dir, f"active_{hashed}.sqlite3")
    return ActiveDatasetInfo(db_path=db_path)


def get_active_connection() -> sqlite3.Connection:
    info = get_active_dataset_info()
    conn = sqlite3.connect(info.db_path)
    # Enable foreign keys if later needed.
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def load_dataframe_into_active_db(df, *, if_exists: str = "replace") -> None:
    """Load a pandas DataFrame into the active dataset table.
    Also detects and stores the master schema in session.
    """
    conn = get_active_connection()
    try:
        df.to_sql(TABLE_NAME, conn, if_exists=if_exists, index=False)
        conn.commit()
    finally:
        conn.close()

    # Detect and store master schema (single source of truth)
    from backend.utils.schema_detector import detect_schema
    master_schema = detect_schema(df)
    set_master_schema(master_schema)


def get_master_schema() -> Optional[Dict[str, str]]:
    """Get the master schema dict from session.
    Returns None if no schema has been stored yet.
    """
    return session.get(MASTER_SCHEMA_KEY)


def get_master_schema_formatted() -> str:
    """Get formatted master schema string for LLM prompts.
    Returns empty string if no schema available.
    """
    schema = get_master_schema()
    if not schema:
        return ""
    from backend.utils.schema_detector import get_schema_for_sql_prompt
    return get_schema_for_sql_prompt(schema)


def set_master_schema(schema: Dict[str, str]) -> None:
    """Store the master schema in session."""
    session[MASTER_SCHEMA_KEY] = schema
    session.modified = True


def clear_master_schema() -> None:
    """Remove master schema from session."""
    if MASTER_SCHEMA_KEY in session:
        del session[MASTER_SCHEMA_KEY]
        session.modified = True


def get_active_schema() -> str:
    """Return schema description using existing get_schema utility.
    This is the legacy method that returns a human-readable string.
    """
    from backend.utils.db_utils import get_schema

    conn = get_active_connection()
    try:
        return get_schema(conn)
    finally:
        conn.close()


def get_active_schema_with_types() -> str:
    """Return schema description enhanced with master schema types.
    
    This builds a rich schema string including the master schema types (NUM/TEXT/DATE)
    rather than raw SQLite types. Used for LLM prompts.
    """
    master = get_master_schema()
    if not master:
        return get_active_schema()

    conn = get_active_connection()
    try:
        from backend.utils.db_utils import get_columns_from_db
        col_names = get_columns_from_db(conn)
        lines = [f"Table name: {TABLE_NAME}"]
        lines.append(f"Schema types: {master}")
        lines.append(f"Columns: {', '.join(col_names)}")
        lines.append("")
        lines.append("Column Details:")
        for col in col_names:
            dtype = master.get(col, "TEXT")
            lines.append(f'  "{col}" type={dtype}')
        return "\n".join(lines)
    finally:
        conn.close()


def active_dataset_exists() -> bool:
    info = get_active_dataset_info()
    return os.path.exists(info.db_path) and os.path.getsize(info.db_path) > 0


def reset_active_dataset() -> None:
    """Remove active sqlite db file for the current session."""
    info = get_active_dataset_info()
    if os.path.exists(info.db_path):
        os.remove(info.db_path)
    clear_master_schema()


def ensure_table_exists(conn: sqlite3.Connection) -> None:
    """Create dataset table if missing (best-effort)."""
    cur = conn.cursor()
    cur.execute(
        """
        SELECT name FROM sqlite_master WHERE type='table' AND name=?
        """,
        (TABLE_NAME,),
    )
    if cur.fetchone() is None:
        # Empty placeholder table; editing services will overwrite with proper schema.
        conn.execute(f"CREATE TABLE {TABLE_NAME} (id INTEGER)")
        conn.commit()