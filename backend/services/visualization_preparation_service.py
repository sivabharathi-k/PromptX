"""
visualization_preparation_service.py — Production-grade chart spec builder.

Transforms a DataFrame into a Chart.js-ready spec with full support for:
  - Aggregation (sum, avg, count, min, max, median)
  - Sort order (ascending / descending)
  - Top-N filtering
  - Proper label handling with truncation for 100+ categories
  - All chart types: bar, line, area, pie, donut, scatter, histogram
  - Performance: handles 50K+ rows efficiently
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd
import numpy as np


# ── Constants ──────────────────────────────────────────────────────────────────
MAX_CATEGORIES_BAR    = 100
MAX_CATEGORIES_PIE    = 20
MAX_POINTS_SCATTER    = 5000
MAX_BINS_HIST         = 40
MAX_LABEL_LENGTH      = 30  # truncate labels longer than this
MAX_LINE_POINTS       = 500
TRUNCATION_SUFFIX     = "…"
DATE_AGG_THRESHOLD    = 200  # aggregate to monthly if more points than this


def _truncate_label(label: str, max_len: int = MAX_LABEL_LENGTH) -> str:
    """Truncate a label to max_len chars, adding ellipsis if truncated."""
    s = str(label)
    if len(s) > max_len:
        return s[:max_len - 1] + TRUNCATION_SUFFIX
    return s


def _format_value(v: float) -> str:
    """Format large numbers for display."""
    if math.isnan(v) or math.isinf(v):
        return "0"
    if abs(v) >= 1_000_000:
        return f"{v / 1_000_000:.2f}M"
    if abs(v) >= 1_000:
        return f"{v / 1_000:.1f}K"
    if v == int(v):
        return str(int(v))
    return f"{v:.2f}"


def _aggregate_data(
    df: pd.DataFrame,
    x_col: str,
    y_col: str | None,
    agg: str,
) -> pd.DataFrame:
    """
    Aggregate df by x_col, applying the specified aggregation to y_col.
    If y_col is None, performs counts.
    """
    if y_col is None or y_col not in df.columns:
        # Count-based aggregation
        grouped = df.groupby(x_col, observed=True).size().reset_index(name="_count_")
        return grouped

    # Ensure numeric
    tmp = df[[x_col, y_col]].copy()
    tmp[y_col] = pd.to_numeric(tmp[y_col], errors="coerce")
    tmp = tmp.dropna(subset=[y_col])

    if tmp.empty:
        # Fallback to count
        grouped = df.groupby(x_col, observed=True).size().reset_index(name="_count_")
        return grouped

    agg_funcs = {
        "sum": ("sum", lambda g: g.sum()),
        "avg": ("mean", lambda g: g.mean()),
        "count": ("count", lambda g: g.count()),
        "min": ("min", lambda g: g.min()),
        "max": ("max", lambda g: g.max()),
        "median": ("median", lambda g: g.median()),
    }

    if agg not in agg_funcs:
        agg = "sum"

    _, func = agg_funcs[agg]
    result = tmp.groupby(x_col, observed=True)[y_col].apply(func).reset_index()
    result.columns = [x_col, "_value_"]
    return result


def _sort_data(
    df: pd.DataFrame,
    value_col: str,
    sort_order: str = "desc",
) -> pd.DataFrame:
    """Sort aggregated data by value column."""
    ascending = sort_order.lower() == "asc"
    return df.sort_values(value_col, ascending=ascending).reset_index(drop=True)


def _apply_top_n(
    df: pd.DataFrame,
    value_col: str,
    top_n: int | None,
    sort_order: str = "desc",
) -> pd.DataFrame:
    """Apply Top-N on already-sorted data. If top_n is None, return all."""
    if top_n is not None and top_n > 0 and top_n < len(df):
        return df.head(top_n).reset_index(drop=True)
    return df


# ── Main Service ───────────────────────────────────────────────────────────────

class VisualizationPreparationService:
    """Transforms (profiled) result data into a Chart.js-ready chart spec.

    Supports axis-aware rendering with full aggregation/sort/Top-N pipeline.
    Pipeline order: Aggregate → Sort → Apply Top-N → Render
    """

    def __init__(
        self,
        max_points_scatter: int = MAX_POINTS_SCATTER,
        max_categories_pie: int = MAX_CATEGORIES_PIE,
        max_bins_hist: int = MAX_BINS_HIST,
        max_categories_bar: int = MAX_CATEGORIES_BAR,
        max_line_points: int = MAX_LINE_POINTS,
    ):
        self.max_points_scatter = max_points_scatter
        self.max_categories_pie = max_categories_pie
        self.max_bins_hist = max_bins_hist
        self.max_categories_bar = max_categories_bar
        self.max_line_points = max_line_points

    def render(self, df: pd.DataFrame, chart_type: str, profile: dict) -> dict:
        """Legacy behavior: choose appropriate columns from the profile automatically."""
        if df is None or df.empty:
            raise ValueError("No data available to render chart")

        cols = profile.get("columns", {})
        numeric_cols = [c for c, p in cols.items() if p.get("kind") == "numeric"]
        categorical_cols = [c for c, p in cols.items() if p.get("kind") == "categorical"]
        date_cols = [c for c, p in cols.items() if p.get("kind") == "date"]

        chart_type = (chart_type or "").lower().strip()

        if chart_type == "scatter":
            return self._scatter(df, numeric_cols, categorical_cols)
        if chart_type == "histogram":
            return self._histogram(df, numeric_cols)
        if chart_type == "line":
            return self._line_area(df, date_cols, numeric_cols, area=False)
        if chart_type == "area":
            return self._line_area(df, date_cols, numeric_cols, area=True)
        if chart_type == "bar":
            return self._bar(df, categorical_cols, numeric_cols)
        if chart_type in ("pie", "donut"):
            return self._pie_donut(df, categorical_cols, numeric_cols, donut=(chart_type == "donut"))

        raise ValueError(f"Unsupported chart type: {chart_type}")

    def render_with_axes(
        self,
        df: pd.DataFrame,
        chart_type: str,
        profile: dict,
        x_column: str | None,
        y_column: str | None,
        aggregation: str = "sum",
        sort_order: str = "desc",
        top_n: int | None = None,
    ) -> dict:
        """Axis-aware rendering using explicit X/Y columns with full pipeline.

        Pipeline: Aggregate → Sort → Apply Top-N → Render

        Args:
            df: Source DataFrame
            chart_type: One of bar, line, area, pie, donut, scatter, histogram
            profile: Column profile from VisualizationProfileService
            x_column: X-axis column name
            y_column: Y-axis column name
            aggregation: Aggregation function (sum, avg, count, min, max, median)
            sort_order: Sort order for aggregated values (asc, desc)
            top_n: Number of top categories to show (None = show all)

        Returns:
            Chart.js-compatible spec dict
        """
        if df is None or df.empty:
            raise ValueError("No data available to render chart")

        chart_type = (chart_type or "").lower().strip()

        if chart_type == "scatter":
            if not x_column or not y_column:
                raise ValueError("Scatter requires xColumn and yColumn")
            return self._scatter_xy(df, x_column, y_column)

        if chart_type == "histogram":
            col = y_column or x_column
            if not col:
                raise ValueError("Histogram requires a column")
            return self._histogram_col(df, col)

        if chart_type in ("line", "area"):
            if not x_column or not y_column:
                raise ValueError(f"{chart_type.title()} requires xColumn and yColumn")
            return self._line_area_xy(
                df, x_column, y_column, area=(chart_type == "area"),
                aggregation=aggregation, sort_order=sort_order, top_n=top_n,
            )

        if chart_type == "bar":
            if not x_column:
                raise ValueError("Bar requires xColumn")
            return self._bar_xy(
                df, x_column, y_column,
                aggregation=aggregation, sort_order=sort_order, top_n=top_n,
            )

        if chart_type in ("pie", "donut"):
            if not x_column:
                raise ValueError(f"{chart_type.title()} requires xColumn")
            return self._pie_donut_xy(
                df, x_column, y_column, donut=(chart_type == "donut"),
                aggregation=aggregation, sort_order=sort_order, top_n=top_n,
            )

        raise ValueError(f"Unsupported chart type: {chart_type}")

    # ── Scatter ────────────────────────────────────────────────────────────────

    def _scatter(self, df, numeric_cols, categorical_cols) -> dict:
        if len(numeric_cols) < 2:
            raise ValueError("Scatter requires at least two numeric columns")
        return self._scatter_xy(df, numeric_cols[0], numeric_cols[1])

    def _scatter_xy(self, df: pd.DataFrame, xcol: str, ycol: str) -> dict:
        plot_df = df[[xcol, ycol]].dropna()
        plot_df[xcol] = pd.to_numeric(plot_df[xcol], errors="coerce")
        plot_df[ycol] = pd.to_numeric(plot_df[ycol], errors="coerce")
        plot_df = plot_df.dropna()

        if len(plot_df) > self.max_points_scatter:
            plot_df = plot_df.sample(n=self.max_points_scatter, random_state=42)

        points = [{"x": float(r[xcol]), "y": float(r[ycol])} for _, r in plot_df.iterrows()]

        return {
            "plotType": "scatter",
            "title": f"{ycol} vs {xcol}",
            "xLabel": xcol,
            "yLabel": ycol,
            "series": [{"label": "Data", "data": points}],
            "total_points": len(points),
        }

    # ── Histogram ──────────────────────────────────────────────────────────────

    def _histogram(self, df, numeric_cols) -> dict:
        if not numeric_cols:
            raise ValueError("Histogram requires a numeric column")
        return self._histogram_col(df, numeric_cols[0])

    def _histogram_col(self, df: pd.DataFrame, col: str) -> dict:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            raise ValueError("Histogram requires non-empty numeric values")

        # Bounded bins
        bins = min(self.max_bins_hist, max(5, int(len(s) ** 0.5)))
        counts, bin_edges = np.histogram(s, bins=bins)
        bin_edges = [float(e) for e in bin_edges]

        labels = [
            f"{bin_edges[i]:.2g}–{bin_edges[i + 1]:.2g}"
            for i in range(len(bin_edges) - 1)
        ]
        data = [int(c) for c in counts]

        return {
            "plotType": "bar",
            "title": f"Distribution of {col}",
            "xLabel": col,
            "yLabel": "Count",
            "series": [{"label": "Frequency", "data": data, "labels": labels}],
            "total_points": len(s),
        }

    # ── Line / Area ────────────────────────────────────────────────────────────

    def _line_area(self, df, date_cols, numeric_cols, area: bool) -> dict:
        if not date_cols or not numeric_cols:
            raise ValueError("Line/Area requires date and numeric columns")
        return self._line_area_xy(df, date_cols[0], numeric_cols[0], area=area)

    def _line_area_xy(
        self,
        df: pd.DataFrame,
        xcol: str,
        ycol: str,
        area: bool,
        aggregation: str = "sum",
        sort_order: str = "asc",
        top_n: int | None = None,
    ) -> dict:
        tmp = df[[xcol, ycol]].copy()
        try:
            tmp[xcol] = pd.to_datetime(tmp[xcol], errors="coerce")
        except Exception:
            tmp[xcol] = pd.to_datetime(tmp[xcol], errors="coerce")
        tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
        tmp = tmp.dropna(subset=[xcol, ycol])
        if tmp.empty:
            raise ValueError("Line/Area requires non-empty date+numeric values")

        tmp = tmp.sort_values(xcol)

        # Aggregate if many points
        if len(tmp) > self.max_line_points:
            tmp["_bucket"] = tmp[xcol].dt.to_period("M").astype(str)
            agg_func = "mean" if aggregation == "avg" else aggregation
            if agg_func == "count":
                agg = tmp.groupby("_bucket")[ycol].count().reset_index()
            elif agg_func == "median":
                agg = tmp.groupby("_bucket")[ycol].median().reset_index()
            elif agg_func == "min":
                agg = tmp.groupby("_bucket")[ycol].min().reset_index()
            elif agg_func == "max":
                agg = tmp.groupby("_bucket")[ycol].max().reset_index()
            else:
                agg = tmp.groupby("_bucket")[ycol].sum().reset_index()
            labels = agg["_bucket"].tolist()
            values = [float(v) for v in agg[ycol].tolist()]
        else:
            labels = tmp[xcol].dt.strftime("%Y-%m-%d").tolist()
            values = [float(v) for v in tmp[ycol].tolist()]

        return {
            "plotType": "line" if not area else "area",
            "title": f"{ycol} over time by {xcol}",
            "xLabel": xcol,
            "yLabel": ycol,
            "series": [{"label": ycol, "data": values, "labels": labels}],
            "area": area,
            "total_points": len(values),
        }

    # ── Bar ────────────────────────────────────────────────────────────────────

    def _bar(self, df, categorical_cols, numeric_cols) -> dict:
        if not categorical_cols:
            raise ValueError("Bar requires a categorical column")
        return self._bar_xy(df, categorical_cols[0], numeric_cols[0] if numeric_cols else None)

    def _bar_xy(
        self,
        df: pd.DataFrame,
        xcol: str,
        ycol: str | None,
        aggregation: str = "sum",
        sort_order: str = "desc",
        top_n: int | None = None,
    ) -> dict:
        # Pipeline: Aggregate → Sort → Top-N → Render
        agg_df = _aggregate_data(df, xcol, ycol, aggregation)
        value_col = "_value_" if "_value_" in agg_df.columns else "_count_"

        # Sort
        agg_df = _sort_data(agg_df, value_col, sort_order)

        # Apply Top-N
        if top_n is None:
            top_n = self.max_categories_bar
        agg_df = _apply_top_n(agg_df, value_col, min(top_n, self.max_categories_bar), sort_order)

        labels = [_truncate_label(l) for l in agg_df[xcol].tolist()]
        data = [float(v) for v in agg_df[value_col].tolist()]

        # Determine label
        agg_label = ycol or "Count"
        if ycol:
            y_axis_label = f"{aggregation.upper()}({ycol})"
        else:
            y_axis_label = "Count"

        # Title
        title = f"{aggregation.upper()} of {agg_label} by {xcol}"

        return {
            "plotType": "bar",
            "title": title,
            "xLabel": xcol,
            "yLabel": y_axis_label,
            "series": [{"label": agg_label, "data": data, "labels": labels}],
            "total_categories": len(agg_df),
        }

    # ── Pie / Donut ────────────────────────────────────────────────────────────

    def _pie_donut(self, df, categorical_cols, numeric_cols, donut: bool) -> dict:
        if not categorical_cols:
            raise ValueError("Pie/Donut requires a categorical column")
        return self._pie_donut_xy(
            df, categorical_cols[0], numeric_cols[0] if numeric_cols else None, donut=donut,
        )

    def _pie_donut_xy(
        self,
        df: pd.DataFrame,
        xcol: str,
        ycol: str | None,
        donut: bool,
        aggregation: str = "sum",
        sort_order: str = "desc",
        top_n: int | None = None,
    ) -> dict:
        # Pipeline: Aggregate → Sort → Top-N → Render
        agg_df = _aggregate_data(df, xcol, ycol, aggregation)
        value_col = "_value_" if "_value_" in agg_df.columns else "_count_"

        # Sort
        agg_df = _sort_data(agg_df, value_col, sort_order)

        # Apply Top-N
        if top_n is None:
            top_n = self.max_categories_pie
        max_pie = min(top_n, self.max_categories_pie)
        agg_df = _apply_top_n(agg_df, value_col, max_pie, sort_order)

        labels = [_truncate_label(l) for l in agg_df[xcol].tolist()]
        data = [float(v) for v in agg_df[value_col].tolist()]

        title = f"{xcol} distribution"
        if ycol:
            title += f" by {aggregation.upper()}({ycol})"

        return {
            "plotType": "pie" if not donut else "donut",
            "title": title,
            "xLabel": xcol,
            "yLabel": ycol or "Count",
            "labels": labels,
            "series": [{"label": xcol, "data": data, "labels": labels}],
            "total_categories": len(agg_df),
        }