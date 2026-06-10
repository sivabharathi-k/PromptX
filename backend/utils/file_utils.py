"""
File utilities — upload validation and CSV/Excel reading.
"""

import io

import pandas as pd
from werkzeug.datastructures import FileStorage

from backend.config.settings import ALLOWED_EXTENSIONS, MAX_ROWS_IN_SESSION


def is_allowed_file(filename: str) -> bool:
    """Return True if the file extension is in the allowed set."""
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _get_extension(filename: str) -> str:
    """Return lowercase file extension."""
    return filename.rsplit(".", 1)[1].lower() if "." in filename else ""


def read_uploaded_file(file: FileStorage) -> tuple[pd.DataFrame | None, str | None]:
    """
    Read and validate an uploaded CSV or Excel file.
    Automatically detects file type by extension.
    Returns (DataFrame, None) on success or (None, error_message) on failure.
    """
    if not file or file.filename == "":
        return None, "No file selected."

    if not is_allowed_file(file.filename):
        return None, "Only CSV (.csv) and Excel (.xlsx, .xls) files are supported."

    ext = _get_extension(file.filename)

    if ext == "csv":
        return _read_csv(file)
    elif ext in ("xlsx", "xls"):
        return _read_excel(file)
    else:
        return None, f"Unsupported file format: .{ext}"


def _read_csv(file: FileStorage) -> tuple[pd.DataFrame | None, str | None]:
    """Read and validate a CSV file. Tries multiple encodings."""
    raw = file.read()
    df = None
    for encoding in ("utf-8", "utf-8-sig", "latin-1", "cp1252"):
        try:
            df = pd.read_csv(io.BytesIO(raw), encoding=encoding)
            break
        except Exception:
            continue

    if df is None:
        return None, "Failed to parse CSV: unsupported encoding or malformed file."

    return _validate_dataframe(df, file.filename)


def _read_excel(file: FileStorage) -> tuple[pd.DataFrame | None, str | None]:
    """Read and validate an Excel (.xlsx, .xls) file."""
    raw = file.read()
    try:
        # Read all sheets; use the first non-empty sheet
        engine = "openpyxl" if _get_extension(file.filename) == "xlsx" else "xlrd"
        xls = pd.ExcelFile(io.BytesIO(raw), engine=engine)
        sheet_names = xls.sheet_names

        df = None
        for sheet in sheet_names:
            sheet_df = pd.read_excel(io.BytesIO(raw), sheet_name=sheet, engine=engine)
            if not sheet_df.empty:
                df = sheet_df
                break

        if df is None:
            # Fallback: try first sheet
            df = pd.read_excel(io.BytesIO(raw), sheet_name=0, engine=engine)

    except Exception as e:
        return None, f"Failed to parse Excel file: {str(e)}"

    return _validate_dataframe(df, file.filename)


def _validate_dataframe(df: pd.DataFrame, filename: str) -> tuple[pd.DataFrame | None, str | None]:
    """Validate a parsed DataFrame for size and content."""
    if df.empty:
        return None, f"The uploaded file '{filename}' is empty."

    if len(df) > MAX_ROWS_IN_SESSION:
        return None, f"File exceeds the {MAX_ROWS_IN_SESSION:,} row limit."

    # Sanitise column names: strip whitespace, replace NaN column names
    df.columns = [str(c).strip() if pd.notna(c) else f"column_{i}" for i, c in enumerate(df.columns)]

    # Remove fully empty columns
    df = df.dropna(axis=1, how="all")

    if df.empty or df.shape[1] == 0:
        return None, f"The uploaded file '{filename}' contains no usable data columns."

    # Convert any remaining object columns with numeric-like data
    for col in df.select_dtypes(include="object").columns:
        try:
            converted = pd.to_numeric(df[col], errors="coerce")
            if converted.notna().sum() == df[col].notna().sum():
                df[col] = converted
        except Exception:
            pass

    return df, None
