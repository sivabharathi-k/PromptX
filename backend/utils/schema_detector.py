"""
Schema Detector — centralized, single source of truth for dataset column types.

Detection order (applied per column):
  1. BOOL  — native bool dtype, or ≤3 distinct values drawn from a boolean vocabulary
  2. NUM   — pandas numeric dtype, or ≥90% of non-null values parse as numbers
  3. DATE  — ≥80% of non-null values parse as datetimes (numeric cols excluded)
  4. MIXED — 20-89% of non-null values parse as numbers (ambiguous column)
  5. TEXT  — fallback

Output types: NUM | TEXT | DATE | BOOL | MIXED
"""

from __future__ import annotations

import warnings
from typing import Dict

import pandas as pd

_BOOL_VOCAB: frozenset[str] = frozenset({
    "true", "false",
    "yes", "no",
    "y", "n",
    "t", "f",
    "1", "0",
    "on", "off",
    "enabled", "disabled",
})

# Explicit common date format strings — tried in order before fallback inference
_DATE_FORMATS: list[str] = [
    "%Y-%m-%d",
    "%d/%m/%Y",
    "%m/%d/%Y",
    "%Y/%m/%d",
    "%d-%m-%Y",
    "%m-%d-%Y",
    "%Y-%m-%d %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%m/%d/%Y %H:%M:%S",
    "%Y%m%d",
    "%d %b %Y",
    "%B %d, %Y",
    "%b %d, %Y",
]


def detect_schema(df: pd.DataFrame) -> Dict[str, str]:
    """
    Detect schema for ALL columns in the dataframe.
    Returns {column_name: "NUM" | "TEXT" | "DATE" | "BOOL" | "MIXED"}.
    """
    return {col: _detect_column_type(df, col) for col in df.columns}


def _detect_column_type(df: pd.DataFrame, col: str) -> str:
    series = df[col]

    # 1. Boolean — check first so binary 0/1 columns are classified as BOOL not NUM
    if _is_bool_column(series):
        return "BOOL"

    # 2. Numeric
    if _is_numeric_column(series):
        return "NUM"

    # 3. Date / time
    if _is_date_column(series):
        return "DATE"

    # 4. Mixed (partial numeric — neither NUM nor pure TEXT)
    if _is_mixed_column(series):
        return "MIXED"

    # 5. Text fallback
    return "TEXT"


# ──────────────────────────────────────────────────────────────────────────────
#  Per-type detectors
# ──────────────────────────────────────────────────────────────────────────────

def _is_bool_column(series: pd.Series) -> bool:
    """True for native bool dtype or columns with 2-3 values from the boolean vocabulary."""
    if series.dtype == bool or pd.api.types.is_bool_dtype(series):
        return True

    clean = series.dropna()
    if len(clean) == 0:
        return False

    # Only 2 or 3 distinct non-null values (not 1 — that's a constant, not a flag)
    distinct = clean.unique()
    if len(distinct) not in (2, 3):
        return False

    return {str(v).lower().strip() for v in distinct}.issubset(_BOOL_VOCAB)


def _is_numeric_column(series: pd.Series) -> bool:
    """True if pandas already classifies as numeric, or ≥90% of non-null values parse as numbers."""
    if pd.api.types.is_numeric_dtype(series):
        return True

    if series.dtype not in ("object", "string"):
        return False

    clean = series.dropna()
    if len(clean) == 0:
        return False

    sample = clean.iloc[:2000]
    converted = pd.to_numeric(sample, errors="coerce")
    return converted.notna().sum() / len(sample) >= 0.90


def _is_date_column(series: pd.Series) -> bool:
    """True if ≥80% of non-null values can be parsed as datetimes."""
    clean = series.dropna()
    if len(clean) == 0:
        return False

    if pd.api.types.is_datetime64_any_dtype(clean):
        return True

    # Never re-classify a numeric column as DATE (avoids small integers → dates)
    if pd.api.types.is_numeric_dtype(clean):
        return False

    sample = clean.iloc[:2000]
    threshold = 0.80

    # Try explicit formats first (faster and avoids ambiguous inference)
    for fmt in _DATE_FORMATS:
        try:
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                parsed = pd.to_datetime(sample, format=fmt, errors="coerce")
            if parsed.notna().sum() / len(sample) >= threshold:
                return True
        except Exception:
            continue

    # Fallback: let pandas infer the format
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("ignore")
            parsed = pd.to_datetime(sample, errors="coerce", infer_datetime_format=True)
        return parsed.notna().sum() / len(sample) >= threshold
    except Exception:
        return False


def _is_mixed_column(series: pd.Series) -> bool:
    """True if 20-89% of non-null object values parse as numbers (ambiguous)."""
    if series.dtype not in ("object", "string"):
        return False

    clean = series.dropna()
    if len(clean) < 5:
        return False

    sample = clean.iloc[:2000]
    ratio = pd.to_numeric(sample, errors="coerce").notna().sum() / len(sample)
    return 0.20 <= ratio < 0.90


# ──────────────────────────────────────────────────────────────────────────────
#  Prompt / validation helpers
# ──────────────────────────────────────────────────────────────────────────────

def get_schema_for_sql_prompt(schema: Dict[str, str]) -> str:
    """Format schema dict for LLM SQL prompts."""
    return "\n".join(f'  "{col}": {dtype}' for col, dtype in schema.items())


def validate_schema_consistency(
    schema_a: Dict[str, str],
    schema_b: Dict[str, str],
    context_a: str = "A",
    context_b: str = "B",
) -> bool:
    """Return True if both schemas are identical; log mismatches and return False otherwise."""
    if schema_a == schema_b:
        return True

    import logging
    log = logging.getLogger("schema_validator")
    for col in set(schema_a) | set(schema_b):
        ta = schema_a.get(col, "MISSING")
        tb = schema_b.get(col, "MISSING")
        if ta != tb:
            log.warning("Schema mismatch '%s': %s=%s vs %s=%s", col, context_a, ta, context_b, tb)
    return False
