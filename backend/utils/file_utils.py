"""
File utilities — upload validation and CSV reading.
"""

import io

import pandas as pd
from werkzeug.datastructures import FileStorage

from backend.config.settings import ALLOWED_EXTENSIONS, MAX_ROWS_IN_SESSION


def is_allowed_file(filename: str) -> bool:
    """Return True if the file extension is in the allowed set."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def read_csv(file: FileStorage) -> tuple[pd.DataFrame | None, str | None]:
    """
    Read and validate an uploaded CSV file.
    Tries UTF-8, then latin-1 to handle Windows/Excel exports.
    Returns (DataFrame, None) on success or (None, error_message) on failure.
    """
    if not file or file.filename == "":
        return None, "No file selected."

    if not is_allowed_file(file.filename):
        return None, "Only CSV files are supported."

    raw = file.read()
    df  = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
            break
        except Exception:
            continue

    if df is None:
        return None, "Failed to parse CSV: unsupported encoding or malformed file."

    if df.empty:
        return None, "The uploaded CSV file is empty."

    if len(df) > MAX_ROWS_IN_SESSION:
        return None, f"File exceeds the {MAX_ROWS_IN_SESSION:,} row limit."

    # Sanitise column names: strip whitespace
    df.columns = [str(c).strip() for c in df.columns]

    return df, None
