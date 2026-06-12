"""
chart_recommender.py — AI Visualization Intelligence Layer.

Pure rule-based engine that analyses a DataFrame profile and produces:
  - recommended_chart  : best chart type
  - x_axis / y_axis    : exact column names
  - reason             : human-readable explanation
  - all_types          : ordered list of applicable chart types for user override
  - insights           : 3-8 smart observations from the data
  - spec_override      : optional pre-aggregation hint for the prep service

No extra LLM call is needed — the VisualizationProfileService already extracts
everything required (column kinds, unique counts, top values, min/max).
"""

from __future__ import annotations

import math
from typing import Any

import pandas as pd


# ── Supported chart types in priority order ───────────────────────────────────
_SUPPORTED = ["bar", "line", "area", "pie", "donut", "scatter", "histogram"]

# ── Column-name hints that signal a date/time axis even for TEXT columns ──────
_DATE_HINTS = {"date", "time", "month", "year", "day", "week", "period",
               "quarter", "timestamp", "created", "updated", "ordered", "dt"}


def _is_date_col(col_name: str, kind: str) -> bool:
    if kind == "date":
        return True
    lc = col_name.lower().replace(" ", "_").replace("-", "_")
    return any(h in lc for h in _DATE_HINTS)


def _col_kind(col_name: str, profile_cols: dict) -> str:
    info = profile_cols.get(col_name, {})
    kind = info.get("kind", "categorical")
    if _is_date_col(col_name, kind):
        return "date"
    return kind


def _fmt(val: Any) -> str:
    try:
        f = float(val)
        if math.isnan(f) or math.isinf(f):
            return str(val)
        if abs(f) >= 1_000_000:
            return f"{f / 1_000_000:.2f}M"
        if abs(f) >= 1_000:
            return f"{f / 1_000:.1f}K"
        if f == int(f):
            return str(int(f))
        return f"{f:.2f}"
    except Exception:
        return str(val)


def _generate_percentage_str(part: float, total: float) -> str:
    if total and total != 0:
        pct = round(100 * part / total, 1)
        return f" ({pct}%)"
    return ""


# ── Main recommender ──────────────────────────────────────────────────────────

class ChartRecommender:
    """
    Analyses a DataFrame profile and returns a full recommendation dict.

    Usage::

        rec = ChartRecommender().recommend(df, profile, question="")
        # rec["recommended_chart"]  -> "bar"
        # rec["x_axis"]             -> "Country"
        # rec["y_axis"]             -> "Confirmed"
        # rec["reason"]             -> "Country is categorical …"
        # rec["all_types"]          -> ["bar", "pie", "donut"]
        # rec["insights"]           -> ["Top country: USA …", …]
    """

    MAX_PIE_CATS    = 8
    MAX_BAR_CATS    = 20   # auto-aggregated to top-N before this
    MAX_SCATTER_PTS = 1000

    def recommend(
        self,
        df: pd.DataFrame,
        profile: dict,
        question: str = "",
        user_requested_chart: str | None = None,
    ) -> dict:
        """
        Returns a recommendation dict.  If *user_requested_chart* is supplied
        the engine honours it (Mode 1) but still fills in the best axes.
        """
        cols   = profile.get("columns", {})
        nrows  = profile.get("row_count", len(df))

        # Classify every column
        numeric_cols     = [c for c in df.columns if _col_kind(c, cols) == "numeric"]
        date_cols        = [c for c in df.columns if _col_kind(c, cols) == "date"]
        categorical_cols = [c for c in df.columns
                            if _col_kind(c, cols) == "categorical"
                            and c not in date_cols]

        # ── Determine best axes & chart via rules ─────────────────────────────
        chart, x, y, reason, all_types = self._decide(
            df, cols, numeric_cols, date_cols, categorical_cols, nrows, question
        )

        # ── User override (Mode 1) ────────────────────────────────────────────
        if user_requested_chart and user_requested_chart in _SUPPORTED:
            overridden_chart = user_requested_chart
            # Re-pick axes that suit the requested type
            x2, y2 = self._axes_for_type(
                user_requested_chart, numeric_cols, date_cols, categorical_cols, x, y
            )
            reason = (
                f"You requested a **{user_requested_chart}** chart. "
                f"Using **{x2}** on the X-axis"
                + (f" and **{y2}** on the Y-axis." if y2 else ".")
            )
            x, y = x2, y2
            chart = overridden_chart
            # Put user choice first in list
            all_types = [chart] + [t for t in all_types if t != chart]

        # ── Generate data insights ────────────────────────────────────────────
        insights = self._generate_insights(
            df, cols, x, y, numeric_cols, categorical_cols, date_cols, nrows
        )

        return {
            "recommended_chart": chart,
            "x_axis":            x,
            "y_axis":            y,
            "reason":            reason,
            "all_types":         all_types,
            "insights":          insights,
        }

    # ── Decision engine ───────────────────────────────────────────────────────

    def _decide(
        self,
        df: pd.DataFrame,
        cols: dict,
        numeric_cols: list,
        date_cols: list,
        categorical_cols: list,
        nrows: int,
        question: str,
    ) -> tuple[str, str | None, str | None, str, list]:
        """Returns (chart_type, x_col, y_col, reason, all_types)."""

        q = question.lower()

        # ── Rule 1: Time-series ───────────────────────────────────────────────
        if date_cols and numeric_cols:
            x = date_cols[0]
            y = numeric_cols[0]
            reason = (
                f"**{x}** is a time/date column and **{y}** is numeric — "
                "a Line chart best shows trends over time."
            )
            return "line", x, y, reason, ["line", "area", "bar"]

        # ── Rule 2: Two numeric columns — scatter ─────────────────────────────
        if len(numeric_cols) >= 2 and not categorical_cols:
            x, y = numeric_cols[0], numeric_cols[1]
            reason = (
                f"Both **{x}** and **{y}** are numeric — "
                "a Scatter plot reveals the relationship between them."
            )
            return "scatter", x, y, reason, ["scatter", "histogram"]

        # ── Rule 3: Category + numeric — bar (or pie if small) ───────────────
        if categorical_cols and numeric_cols:
            x = categorical_cols[0]
            y = numeric_cols[0]
            n_unique = cols.get(x, {}).get("unique_count", 999)

            if n_unique <= self.MAX_PIE_CATS and ("pie" in q or "proportion" in q or "share" in q):
                reason = (
                    f"**{x}** has only {n_unique} categories — "
                    "a Pie chart shows part-to-whole proportions clearly."
                )
                return "pie", x, y, reason, ["pie", "donut", "bar"]

            if n_unique <= self.MAX_PIE_CATS:
                reason = (
                    f"**{x}** is categorical ({n_unique} values) and **{y}** is numeric — "
                    "a Bar chart is best for category comparison."
                )
                return "bar", x, y, reason, ["bar", "pie", "donut", "line", "area"]

            # Many categories → bar with top-N note
            reason = (
                f"**{x}** is categorical and **{y}** is numeric — "
                f"showing top {self.MAX_BAR_CATS} categories as a Bar chart."
            )
            return "bar", x, y, reason, ["bar", "line", "area"]

        # ── Rule 4: Only categorical columns — frequency bar ─────────────────
        if categorical_cols and not numeric_cols:
            x = categorical_cols[0]
            n_unique = cols.get(x, {}).get("unique_count", 999)
            if n_unique <= self.MAX_PIE_CATS:
                reason = (
                    f"**{x}** has {n_unique} categories — "
                    "a Pie chart shows the frequency distribution."
                )
                return "pie", x, None, reason, ["pie", "donut", "bar"]
            reason = (
                f"**{x}** is categorical — "
                "a Bar chart shows the frequency of each category."
            )
            return "bar", x, None, reason, ["bar", "pie", "donut"]

        # ── Rule 5: Only numeric columns — histogram ──────────────────────────
        if numeric_cols:
            x = numeric_cols[0]
            reason = (
                f"**{x}** is a single numeric column — "
                "a Histogram shows its distribution."
            )
            return "histogram", x, None, reason, ["histogram", "bar"]

        # ── Fallback ──────────────────────────────────────────────────────────
        first = df.columns[0] if len(df.columns) > 0 else None
        second = df.columns[1] if len(df.columns) > 1 else None
        return "bar", first, second, "Using Bar chart as default.", ["bar"]

    def _axes_for_type(
        self,
        chart: str,
        numeric_cols: list,
        date_cols: list,
        categorical_cols: list,
        default_x: str | None,
        default_y: str | None,
    ) -> tuple[str | None, str | None]:
        """Pick the most suitable axes for a user-requested chart type."""
        if chart in ("line", "area"):
            x = date_cols[0] if date_cols else (categorical_cols[0] if categorical_cols else default_x)
            y = numeric_cols[0] if numeric_cols else default_y
            return x, y
        if chart == "scatter":
            x = numeric_cols[0] if len(numeric_cols) >= 1 else default_x
            y = numeric_cols[1] if len(numeric_cols) >= 2 else default_y
            return x, y
        if chart == "histogram":
            x = numeric_cols[0] if numeric_cols else default_x
            return x, None
        if chart in ("pie", "donut"):
            x = categorical_cols[0] if categorical_cols else default_x
            y = numeric_cols[0] if numeric_cols else default_y
            return x, y
        # bar / default
        x = categorical_cols[0] if categorical_cols else (date_cols[0] if date_cols else default_x)
        y = numeric_cols[0] if numeric_cols else default_y
        return x, y

    # ── Smart Insight Generator ───────────────────────────────────────────────

    def _generate_insights(
        self,
        df: pd.DataFrame,
        cols: dict,
        x_col: str | None,
        y_col: str | None,
        numeric_cols: list,
        categorical_cols: list,
        date_cols: list,
        nrows: int,
    ) -> list[str]:
        insights: list[str] = []

        try:
            # ── Insight 1: Chart Summary ─────────────────────────────────────
            insights.append(f"📊 **Chart Summary:** Analyzing {nrows:,} data points.")

            # ── Insight 2: Top / Highest category ─────────────────────────────
            if x_col and y_col and x_col in df.columns and y_col in df.columns:
                try:
                    agg = (
                        df.groupby(x_col)[y_col]
                        .sum()
                        .sort_values(ascending=False)
                    )
                    if not agg.empty:
                        top_label = str(agg.index[0])
                        top_val = float(agg.iloc[0])
                        total_val = float(agg.sum())

                        pct_str = _generate_percentage_str(top_val, total_val)
                        insights.append(
                            f"🏆 **Highest {x_col}:** {top_label} ({_fmt(top_val)}{pct_str})"
                        )

                        # Lowest
                        bottom_label = str(agg.index[-1])
                        bottom_val = float(agg.iloc[-1])
                        insights.append(
                            f"📉 **Lowest {x_col}:** {bottom_label} ({_fmt(bottom_val)})"
                        )

                        # Average across categories
                        avg_val = float(agg.mean())
                        insights.append(
                            f"📈 **Average {y_col}:** {_fmt(avg_val)} across {len(agg)} categories"
                        )

                        # Total value
                        insights.append(
                            f"📋 **Total {y_col}:** {_fmt(total_val)}"
                        )

                        # Top 3 concentration
                        if len(agg) >= 3 and total_val:
                            top3_val = float(agg.iloc[:3].sum())
                            top3_pct = round(100 * top3_val / total_val, 1)
                            other_pct = round(100 - top3_pct, 1)
                            insights.append(
                                f"🔍 **Distribution:** Top 3 {x_col}s contribute **{top3_pct}%** "
                                f"of total {y_col} (others: {other_pct}%)"
                            )

                        # Outlier detection: check if any single category dominates
                        if total_val and len(agg) >= 5:
                            top_pct = round(100 * top_val / total_val, 1)
                            if top_pct > 50:
                                insights.append(
                                    f"⚠ **Outlier:** '{top_label}' alone accounts for {top_pct}% "
                                    f"of total {y_col} — dominant category detected."
                                )
                            elif top_pct < 2 and len(agg) > 10:
                                insights.append(
                                    f"💡 **Key Finding:** {y_col} is evenly distributed "
                                    f"across {len(agg)} categories (no single dominant one)."
                                )
                except Exception:
                    pass

            # ── Insight 3: Numeric range ──────────────────────────────────────
            if y_col and y_col in df.columns:
                try:
                    s = pd.to_numeric(df[y_col], errors="coerce").dropna()
                    if not s.empty:
                        insights.append(
                            f"📈 **{y_col} range:** {_fmt(s.min())} to {_fmt(s.max())} "
                            f"(avg: {_fmt(s.mean())}, median: {_fmt(s.median())})"
                        )
                except Exception:
                    pass

            # ── Insight 4: Trend detection for line/area ──────────────────────
            if x_col and y_col and x_col in df.columns and y_col in df.columns:
                try:
                    # Check if x_col looks like a date
                    if date_cols and x_col in date_cols:
                        tmp = df[[x_col, y_col]].copy()
                        tmp[y_col] = pd.to_numeric(tmp[y_col], errors="coerce")
                        tmp = tmp.dropna()
                        if len(tmp) >= 5:
                            first_half = tmp[y_col].iloc[:len(tmp)//2].mean()
                            second_half = tmp[y_col].iloc[len(tmp)//2:].mean()
                            if second_half > first_half * 1.1:
                                change_pct = round(100 * (second_half - first_half) / max(first_half, 0.001), 1)
                                insights.append(
                                    f"📈 **Trend:** Upward trend detected — "
                                    f"values increased by ~{change_pct}% over the period"
                                )
                            elif first_half > second_half * 1.1:
                                change_pct = round(100 * (first_half - second_half) / max(first_half, 0.001), 1)
                                insights.append(
                                    f"📉 **Trend:** Downward trend detected — "
                                    f"values decreased by ~{change_pct}% over the period"
                                )
                            else:
                                insights.append(
                                    f"➡️ **Trend:** Relatively stable over time "
                                    f"(within 10% of mean)"
                                )
                except Exception:
                    pass

            # ── Insight 5: Correlation for scatter ────────────────────────────
            if x_col and y_col and x_col in df.columns and y_col in df.columns:
                try:
                    tmp = df[[x_col, y_col]].dropna()
                    tmp[x_col] = pd.to_numeric(tmp[x_col], errors="coerce")
                    tmp[y_col] = pd.to_numeric(tmp[y_col], errors="coerce")
                    tmp = tmp.dropna()
                    if len(tmp) >= 5:
                        corr = tmp[x_col].corr(tmp[y_col])
                        direction = "positive" if corr > 0 else "negative"
                        strength = "strong" if abs(corr) > 0.7 else "moderate" if abs(corr) > 0.3 else "weak"
                        insights.append(
                            f"🔗 **Correlation:** {strength.capitalize()} {direction} "
                            f"correlation (r={corr:.2f}) between {x_col} and {y_col} "
                            f"across {len(tmp)} data points"
                        )
                except Exception:
                    pass

            # ── Insight 6: Distribution shape for histogram ───────────────────
            if numeric_cols:
                try:
                    col = x_col or y_col or numeric_cols[0]
                    if col and col in df.columns:
                        s = pd.to_numeric(df[col], errors="coerce").dropna()
                        if not s.empty and len(s) > 2:
                            skewness = s.skew()
                            if abs(skewness) < 0.5:
                                shape = "approximately symmetric (normal-like)"
                            elif skewness > 0.5:
                                shape = "right-skewed (positive skew)"
                            else:
                                shape = "left-skewed (negative skew)"
                            kurtosis = s.kurtosis()
                            if kurtosis > 2:
                                tail = "heavy tails (outliers present)"
                            else:
                                tail = "light tails"
                            insights.append(
                                f"🔍 **Distribution:** {col} is {shape} with {tail}"
                            )
                except Exception:
                    pass

            # ── Insight 7: Missing data ───────────────────────────────────────
            miss_cols = [
                c for c in df.columns
                if cols.get(c, {}).get("missing_count", 0) > 0
            ]
            if miss_cols:
                worst = max(miss_cols, key=lambda c: cols[c].get("missing_count", 0))
                pct = round(
                    100 * cols[worst]["missing_count"] / max(nrows, 1), 1
                )
                if pct > 0:
                    insights.append(
                        f"⚠️ **Data Quality:** '{worst}' has "
                        f"{cols[worst]['missing_count']} missing values ({pct}%)"
                    )

            # ── Insight 8: Dataset size ──────────────────────────────────────
            if nrows > 0:
                insights.append(f"📋 Based on **{nrows:,}** total data point{'s' if nrows != 1 else ''}")

        except Exception:
            pass  # insights are bonus — never break the chart

        return insights[:8]  # cap at 8