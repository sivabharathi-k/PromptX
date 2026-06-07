"""
Database utilities — SQLite connection management and rich schema extraction.
"""

import sqlite3

import pandas as pd

TABLE_NAME = "dataset"

# Semantic hints the LLM can use for fuzzy column matching
_SEMANTIC_HINTS = {
    "money":    {"revenue", "sales", "income", "earnings", "profit", "amount",
                 "price", "cost", "total", "value", "payment", "fee", "salary",
                 "wage", "compensation", "ctc", "pay"},
    "customer": {"customer", "client", "buyer", "user", "account", "member",
                 "consumer", "patron", "subscriber"},
    "product":  {"product", "item", "sku", "goods", "service", "article",
                 "merchandise", "offering"},
    "date":     {"date", "time", "timestamp", "created", "updated", "ordered",
                 "shipped", "period", "month", "year", "day", "week"},
    "location": {"region", "city", "country", "state", "zone", "area",
                 "location", "territory", "branch", "store", "address"},
    "quantity": {"quantity", "qty", "units", "volume", "count", "number",
                 "sold", "ordered", "stock", "inventory"},
    "category": {"category", "type", "segment", "class", "group", "kind",
                 "department", "dept", "division", "team", "section"},
    "score":    {"score", "grade", "rating", "gpa", "marks", "points",
                 "rank", "index", "percentile"},
    "status":   {"status", "flag", "active", "state", "stage", "phase",
                 "condition", "result", "outcome"},
    "name":     {"name", "title", "label", "description", "desc",
                 "fullname", "firstname", "lastname"},
    "id":       {"id", "key", "code", "number", "ref", "reference",
                 "identifier", "no", "num"},
}


def _semantic_tag(col_name: str) -> str | None:
    """Return a semantic category tag for a column name if one matches."""
    lower = col_name.lower().replace(" ", "_").replace("-", "_")
    for tag, keywords in _SEMANTIC_HINTS.items():
        if any(kw in lower for kw in keywords):
            return tag
    return None


def load_dataframe(df: pd.DataFrame) -> sqlite3.Connection:
    """
    Load a DataFrame into a per-request in-memory SQLite database.
    :memory: guarantees zero cross-session / cross-user leakage.
    """
    conn = sqlite3.connect(":memory:")
    df.to_sql(TABLE_NAME, conn, if_exists="replace", index=False)
    return conn


def get_schema(conn: sqlite3.Connection) -> str:
    """
    Build a comprehensive schema description for the LLM including:
    - Total row and column counts
    - Per-column: SQLite type, semantic tag, null count
    - Numeric columns: min, max, avg, distinct count
    - Categorical columns: distinct count + up to 15 sample values
    - Date columns: earliest and latest values
    - 5 sample rows
    """
    cursor = conn.cursor()

    cursor.execute(f"PRAGMA table_info({TABLE_NAME})")
    columns = cursor.fetchall()          # (cid, name, type, notnull, dflt, pk)
    col_names = [c[1] for c in columns]

    cursor.execute(f"SELECT COUNT(*) FROM {TABLE_NAME}")
    total_rows = cursor.fetchone()[0]

    cursor.execute(f"SELECT * FROM {TABLE_NAME} LIMIT 5")
    samples = cursor.fetchall()

    lines = [
        f"Table name : {TABLE_NAME}",
        f"Total rows : {total_rows}",
        f"Total cols : {len(col_names)}",
        f"Columns    : {', '.join(col_names)}",
        "",
        "Column Details:",
    ]

    for col in columns:
        col_name = col[1]
        col_type = col[2].upper() if col[2] else "TEXT"
        tag      = _semantic_tag(col_name)

        # Null / empty count
        try:
            cursor.execute(
                f'SELECT COUNT(*) FROM {TABLE_NAME} '
                f'WHERE "{col_name}" IS NULL OR TRIM(CAST("{col_name}" AS TEXT)) = \'\''
            )
            null_count = cursor.fetchone()[0]
        except Exception:
            null_count = 0

        parts = [f'  "{col_name}"']
        parts.append(f"type={col_type}")
        if tag:
            parts.append(f"semantic={tag}")
        if null_count:
            parts.append(f"nulls={null_count}/{total_rows}")

        is_numeric = col_type in (
            "INTEGER", "REAL", "NUMERIC", "FLOAT", "DOUBLE",
            "BIGINT", "INT", "DECIMAL", "NUMBER",
        )
        is_date = (
            col_type in ("DATE", "DATETIME", "TIMESTAMP") or
            tag == "date"
        )

        if is_numeric:
            try:
                cursor.execute(
                    f'SELECT MIN("{col_name}"), MAX("{col_name}"), '
                    f'ROUND(AVG("{col_name}"), 2), COUNT(DISTINCT "{col_name}") '
                    f'FROM {TABLE_NAME}'
                )
                mn, mx, avg, dist = cursor.fetchone()
                parts.append(f"min={mn}, max={mx}, avg={avg}, distinct={dist}")
            except Exception:
                pass

        elif is_date:
            try:
                cursor.execute(
                    f'SELECT MIN("{col_name}"), MAX("{col_name}") FROM {TABLE_NAME}'
                )
                mn, mx = cursor.fetchone()
                parts.append(f"range={mn} → {mx}")
            except Exception:
                pass

        else:
            try:
                cursor.execute(
                    f'SELECT COUNT(DISTINCT "{col_name}") FROM {TABLE_NAME}'
                )
                distinct = cursor.fetchone()[0]
                parts.append(f"distinct={distinct}")

                if distinct <= 30:
                    cursor.execute(
                        f'SELECT DISTINCT "{col_name}" FROM {TABLE_NAME} '
                        f'WHERE "{col_name}" IS NOT NULL LIMIT 15'
                    )
                    vals = [str(r[0]) for r in cursor.fetchall() if r[0] is not None]
                    if vals:
                        parts.append(f"values=[{', '.join(vals)}]")
            except Exception:
                pass

        lines.append(" | ".join(parts))

    lines.append("")
    lines.append("Sample rows (first 5):")
    for row in samples:
        row_dict = {col_names[i]: row[i] for i in range(len(col_names))}
        lines.append(f"  {row_dict}")

    return "\n".join(lines)
