import pandas as pd
import numpy as np
import math


class VisualizationProfileService:
    """Profiles a pandas DataFrame for visualization suitability and enterprise data intelligence.

    This service is optimized and bounded for performance.
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
            return {
                "row_count": 0,
                "columns": {},
                "health_score": 100,
                "correlations": [],
                "trends": [],
                "alerts": []
            }

        total_rows = len(df)
        sample = df
        if total_rows > self.max_profile_rows:
            sample = df.sample(n=self.max_profile_rows, random_state=42)

        profile = {
            "row_count": int(total_rows),
            "columns": {},
            "health_score": 100,
            "correlations": [],
            "trends": [],
            "alerts": []
        }

        numeric_cols = []
        date_cols = []
        categorical_cols = []
        boolean_cols = []
        geo_cols = []

        # Keywords to detect geographical columns
        geo_keywords = {"latitude", "longitude", "lat", "lon", "country", "city", "state", "location", "zip", "postal", "region", "geo", "address"}

        # ── Profile individual columns ──
        for col in df.columns:
            s = df[col]
            non_null_s = s.dropna()
            uniq_count = int(s.nunique(dropna=True))
            missing_cnt = int(s.isna().sum())
            missing_pct = round(100 * missing_cnt / total_rows, 2) if total_rows > 0 else 0.0

            col_profile = {
                "dtype": str(s.dtype),
                "kind": "unknown",  # numeric|categorical|date|boolean|geo|unknown
                "unique_count": uniq_count,
                "missing_count": missing_cnt,
                "missing_percentage": missing_pct,
                "min": None,
                "max": None,
                "mean": None,
                "median": None,
                "std": None,
                "skewness": None,
                "outliers_count": 0,
                "outliers_percentage": 0.0,
                "top_values": [],
            }

            # Check if name signals geographical
            is_geo = any(gk in col.lower() for gk in geo_keywords)

            # 1. Boolean detection
            is_bool = False
            if pd.api.types.is_bool_dtype(s):
                is_bool = True
            elif uniq_count <= 2 and uniq_count > 0:
                # check string values or numeric representation
                vals = set(str(v).lower().strip() for v in non_null_s.unique())
                _bool_vocab = {"true", "false", "1", "0", "yes", "no", "y", "n", "t", "f", "on", "off"}
                if vals.issubset(_bool_vocab):
                    is_bool = True

            if is_bool:
                col_profile["kind"] = "boolean"
                boolean_cols.append(col)
                # min/max for boolean
                if uniq_count > 0:
                    col_profile["min"] = str(non_null_s.min())
                    col_profile["max"] = str(non_null_s.max())

            # 2. Date/Time detection
            elif pd.api.types.is_datetime64_any_dtype(s):
                col_profile["kind"] = "date"
                date_cols.append(col)
                col_profile["min"] = self._safe_min(s)
                col_profile["max"] = self._safe_max(s)

            # 3. Numeric detection
            elif pd.api.types.is_numeric_dtype(s) and not is_bool:
                col_profile["kind"] = "numeric"
                numeric_cols.append(col)
                col_profile["min"] = self._safe_min(s)
                col_profile["max"] = self._safe_max(s)
                
                # Detailed stats
                if not non_null_s.empty:
                    col_profile["mean"] = self._safe_float(non_null_s.mean())
                    col_profile["median"] = self._safe_float(non_null_s.median())
                    col_profile["std"] = self._safe_float(non_null_s.std())
                    col_profile["skewness"] = self._safe_float(non_null_s.skew())
                    
                    # Outliers using IQR
                    try:
                        q1 = non_null_s.quantile(0.25)
                        q3 = non_null_s.quantile(0.75)
                        iqr = q3 - q1
                        if iqr > 0:
                            lower_b = q1 - 1.5 * iqr
                            upper_b = q3 + 1.5 * iqr
                            outliers = non_null_s[(non_null_s < lower_b) | (non_null_s > upper_b)]
                            col_profile["outliers_count"] = int(len(outliers))
                            col_profile["outliers_percentage"] = round(100 * len(outliers) / total_rows, 2)
                    except Exception:
                        pass

            # 4. Text / Parser fallback
            else:
                # Try parsing date
                parsed = None
                try:
                    parsed = pd.to_datetime(sample[col], errors="coerce", utc=False)
                except Exception:
                    pass

                if parsed is not None:
                    non_na = parsed.notna().sum()
                    if non_na >= max(5, int(0.7 * len(sample))):
                        col_profile["kind"] = "date"
                        date_cols.append(col)
                        parsed_full = pd.to_datetime(s, errors="coerce", utc=False)
                        col_profile["min"] = self._safe_min(parsed_full)
                        col_profile["max"] = self._safe_max(parsed_full)
                    else:
                        col_profile["kind"] = "categorical"
                        categorical_cols.append(col)
                else:
                    col_profile["kind"] = "categorical"
                    categorical_cols.append(col)

            # Override/supplement with Geo tag if detected
            if is_geo and col_profile["kind"] in ("categorical", "unknown"):
                col_profile["kind"] = "geo"
                geo_cols.append(col)

            # categorical top values
            if col_profile["kind"] in ("categorical", "geo"):
                vc = s.value_counts(dropna=True)
                top = vc.head(self.max_unique_values)
                col_profile["top_values"] = [
                    {"value": str(idx), "count": int(cnt)} for idx, cnt in top.items()
                ]

            profile["columns"][col] = col_profile

        # ── 5. Pearson Correlation Matrix ──
        correlations = []
        if len(numeric_cols) >= 2 and total_rows >= 5:
            try:
                # compute correlation on sample to ensure speed
                num_df = sample[numeric_cols].apply(pd.to_numeric, errors="coerce").dropna(how="all")
                corr_matrix = num_df.corr(method="pearson")
                for i, c1 in enumerate(numeric_cols):
                    for c2 in numeric_cols[i+1:]:
                        coef = corr_matrix.loc[c1, c2]
                        if not pd.isna(coef) and abs(coef) >= 0.4:
                            correlations.append({
                                "col1": c1,
                                "col2": c2,
                                "coefficient": round(float(coef), 3),
                                "strength": "strong" if abs(coef) >= 0.7 else "moderate"
                            })
            except Exception:
                pass
        profile["correlations"] = correlations

        # ── 6. Trend Detection ──
        trends = []
        if date_cols and numeric_cols:
            dcol = date_cols[0]  # use primary date column
            for ncol in numeric_cols:
                try:
                    tmp = sample[[dcol, ncol]].copy()
                    tmp[ncol] = pd.to_numeric(tmp[ncol], errors="coerce")
                    tmp = tmp.dropna()
                    if len(tmp) >= 6:
                        tmp["_date"] = pd.to_datetime(tmp[dcol], errors="coerce")
                        tmp = tmp.dropna(subset=["_date"]).sort_values("_date")
                        n = len(tmp)
                        if n >= 6:
                            first_avg = tmp[ncol].iloc[:n//2].mean()
                            second_avg = tmp[ncol].iloc[n//2:].mean()
                            if first_avg != 0 and not pd.isna(first_avg) and not pd.isna(second_avg):
                                change = (second_avg - first_avg) / abs(first_avg)
                                if abs(change) >= 0.05:  # 5% change threshold
                                    trends.append({
                                        "date_col": dcol,
                                        "num_col": ncol,
                                        "direction": "upward" if change > 0 else "downward",
                                        "change_pct": round(float(change * 100), 2)
                                    })
                except Exception:
                    pass
        profile["trends"] = trends

        # ── 7. Health Score and Alerts ──
        alerts = []
        health_score = 100.0

        # missing values penalty
        total_cells = total_rows * len(df.columns)
        total_missing = sum(col_profile["missing_count"] for col_profile in profile["columns"].values())
        missing_pct_all = (100 * total_missing / total_cells) if total_cells > 0 else 0.0
        health_score -= missing_pct_all * 1.5

        # duplicate penalty
        dupe_count = int(df.duplicated().sum())
        dupe_pct = (100 * dupe_count / total_rows) if total_rows > 0 else 0.0
        health_score -= dupe_pct * 1.0

        # outlier penalty
        total_outliers = sum(col_profile["outliers_count"] for col_profile in profile["columns"].values())
        outlier_pct_all = (100 * total_outliers / total_rows) if total_rows > 0 else 0.0
        health_score -= outlier_pct_all * 0.5

        profile["health_score"] = max(0, min(100, int(health_score)))

        # Generate Alerts
        for col, col_profile in profile["columns"].items():
            if col_profile["missing_percentage"] > 20.0:
                alerts.append(f"Column '{col}' has high rate of missing values: {col_profile['missing_percentage']}%")
            if col_profile["outliers_percentage"] > 10.0:
                alerts.append(f"Column '{col}' has substantial outliers: {col_profile['outliers_count']} detected ({col_profile['outliers_percentage']}%)")
            if col_profile["skewness"] is not None and abs(col_profile["skewness"]) > 2.0:
                direction = "right-skewed" if col_profile["skewness"] > 0 else "left-skewed"
                alerts.append(f"Column '{col}' is highly skewed ({direction}, skew={round(col_profile['skewness'], 2)})")

        if dupe_pct > 5.0:
            alerts.append(f"Dataset contains {dupe_count} duplicate rows ({round(dupe_pct, 1)}%)")

        profile["alerts"] = alerts

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

    def _safe_float(self, v):
        try:
            f = float(v)
            return None if math.isnan(f) or math.isinf(f) else f
        except Exception:
            return None
