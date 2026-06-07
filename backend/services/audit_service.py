"""Audit & undo support for dataset editing operations."""

from __future__ import annotations

import datetime as _dt
import sqlite3
import uuid
from dataclasses import dataclass

from backend.utils.active_dataset_store import get_active_connection


@dataclass(frozen=True)
class AuditRecord:
    operation_id: str
    timestamp: str
    operation_type: str
    affected_rows: int
    details: dict


UNDO_TABLE = "__dataset_undo__"


def _ensure_undo_table(conn: sqlite3.Connection) -> None:
    conn.execute(
        f"""
        CREATE TABLE IF NOT EXISTS {UNDO_TABLE} (
            operation_id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            operation_type TEXT NOT NULL,
            affected_rows INTEGER NOT NULL,
            snapshot_table TEXT NOT NULL,
            details TEXT
        )
        """
    )
    conn.commit()


def create_snapshot_for_undo(*, operation_type: str, affected_rows: int, details: dict) -> str:
    """Create a full snapshot table of current dataset for undo.

    Returns operation_id.

    Snapshot approach is safest MVP (no complex delta reverse engineering).
    """
    operation_id = uuid.uuid4().hex
    created_at = _dt.datetime.utcnow().isoformat() + "Z"
    snapshot_table = f"dataset_undo_{operation_id}"

    conn = get_active_connection()
    try:
        _ensure_undo_table(conn)
        conn.execute(f"DROP TABLE IF EXISTS {snapshot_table}")
        conn.execute(f"CREATE TABLE {snapshot_table} AS SELECT * FROM dataset")
        conn.execute(
            f"INSERT INTO {UNDO_TABLE} (operation_id, created_at, operation_type, affected_rows, snapshot_table, details) "
            f"VALUES (?, ?, ?, ?, ?, ?)",
            (operation_id, created_at, operation_type, int(affected_rows), snapshot_table, str(details)),
        )
        conn.commit()
        return operation_id
    finally:
        conn.close()


def undo_last_operation(*, operation_id: str | None = None) -> dict:
    """Undo by restoring dataset from the snapshot table.

    If operation_id is None, undo the most recent operation.
    Returns dict with restored snapshot.
    """
    conn = get_active_connection()
    try:
        _ensure_undo_table(conn)

        if operation_id:
            row = conn.execute(
                f"SELECT snapshot_table, operation_type, created_at, affected_rows FROM {UNDO_TABLE} WHERE operation_id=?",
                (operation_id,),
            ).fetchone()
        else:
            row = conn.execute(
                f"SELECT snapshot_table, operation_type, created_at, affected_rows FROM {UNDO_TABLE} ORDER BY created_at DESC LIMIT 1"
            ).fetchone()

        if not row:
            return {"undone": False, "error": "No undo history available."}

        snapshot_table, operation_type, created_at, affected_rows = row

        # Restore: replace dataset with snapshot.
        conn.execute("DROP TABLE IF EXISTS dataset")
        conn.execute(f"CREATE TABLE dataset AS SELECT * FROM {snapshot_table}")
        conn.commit()

        # Optionally keep audit record; deleting is okay too. We'll keep it.
        return {
            "undone": True,
            "restoredFrom": snapshot_table,
            "operationType": operation_type,
            "timestamp": created_at,
            "affectedRows": int(affected_rows),
        }
    finally:
        conn.close()

