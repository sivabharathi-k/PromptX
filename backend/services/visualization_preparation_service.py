from __future__ import annotations

import pandas as pd


class VisualizationPreparationService:
    """Transforms (profiled) result data into a Chart.js-ready chart spec.

    Output is backend-agnostic: the frontend renders using Chart.js.

    This service supports **axis-aware** rendering. The caller can explicitly
    choose which columns map to X/Y for each chart type.
    """


    def __init__(
        self,
        max_points_scatter: int = 2000,
        max_categories_pie: int = 8,
        max_bins_hist: int = 30,
        max_categories_bar: int = 12,
    ):
        self.max_points_scatter = max_points_scatter
        self.max_categories_pie = max_categories_pie
        self.max_bins_hist = max_bins_hist
        self.max_categories_bar = max_categories_bar

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
    ) -> dict:
        """Axis-aware rendering using explicit X/Y columns.

        Supported combinations are validated by the API layer, but this method
        still raises ValueError if required columns are missing/empty.
        """
        if df is None or df.empty:
            raise ValueError("No data available to render chart")

        chart_type = (chart_type or "").lower().strip()

        if chart_type == "scatter":
            if not x_column or not y_column:
                raise ValueError("Scatter requires xColumn and yColumn")
            return self._scatter_xy(df, x_column, y_column)

        if chart_type == "histogram":
            if not y_column:
                raise ValueError("Histogram requires yColumn")
            return self._histogram_col(df, y_column)

        if chart_type in ("line", "area"):
            if not x_column or not y_column:
                raise ValueError(f"{chart_type.title()} requires xColumn and yColumn")
            return self._line_area_xy(df, x_column, y_column, area=(chart_type == "area"))

        if chart_type == "bar":
            if not x_column:
                raise ValueError("Bar requires xColumn")
            # y_column optional: if absent, counts-only bar
            return self._bar_xy(df, x_column, y_column)

        if chart_type in ("pie", "donut"):
            if not x_column:
                raise ValueError(f"{chart_type.title()} requires xColumn")
            return self._pie_donut_xy(df, x_column, y_column, donut=(chart_type == "donut"))

        raise ValueError(f"Unsupported chart type: {chart_type}")


    def _scatter(self, df, numeric_cols, categorical_cols) -> dict:
        if len(numeric_cols) < 2:
            raise ValueError("Scatter requires at least two numeric columns")
        xcol, ycol = numeric_cols[0], numeric_cols[1]

        return self._scatter_xy(df, xcol, ycol)

    def _scatter_xy(self, df: pd.DataFrame, xcol: str, ycol: str) -> dict:
        plot_df = df[[xcol, ycol]].dropna()
        if len(plot_df) > self.max_points_scatter:
            plot_df = plot_df.sample(n=self.max_points_scatter, random_state=42)

        points = [{"x": float(r[xcol]), "y": float(r[ycol])} for _, r in plot_df.iterrows()]

        return {
            "plotType": "scatter",
            "title": f"{ycol} vs {xcol}",
            "xLabel": xcol,
            "yLabel": ycol,
            "series": [{"label": "Data", "data": points}],
        }


    def _histogram(self, df, numeric_cols) -> dict:
        if not numeric_cols:
            raise ValueError("Histogram requires a numeric column")
        col = numeric_cols[0]
        return self._histogram_col(df, col)

    def _histogram_col(self, df: pd.DataFrame, col: str) -> dict:
        s = pd.to_numeric(df[col], errors="coerce").dropna()
        if s.empty:
            raise ValueError("Histogram requires non-empty numeric values")

        # Bounded bins
        bins = min(self.max_bins_hist, max(5, int(len(s) ** 0.5)))
        counts, bin_edges = pd.cut(s, bins=bins, include_lowest=True, retbins=True)
        freq = counts.value_counts().sort_index()

        labels = [f"{bin_edges[i]:.2g}–{bin_edges[i+1]:.2g}" for i in range(len(bin_edges) - 1)]
        data = [int(freq.iloc[i]) if i < len(freq) else 0 for i in range(len(labels))]

        return {
            "plotType": "bar",
            "title": f"Distribution of {col}",
            "xLabel": col,
            "yLabel": "Count",
            "series": [{"label": "Frequency", "data": data, "labels": labels}],
        }


    def _line_area(self, df, date_cols, numeric_cols, area: bool) -> dict:
        if not date_cols or not numeric_cols:
            raise ValueError("Line/Area requires date and numeric columns")
        dcol = date_cols[0]
        ycol = numeric_cols[0]
        return self._line_area_xy(df, dcol, ycol, area=area)

    def _line_area_xy(self, df: pd.DataFrame, xcol: str, ycol: str, area: bool) -> dict:
        tmp = df[[xcol, ycol]].copy()
        tmp[xcol] = pd.to_datetime(tmp[xcol], errors="coerce")
        tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
        tmp = tmp.dropna(subset=[xcol, ycol])
        if tmp.empty:
            raise ValueError("Line/Area requires non-empty date+numeric values")

        tmp = tmp.sort_values(xcol)

        # Aggregate if many points
        if len(tmp) > 500:
            tmp["_bucket"] = tmp[xcol].dt.to_period("M").astype(str)
            agg = tmp.groupby("_bucket")[ycol].mean().reset_index()
            labels = agg["_bucket"].tolist()
            values = [float(v) for v in agg[ycol].tolist()]
        else:
            labels = tmp[xcol].dt.strftime("%Y-%m-%d").tolist()
            values = [float(v) for v in tmp[ycol].tolist()]

        return {
            "plotType": "line" if not area else "area",
            "title": f"{ycol} over time",
            "xLabel": xcol,
            "yLabel": ycol,
            "series": [{"label": ycol, "data": values, "labels": labels}],
            "area": area,
        }


    def _bar(self, df, categorical_cols, numeric_cols) -> dict:
        if not categorical_cols:
            raise ValueError("Bar requires a categorical column")
        cat = categorical_cols[0]
        val = numeric_cols[0] if numeric_cols else None
        return self._bar_xy(df, cat, val)

    def _bar_xy(self, df: pd.DataFrame, xcol: str, ycol: str | None) -> dict:
        # ycol optional: if absent, counts-only bar
        if ycol:
            tmp = df[[xcol, ycol]].copy().dropna(subset=[xcol])
            tmp[ycol] = pd.to_numeric(tmp[ycol], errors="coerce")
            tmp = tmp.dropna(subset=[ycol])
            if tmp.empty:
                # fallback to counts
                vc = df[xcol].astype(str).value_counts().head(self.max_categories_bar)
                labels = vc.index.tolist()
                data = [int(x) for x in vc.values.tolist()]
            else:
                # Top categories by frequency
                freq = df[xcol].astype(str).value_counts()
                top_cats = freq.head(self.max_categories_bar).index.tolist()
                tmp[xcol] = tmp[xcol].astype(str)
                tmp = tmp[tmp[xcol].isin(top_cats)]
                agg = tmp.groupby(xcol)[ycol].mean().reset_index()
                # preserve top order
                order = {c: i for i, c in enumerate(top_cats)}
                agg["_ord"] = agg[xcol].map(order)
                agg = agg.sort_values("_ord")
                labels = agg[xcol].astype(str).tolist()
                data = [float(v) for v in agg[ycol].tolist()]

            return {
                "plotType": "bar",
                "title": f"{ycol} by {xcol}",
                "xLabel": xcol,
                "yLabel": ycol,
                "series": [{"label": ycol, "data": data, "labels": labels}],
            }

        # counts-only bar
        vc = df[xcol].astype(str).value_counts().head(self.max_categories_bar)
        labels = vc.index.tolist()
        data = [int(x) for x in vc.values.tolist()]

        return {
            "plotType": "bar",
            "title": f"Top {xcol} categories",
            "xLabel": xcol,
            "yLabel": "Count",
            "series": [{"label": "Count", "data": data, "labels": labels}],
        }



    def _pie_donut(self, df, categorical_cols, numeric_cols, donut: bool) -> dict:
        if not categorical_cols:
            raise ValueError("Pie/Donut requires a categorical column")
        cat = categorical_cols[0]
        val = numeric_cols[0] if numeric_cols else None
        return self._pie_donut_xy(df, cat, val, donut=donut)

    def _pie_donut_xy(
        self,
        df: pd.DataFrame,
        xcol: str,
        ycol: str | None,
        donut: bool,
    ) -> dict:
        """Render pie/donut from explicit categorical X and optional numeric Y."""

        # xcol is categorical
        cat = xcol

        # If numeric exists, try to treat numeric as value; otherwise use counts
        if ycol:
            val = ycol
            tmp = df[[cat, val]].copy().dropna(subset=[cat])
            tmp[val] = pd.to_numeric(tmp[val], errors="coerce")
            tmp = tmp.dropna(subset=[val])
            if not tmp.empty:
                tmp[cat] = tmp[cat].astype(str)
                # Top categories by frequency
                freq = df[cat].astype(str).value_counts()
                top_cats = freq.head(self.max_categories_pie).index.tolist()
                tmp = tmp[tmp[cat].isin(top_cats)]
                agg = tmp.groupby(cat)[val].mean().reset_index()
                order = {c: i for i, c in enumerate(top_cats)}
                agg["_ord"] = agg[cat].map(order)
                agg = agg.sort_values("_ord")
                labels = agg[cat].astype(str).tolist()
                data = [float(v) for v in agg[val].tolist()]
                title = f"{cat} distribution of {val}"
            else:
                vc = df[cat].astype(str).value_counts().head(self.max_categories_pie)
                labels = vc.index.tolist()
                data = [int(x) for x in vc.values.tolist()]
                title = f"{cat} distribution"
        else:
            vc = df[cat].astype(str).value_counts().head(self.max_categories_pie)
            labels = vc.index.tolist()
            data = [int(x) for x in vc.values.tolist()]
            title = f"{cat} distribution"

        return {
            "plotType": "pie" if not donut else "donut",
            "title": title,
            "labels": labels,
            "series": [{"label": cat, "data": data}],
        }


