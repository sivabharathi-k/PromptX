"""In-memory cache for the active dataset's DataFrame and visualization profile.

The Custom Chart Builder and Auto Visualization panel repeatedly call back to
the server as the user tweaks chart type, axes, aggregation, sort order and
Top-N — each call previously re-read the entire `dataset` table from SQLite
and re-ran VisualizationProfileService.profile() from scratch. For larger
datasets this dominated request latency even though neither the data nor the
profile actually changed between requests.

Cache entries are keyed by the active dataset's SQLite file path and are
validated against that file's mtime, so any upload, insert, update, delete,
clean, or transform operation (all of which commit to the same file)
automatically invalidates the cache on the next read.
"""

from __future__ import annotations

import os
import threading

import pandas as pd

from backend.utils.active_dataset_store import get_active_dataset_info, get_active_connection
from backend.services.visualization_profile_service import VisualizationProfileService

_lock = threading.Lock()
_cache: dict[str, dict] = {}
_reco_cache: dict[str, dict] = {}


def get_active_dataframe_and_profile() -> tuple[pd.DataFrame, dict]:
    """Return (df, profile) for the active dataset, reusing a cached copy
    when the underlying SQLite file hasn't changed since it was last read."""
    db_path = get_active_dataset_info().db_path
    mtime = os.path.getmtime(db_path) if os.path.exists(db_path) else None

    with _lock:
        entry = _cache.get(db_path)
        if entry is not None and entry["mtime"] == mtime:
            return entry["df"], entry["profile"]

    conn = get_active_connection()
    try:
        df = pd.read_sql("SELECT * FROM dataset", conn)
    finally:
        conn.close()

    profile = VisualizationProfileService().profile(df)

    with _lock:
        _cache[db_path] = {"mtime": mtime, "df": df, "profile": profile}

    return df, profile


def get_cached_recommendations(compute_fn):
    """Return the auto-recommendations payload for the active dataset,
    reusing a cached copy when the underlying SQLite file hasn't changed
    since it was last computed. `compute_fn` is only called on a cache miss."""
    db_path = get_active_dataset_info().db_path
    mtime = os.path.getmtime(db_path) if os.path.exists(db_path) else None

    with _lock:
        entry = _reco_cache.get(db_path)
        if entry is not None and entry["mtime"] == mtime:
            return entry["data"]

    data = compute_fn()

    with _lock:
        _reco_cache[db_path] = {"mtime": mtime, "data": data}

    return data
