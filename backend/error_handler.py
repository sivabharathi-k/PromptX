"""
Enterprise-grade error handler — zero-failure architecture.
Wraps every route, service, and utility with multiple safety layers.
No exception ever propagates unhandled.
"""
from __future__ import annotations

import functools
import logging
import traceback
from typing import Any, Callable, TypeVar

from flask import jsonify

logger = logging.getLogger("error_handler")

F = TypeVar("F", bound=Callable)


def safe_route(f: F) -> F:
    """Decorator that wraps Flask route handlers with complete error isolation.
    Every exception is caught and returned as a structured JSON error response.
    """
    @functools.wraps(f)
    def wrapper(*args, **kwargs):
        try:
            return f(*args, **kwargs)
        except Exception as e:
            tb = traceback.format_exc()
            logger.critical("UNHANDLED ROUTE EXCEPTION [%s]: %s\n%s", f.__name__, str(e), tb)
            return jsonify({
                "error": "An unexpected error occurred. Please try again.",
                "success": False,
                "_trace": str(e),
            }), 500
    return wrapper


def safe_call(fn: Callable, *args, default: Any = None, **kwargs) -> Any:
    """Execute a function with complete error isolation.
    Returns *default* on any exception instead of crashing.
    """
    try:
        return fn(*args, **kwargs)
    except Exception:
        logger.warning("safe_call failed for %s: %s", getattr(fn, '__name__', str(fn)), traceback.format_exc())
        return default


def safe_get(obj: Any, *keys: str, default: Any = None) -> Any:
    """Safely traverse a nested dict/list structure. Returns default on any missing key."""
    current = obj
    for key in keys:
        try:
            if isinstance(current, dict):
                current = current.get(key, default)
            elif isinstance(current, (list, tuple)) and isinstance(key, int):
                current = current[key] if 0 <= key < len(current) else default
            elif isinstance(current, (list, tuple)):
                current = default
                break
            else:
                current = default
                break
        except (IndexError, KeyError, TypeError, AttributeError):
            return default
        if current is None:
            return default
    return current


def validate_not_none(value: Any, name: str = "value") -> Any:
    """Return value if not None, otherwise log warning and return None."""
    if value is None:
        logger.warning("validate_not_none: '%s' is None", name)
    return value


def safe_dataframe_call(df, fn, *args, default=None, **kwargs):
    """Execute a DataFrame operation safely. Returns default on failure."""
    if df is None:
        logger.warning("safe_dataframe_call: DataFrame is None")
        return default
    try:
        return fn(df, *args, **kwargs)
    except Exception:
        logger.warning("safe_dataframe_call failed: %s", traceback.format_exc())
        return default


class SafeAccessMixin:
    """Mixin providing safe property access methods."""

    @staticmethod
    def _safe(obj, key, default=None):
        if obj is None:
            return default
        try:
            val = obj.get(key) if isinstance(obj, dict) else getattr(obj, key, default)
            return val if val is not None else default
        except (AttributeError, KeyError, TypeError):
            return default

    @staticmethod
    def _safe_nested(obj, *keys, default=None):
        current = obj
        for key in keys:
            try:
                if isinstance(current, dict):
                    current = current.get(key)
                elif isinstance(current, (list, tuple)):
                    current = current[int(key)] if hasattr(key, '__index__') and 0 <= int(key) < len(current) else None
                else:
                    current = None
            except (IndexError, KeyError, TypeError, ValueError):
                return default
            if current is None:
                return default
        return current if current is not None else default

    @staticmethod
    def _safe_float(v, default=0.0):
        if v is None:
            return default
        try:
            f = float(v)
            import math
            return default if math.isnan(f) or math.isinf(f) else f
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_int(v, default=0):
        if v is None:
            return default
        try:
            return int(v)
        except (ValueError, TypeError):
            return default

    @staticmethod
    def _safe_str(v, default=""):
        if v is None:
            return default
        try:
            return str(v)
        except Exception:
            return default