import pandas as pd


class VisualizationProfileService:
    """Profiles a pandas DataFrame for visualization suitability.

    This service is intentionally conservative and bounded for performance.
    """

    def __init__(
        self,
        max_unique_values: int = 50,
        max_profile_rows: int = 2000,
    ):
        self.max_unique_values = max_unique_values
        self.max_profile_rows = max_profile_rows

    def profile(self, df: pd.DataFrame) -> dict:
        if df is None or df.empty:
            return {"row_count": 0, "columns": {}}

        sample = df
        if len(df) > self.max_profile_rows:
            sample = df.sample(n=self.max_profile_rows, random_state=42)

        profile = {
            "row_count": int(len(df)),
            "columns": {},
        }

        for col in df.columns:
            s = df[col]
            col_profile = {
                "dtype": str(s.dtype),
                "kind": "unknown",  # numeric|categorical|date|unknown
                "unique_count": int(s.nunique(dropna=True)),
                "missing_count": int(s.isna().sum()),
                "min": None,
                "max": None,
                "top_values": [],  # bounded for categories
            }

            # numeric detection
            if pd.api.types.is_numeric_dtype(s):
                col_profile["kind"] = "numeric"
                col_profile["min"] = self._safe_min(s)
                col_profile["max"] = self._safe_max(s)

            # date/time detection (object or string columns)
            elif pd.api.types.is_datetime64_any_dtype(s):
                col_profile["kind"] = "date"
                col_profile["min"] = self._safe_min(s)
                col_profile["max"] = self._safe_max(s)

            else:
                # Try parsing datetimes for non-numeric columns
                parsed = None
                try:
                    # only on a sample to avoid heavy parsing
                    parsed = pd.to_datetime(sample[col], errors="coerce", utc=False)
                except Exception:
                    parsed = None

                if parsed is not None:
                    non_na = parsed.notna().sum()
                    if non_na >= max(5, int(0.7 * len(sample))):
                        col_profile["kind"] = "date"
                        # Use parsed values for bounds from df
                        parsed_full = pd.to_datetime(s, errors="coerce", utc=False)
                        col_profile["min"] = self._safe_min(parsed_full)
                        col_profile["max"] = self._safe_max(parsed_full)
                    else:
                        col_profile["kind"] = "categorical"

                # if parsing failed entirely, treat as categorical
                if col_profile["kind"] == "unknown":
                    col_profile["kind"] = "categorical"

            # categorical top values (bounded)
            if col_profile["kind"] == "categorical":
                vc = s.value_counts(dropna=True)
                top = vc.head(self.max_unique_values)
                col_profile["top_values"] = [
                    {"value": str(idx), "count": int(cnt)} for idx, cnt in top.items()
                ]

            profile["columns"][col] = col_profile

        return profile

    def _safe_min(self, s):
        try:
            v = s.min(skipna=True)
            return None if pd.isna(v) else (v.isoformat() if hasattr(v, "isoformat") else float(v) if isinstance(v, (int, float)) else str(v))
        except Exception:
            return None

    def _safe_max(self, s):
        try:
            v = s.max(skipna=True)
            return None if pd.isna(v) else (v.isoformat() if hasattr(v, "isoformat") else float(v) if isinstance(v, (int, float)) else str(v))
        except Exception:
            return None

