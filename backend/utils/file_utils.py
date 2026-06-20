"""
File utilities — upload validation and CSV/Excel/TSV/TXT reading.

Preprocessing applied on every upload:
  1. Encoding fallback (utf-8 → utf-8-sig → latin-1 → cp1252 → iso-8859-1)
  2. Delimiter auto-detection for plain-text files (comma / tab / semicolon / pipe)
  3. Null-sentinel replacement (N/A, null, none, -, ?, #N/A, …) → NaN at parse time
  4. Column name sanitization (strip whitespace, safe SQLite identifiers, deduplicate)
  5. Fully-empty rows & columns removed
  6. Trailing whitespace stripped from string cells; empty strings → NaN
  7. Purely-numeric object columns coerced to float
"""

from __future__ import annotations

import io
import logging
import re
import warnings

import numpy as np
import pandas as pd
from werkzeug.datastructures import FileStorage

from backend.config.settings import ALLOWED_EXTENSIONS, MAX_ROWS_IN_SESSION

logger = logging.getLogger("file_utils")

# Null-sentinel strings to convert to NaN during parsing
_NULL_SENTINELS: list[str] = [
    "N/A", "NA", "n/a", "na", "N.A.", "N/A.", "N.A",
    "null", "NULL", "Null",
    "none", "None", "NONE",
    "NaN", "nan", "NAN",
    "-", "--", "---",
    "?", "??",
    "#N/A", "#NA", "#NULL!", "#REF!", "#VALUE!", "#DIV/0!", "#ERROR!",
    "missing", "Missing", "MISSING",
    "undefined", "Undefined", "UNDEFINED",
    "N.D.", "nd", "ND",
    "(null)", "(None)", "(none)", "(empty)",
]


def is_allowed_file(filename: str) -> bool:
    """Return True if the file extension is in the allowed set."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_extension(filename: str) -> str:
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


# ──────────────────────────────────────────────────────────────────────────────
#  Public entry point
# ──────────────────────────────────────────────────────────────────────────────

def read_uploaded_file(file: FileStorage) -> tuple[pd.DataFrame | None, str | None]:
    """
    Read and validate an uploaded file (CSV, TSV, TXT, or Excel).
    Returns (DataFrame, None) on success, or (None, error_message) on failure.
    """
    if not file or file.filename == "":
        return None, "No file selected."

    if not is_allowed_file(file.filename):
        return (
            None,
            "Only CSV (.csv), Excel (.xlsx / .xls), TSV (.tsv), "
            "or plain-text (.txt) files are supported.",
        )

    ext = _get_extension(file.filename)

    if ext in ("csv", "tsv", "txt"):
        return _read_delimited(file, ext)
    if ext in ("xlsx", "xls"):
        return _read_excel(file)
    return None, f"Unsupported file format: .{ext}"


# ──────────────────────────────────────────────────────────────────────────────
#  Delimited-text reader (CSV / TSV / TXT)
# ──────────────────────────────────────────────────────────────────────────────

def _sniff_delimiter(raw: bytes, encoding: str) -> str:
    """Return the most-frequent field delimiter found in the first 4 KB."""
    try:
        sample = raw[:4096].decode(encoding, errors="replace")
        lines = [ln for ln in sample.splitlines()[:15] if ln.strip()]
        counts: dict[str, int] = {"\t": 0, ",": 0, ";": 0, "|": 0}
        for line in lines:
            for d in counts:
                counts[d] += line.count(d)
        return max(counts, key=counts.get)
    except Exception:
        return ","


def _read_delimited(file: FileStorage, ext: str) -> tuple[pd.DataFrame | None, str | None]:
    """Read CSV / TSV / TXT with multi-encoding fallback and delimiter sniffing."""
    raw = file.read()
    df: pd.DataFrame | None = None
    last_err: str = ""

    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252", "iso-8859-1"):
        try:
            delimiter = "\t" if ext == "tsv" else _sniff_delimiter(raw, encoding)
            with warnings.catch_warnings():
                warnings.simplefilter("ignore")
                df = pd.read_csv(
                    io.BytesIO(raw),
                    encoding=encoding,
                    sep=delimiter,
                    na_values=_NULL_SENTINELS,
                    keep_default_na=True,
                    on_bad_lines="warn",
                    engine="python",
                    dtype_backend="numpy_nullable",
                )
            break
        except Exception as exc:
            last_err = str(exc)
            df = None
            continue

    if df is None:
        return None, f"Failed to parse file: {last_err or 'unsupported encoding or malformed content'}"

    return _validate_dataframe(df, file.filename)


# ──────────────────────────────────────────────────────────────────────────────
#  Excel reader
# ──────────────────────────────────────────────────────────────────────────────

def _read_excel(file: FileStorage) -> tuple[pd.DataFrame | None, str | None]:
    """Read an Excel (.xlsx / .xls) file, picking the first non-empty sheet."""
    raw = file.read()
    try:
        engine = "openpyxl" if _get_extension(file.filename) == "xlsx" else "xlrd"
        xls = pd.ExcelFile(io.BytesIO(raw), engine=engine)

        df: pd.DataFrame | None = None
        for sheet in xls.sheet_names:
            sheet_df = pd.read_excel(
                io.BytesIO(raw),
                sheet_name=sheet,
                engine=engine,
                na_values=_NULL_SENTINELS,
                keep_default_na=True,
            )
            if not sheet_df.empty:
                df = sheet_df
                break

        if df is None:
            df = pd.read_excel(
                io.BytesIO(raw),
                sheet_name=0,
                engine=engine,
                na_values=_NULL_SENTINELS,
                keep_default_na=True,
            )
    except Exception as exc:
        return None, f"Failed to parse Excel file: {exc}"

    return _validate_dataframe(df, file.filename)


# ──────────────────────────────────────────────────────────────────────────────
#  Column-name sanitization
# ──────────────────────────────────────────────────────────────────────────────

_UNSAFE_COL_RE = re.compile(r"[^\w\s]")
_SPACE_RE = re.compile(r"[\s_]+")

def _sanitise_col(name: object, idx: int) -> str:
    """Return a clean, SQLite-safe column name."""
    s = str(name).strip()
    if not s or s.lower() in ("nan", "none", "null", "unnamed"):
        return f"column_{idx}"
    s = _UNSAFE_COL_RE.sub("_", s)          # special chars → underscore
    s = _SPACE_RE.sub("_", s).strip("_")    # collapse whitespace/underscores
    return s or f"column_{idx}"


# ──────────────────────────────────────────────────────────────────────────────
#  DataFrame validation & preprocessing
# ──────────────────────────────────────────────────────────────────────────────

def _validate_dataframe(
    df: pd.DataFrame, filename: str
) -> tuple[pd.DataFrame | None, str | None]:
    """
    Validate a parsed DataFrame and apply standard preprocessing.
    Steps: size check → column-name sanitization → drop fully-empty rows/cols
           → coerce all-numeric object cols → strip string whitespace.
    """
    if df.empty:
        return None, f"'{filename}' is empty."

    if len(df) > MAX_ROWS_IN_SESSION:
        return (
            None,
            f"File exceeds the {MAX_ROWS_IN_SESSION:,}-row limit. "
            "Please upload a smaller sample.",
        )

    # -- Column-name sanitization & deduplication
    seen: dict[str, int] = {}
    new_cols: list[str] = []
    for i, c in enumerate(df.columns):
        clean = _sanitise_col(c, i)
        if clean in seen:
            seen[clean] += 1
            clean = f"{clean}_{seen[clean]}"
        else:
            seen[clean] = 0
        new_cols.append(clean)
    df.columns = new_cols

    # -- Drop fully-empty columns
    df = df.dropna(axis=1, how="all")

    # -- Drop fully-empty rows (common in Excel files with blank separator rows)
    df = df.dropna(how="all").reset_index(drop=True)

    if df.empty or df.shape[1] == 0:
        return None, f"'{filename}' contains no usable data after removing blank rows/columns."

    # -- Coerce object columns that are entirely numeric
    for col in df.select_dtypes(include=["object", "string"]).columns:
        try:
            converted = pd.to_numeric(df[col], errors="coerce")
            non_null = df[col].notna().sum()
            if non_null > 0 and converted.notna().sum() == non_null:
                df[col] = converted
        except Exception:
            pass

    # -- Strip leading/trailing whitespace from remaining string columns;
    #    re-null empty strings that may have been left behind
    for col in df.select_dtypes(include=["object", "string"]).columns:
        try:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace({"": np.nan, "nan": np.nan, "None": np.nan})
        except Exception:
            pass

    # -- Convert nullable dtypes back to plain numpy types for SQLite compatibility
    for col in df.columns:
        try:
            if hasattr(df[col].dtype, "numpy_dtype"):
                df[col] = df[col].to_numpy(dtype=df[col].dtype.numpy_dtype, na_value=np.nan)
        except Exception:
            try:
                df[col] = df[col].astype(object)
            except Exception:
                pass

    return df, None
