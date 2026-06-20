from __future__ import annotations


class ChartRecommendationService:
    """Recommends supported chart types based on a DataFrame profile.

    Recommendations can be made either globally (existing behavior) or
    axis-aware for user-selected X/Y columns.
    """


    SUPPORTED = [
        "bar",
        "line",
        "pie",
        "scatter",
        "area",
        "histogram",
        "donut",
    ]

    def recommend(self, profile: dict, result_total: int) -> dict:
        """Global recommendation (legacy) based only on column kinds."""
        if not profile or result_total is None or int(result_total) < 10:
            return {"enabled": False, "recommendedTypes": [], "defaultType": None}

        cols = profile.get("columns", {})
        numeric_cols = [c for c, p in cols.items() if p.get("kind") == "numeric"]
        categorical_cols = [c for c, p in cols.items() if p.get("kind") == "categorical"]
        date_cols = [c for c, p in cols.items() if p.get("kind") == "date"]

        # Heuristics to keep selections valid.
        recs: list[str] = []

        # Two numeric columns => scatter
        if len(numeric_cols) >= 2:
            recs.append("scatter")

        # Numeric distributions => histogram
        if len(numeric_cols) >= 1 and len(numeric_cols) <= 2:
            recs.append("histogram")

        # Date + numeric => line/area
        if len(date_cols) >= 1 and len(numeric_cols) >= 1:
            # both can be valid; include both, default to line
            recs.extend(["line", "area"])

        # Category distribution => pie/donut
        if categorical_cols and (len(numeric_cols) >= 1 or result_total <= 5000):
            recs.extend(["pie", "donut"])

        # Category + numeric => bar
        if categorical_cols and len(numeric_cols) >= 1:
            recs.append("bar")

        # If only categorical columns => bar could show top categories by frequency.
        if not recs and categorical_cols:
            recs.append("bar")

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for t in recs:
            if t in self.SUPPORTED and t not in seen:
                seen.add(t)
                deduped.append(t)

        if not deduped:
            return {"enabled": False, "recommendedTypes": [], "defaultType": None}

        default = "line" if "line" in deduped else deduped[0]
        return {
            "enabled": True,
            "recommendedTypes": deduped,
            "defaultType": default,
        }

    def recommend_for_axes(

        self,
        profile: dict,
        result_total: int,
        x_column: str | None,
        y_column: str | None,
    ) -> dict:
        """Axis-aware recommendation: only chart types valid for the selected X/Y kinds."""
        if not profile or result_total is None or int(result_total) < 10:
            return {"enabled": False, "recommendedTypes": [], "defaultType": None}

        cols = profile.get("columns", {})
        x_kind = cols.get(x_column, {}).get("kind") if x_column else None
        y_kind = cols.get(y_column, {}).get("kind") if y_column else None

        numeric_cols = [c for c, p in cols.items() if p.get("kind") == "numeric"]
        categorical_cols = [c for c, p in cols.items() if p.get("kind") == "categorical"]
        date_cols = [c for c, p in cols.items() if p.get("kind") == "date"]

        recs: list[str] = []

        # Scatter: numeric x and numeric y
        if x_kind == "numeric" and y_kind == "numeric":
            recs.append("scatter")

        # Histogram: numeric y (x unused)
        if y_kind == "numeric":
            recs.append("histogram")

        # Line/Area: date x and numeric y
        if x_kind == "date" and y_kind == "numeric":
            recs.extend(["line", "area"])

        # Bar: categorical x; y numeric optional
        if x_kind == "categorical":
            recs.append("bar")

        # Pie/Donut: categorical x; y numeric optional
        if x_kind == "categorical":
            recs.extend(["pie", "donut"])

        # If we have chosen x_kind but not y_kind yet, still allow those that don't need y
        # (bar/pie/donut don't require y)

        # Deduplicate preserving order
        seen = set()
        deduped = []
        for t in recs:
            if t in self.SUPPORTED and t not in seen:
                seen.add(t)
                deduped.append(t)

        if not deduped:
            return {"enabled": False, "recommendedTypes": [], "defaultType": None}

        default = None
        if "line" in deduped:
            default = "line"
        else:
            default = deduped[0]

        # If y is missing but type requires it, filter them out more strictly.
        filtered: list[str] = []
        for t in deduped:
            if t in ("scatter", "line", "area", "histogram"):
                if y_column is None:
                    continue
            filtered.append(t)

        if not filtered:
            return {"enabled": False, "recommendedTypes": [], "defaultType": None}

        default = default if default in filtered else filtered[0]

        return {
            "enabled": True,
            "recommendedTypes": filtered,
            "defaultType": default,
        }


