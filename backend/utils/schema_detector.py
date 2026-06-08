"""
Schema Detector — centralized, single source of truth for dataset column types.

Detection Logic (applied in order):
1. Try datetime conversion — if >90% valid dates → DATE
2. Try numeric conversion — if all non-null values are numeric → NUM
3. Otherwise → TEXT

Allowed output types: NUM, TEXT, DATE
"""

from __future__ import annotations

import pandas as pd

from typing import Dict


def detect_schema(df: pd.DataFrame) -> Dict[str, str]:
    """
    Detect schema for ALL columns in the dataframe.
    Returns a dict: {column_name: "NUM"|"TEXT"|"DATE"}

    Rules:
    - If column can be converted to datetime with >90% success → DATE
    - Else if column is numeric (int or float) → NUM
    - Else → TEXT
    """
    schema: Dict[str, str] = {}

    for col in df.columns:
        schema[col] = _detect_column_type(df, col)

    return schema


def _detect_column_type(df: pd.DataFrame, col: str) -> str:
    """Detect the type of a single column."""
    series = df[col]

    # Step 1: Check if it's NUMERIC first
    # IMPORTANT: Must check numeric BEFORE date, because integers like 101, 102
    # can be incorrectly parsed as dates by pandas.
    if _is_numeric_column(series):
        return "NUM"

    # Step 2: Check if it's a DATE column (>90% valid dates)
    if _is_date_column(series):
        return "DATE"

    # Step 3: Fallback to TEXT
    return "TEXT"


def _is_date_column(series: pd.Series) -> bool:
    """Check if >90% of non-null values can be parsed as dates."""
    # Remove nulls
    clean = series.dropna()
    if len(clean) == 0:
        return False

    # If already datetime dtype
    if pd.api.types.is_datetime64_any_dtype(clean):
        return True

    # Skip date check if column is already numeric (to avoid small ints being parsed as dates)
    if pd.api.types.is_numeric_dtype(clean):
        return False

    # Try parsing as datetime (coerce errors to NaT)
    try:
        # Sample up to 1000 rows for performance
        sample = clean.head(1000) if len(clean) > 1000 else clean
        parsed = pd.to_datetime(sample, errors="coerce")
        valid_ratio = parsed.notna().sum() / len(sample)
        return valid_ratio > 0.9
    except (ValueError, TypeError):
        return False


def _is_numeric_column(series: pd.Series) -> bool:
    """Check if column is numeric (int or float)."""
    # If pandas already detects as numeric
    if pd.api.types.is_numeric_dtype(series):
        return True

    # For object/string columns, try converting to numeric
    if series.dtype == "object":
        clean = series.dropna()
        if len(clean) == 0:
            return False

        # Sample up to 1000 rows for performance
        sample = clean.head(1000) if len(clean) > 1000 else clean
        converted = pd.to_numeric(sample, errors="coerce")
        valid_ratio = converted.notna().sum() / len(sample)
        return valid_ratio > 0.9

    return False


def get_schema_for_sql_prompt(schema: Dict[str, str]) -> str:
    """
    Convert schema dict to a formatted string suitable for LLM SQL prompts.
    Example:
      order_id: NUM
      customer_name: TEXT
      order_date: DATE
    """
    lines = [f"  \"{col}\": {dtype}" for col, dtype in schema.items()]
    return "\n".join(lines)


def validate_schema_consistency(schema_a: Dict[str, str], schema_b: Dict[str, str], context_a: str = "A", context_b: str = "B") -> bool:
    """
    Validate that two schema dicts are identical.
    Returns True if identical, False if mismatch found.
    """
    if schema_a == schema_b:
        return True

    mismatches = []
    all_cols = set(schema_a.keys()) | set(schema_b.keys())
    for col in all_cols:
        ta = schema_a.get(col, "MISSING")
        tb = schema_b.get(col, "MISSING")
        if ta != tb:
            mismatches.append(f"  {col}: {context_a}={ta} vs {context_b}={tb}")

    import logging
    logger = logging.getLogger("schema_validator")
    for m in mismatches:
        logger.warning("Schema mismatch: %s", m)

    return False