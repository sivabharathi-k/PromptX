"""
Enterprise AI Insights Engine — generates comprehensive 12-section analysis
for any tabular dataset uploaded to the platform.

Output Format:
  📊 Dataset Overview
  🔍 Data Quality Assessment
  📈 Statistical Summary
  ⚠️ Outlier Analysis
  🔗 Correlation Insights
  📉 Trend Analysis
  📂 Category Analysis
  🏆 Performance Analysis
  🚨 Anomaly Detection
  💡 Key Business Insights
  ✅ Recommendations
  📋 Executive Summary
"""

from __future__ import annotations

import math
import numpy as np
import pandas as pd

from backend.utils.active_dataset_store import get_active_connection, active_dataset_exists


# Performance: for large datasets, compute expensive stats on a bounded sample
MAX_ROWS_FOR_FULL_ANALYSIS = 100000
DEFAULT_SAMPLE_SIZE = 20000


def _maybe_sample(df: pd.DataFrame) -> pd.DataFrame:
    """Return full df when small; otherwise return a deterministic sample."""
    try:
        n = len(df)
        if n <= MAX_ROWS_FOR_FULL_ANALYSIS:
            return df
        sample_n = min(DEFAULT_SAMPLE_SIZE, max(5000, int(0.2 * n)))
        return df.sample(n=sample_n, random_state=42)
    except Exception:
        return df


def _safe_to_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _classify_columns(df: pd.DataFrame) -> dict:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    for c in df.columns:
        if c in numeric_cols:
            continue
        if df[c].dtype == "object":
            num = pd.to_numeric(df[c], errors="coerce")
            if num.notna().sum() >= max(10, int(0.3 * len(df))):
                numeric_cols.append(c)

    numeric_cols = list(dict.fromkeys(numeric_cols))

    date_cols = []
    for c in df.columns:
        if c in numeric_cols:
            continue
        if df[c].dtype == "object":
            parsed = pd.to_datetime(df[c], errors="coerce", utc=False)
            if parsed.notna().sum() >= max(10, int(0.3 * len(df))):
                date_cols.append(c)

    categorical_cols = [c for c in df.columns if c not in numeric_cols and c not in date_cols]

    return {
        "numeric_cols": numeric_cols,
        "date_cols": date_cols,
        "categorical_cols": categorical_cols,
    }


def compute_dataset_overview() -> dict:
    """
    Compute a comprehensive Dataset Overview for the active dataset.
    Works with ANY dataset (no hardcoded column names).
    
    Returns:
        dict with: total_rows, total_columns, dataset_size, column_type_counts,
                   missing_values_summary, duplicate_count, key_fields, health_score
    """
    try:
        import math
        if not active_dataset_exists():
            return {"success": False, "error": "No active dataset."}
        
        conn = get_active_connection()
        try:
            df = pd.read_sql("SELECT * FROM dataset", conn)
        finally:
            conn.close()
        
        if df.empty:
            return {"success": False, "error": "Dataset is empty."}
        
        total_rows = len(df)
        total_columns = len(df.columns)
        
        # ── Dataset Size (memory usage + approximate file size) ──
        memory_bytes = df.memory_usage(deep=True).sum()
        memory_mb = round(memory_bytes / (1024 * 1024), 2)
        if memory_mb < 1:
            size_str = f"{round(memory_bytes / 1024, 1)} KB"
        else:
            size_str = f"{memory_mb} MB"
        
        # ── Column Type Distribution using master schema (single source of truth) ──
        from backend.utils.active_dataset_store import get_master_schema
        master_schema = get_master_schema()
        
        boolean_columns = set()
        if master_schema:
            # Use master schema for classification
            numeric_count = sum(1 for v in master_schema.values() if v == "NUM")
            categorical_count = sum(1 for v in master_schema.values() if v == "TEXT")
            date_count = sum(1 for v in master_schema.values() if v == "DATE")
            boolean_count = 0
            # Detect boolean columns from actual data
            for col in df.columns:
                unique_vals = df[col].dropna().unique()
                if 0 < len(unique_vals) <= 2:
                    bool_set = {str(v).lower().strip() for v in unique_vals}
                    if bool_set.issubset({"true", "false", "1", "0", "yes", "no", "t", "f", "y", "n"}):
                        boolean_columns.add(col)
                        boolean_count += 1
                        if master_schema.get(col) == "NUM":
                            numeric_count -= 1
                        elif master_schema.get(col) == "TEXT":
                            categorical_count -= 1
        else:
            # Fallback: classify from dataframe dtypes + heuristic
            numeric_count = 0
            categorical_count = 0
            date_count = 0
            boolean_count = 0
            for col in df.columns:
                if pd.api.types.is_numeric_dtype(df[col]):
                    numeric_count += 1
                elif pd.api.types.is_datetime64_any_dtype(df[col]):
                    date_count += 1
                elif df[col].dtype == "bool":
                    boolean_count += 1
                else:
                    # Check for boolean-like string columns
                    unique_vals = df[col].dropna().unique()
                    if 1 <= len(unique_vals) <= 2:
                        bool_set = {str(v).lower().strip() for v in unique_vals}
                        if bool_set.issubset({"true", "false", "1", "0", "yes", "no", "t", "f", "y", "n", ""}):
                            boolean_columns.add(col)
                            boolean_count += 1
                            continue
                    categorical_count += 1
        
        # ── Data Quality Summary ──
        missing_mask = df.isna() | df.astype(str).apply(lambda col: col.str.strip().eq(""))
        total_missing = int(missing_mask.sum().sum())
        missing_pct = round(total_missing / (total_rows * total_columns) * 100, 2) if total_rows * total_columns > 0 else 0
        duplicate_count = int(df.duplicated().sum())
        empty_columns = int(missing_mask.all(axis=0).sum())

        checked_values = 0
        inconsistent_values = 0
        sampled = _maybe_sample(df)
        for col in sampled.columns:
            source = sampled[col].dropna()
            master_type = master_schema.get(col) if master_schema else None
            if master_type == "NUM":
                checked_values += len(source)
                inconsistent_values += int(pd.to_numeric(source, errors="coerce").isna().sum())
            elif master_type == "DATE":
                checked_values += len(source)
                inconsistent_values += int(pd.to_datetime(source, errors="coerce").isna().sum())
        consistency_pct = round(
            100 * (1 - inconsistent_values / checked_values), 2
        ) if checked_values else 100.0
        
        # ── Key Fields Detection (no hardcoded column names) ──
        id_column = None
        date_column = None
        measure_columns = []
        
        unique_candidates = []
        for col in df.columns:
            col_lower = col.lower().strip()
            non_missing = int(df[col].notna().sum())
            unique_ratio = df[col].nunique(dropna=True) / max(non_missing, 1)
            if non_missing == total_rows and unique_ratio >= 0.98:
                unique_candidates.append((unique_ratio, col))
            
            # Detect ID column: column name hints like id, code, key, or primary-key-like unique values
            if not id_column:
                id_hints = ["id", "code", "key", "identifier", "primary", "uuid", "sk", "pk", "record"]
                is_id_hint = any(h in col_lower for h in id_hints)
                if is_id_hint or col_lower in ("id", "code"):
                    unique_ratio = df[col].nunique() / max(total_rows, 1)
                    if unique_ratio >= 0.7:
                        id_column = col
                        continue
            
            # Detect date column
            if not date_column:
                date_hints = ["date", "time", "timestamp", "datetime", "year", "month", "day", "period", "created", "updated"]
                master_type = master_schema.get(col) if master_schema else None
                if master_type == "DATE" or any(h in col_lower for h in date_hints):
                    date_column = col
                    continue
            
            # Detect main measure columns (numeric with high variance)
            if master_schema:
                master_type = master_schema.get(col)
                if master_type == "NUM" and col not in boolean_columns:
                    measure_columns.append(col)
            elif pd.api.types.is_numeric_dtype(df[col]) and col not in boolean_columns:
                measure_columns.append(col)

        if not id_column and unique_candidates:
            unique_candidates.sort(reverse=True)
            id_column = unique_candidates[0][1]
        
        # Limit measure columns to top 5 by variance
        if len(measure_columns) > 5:
            var_scores = []
            for c in measure_columns:
                try:
                    s = pd.to_numeric(df[c], errors="coerce").dropna()
                    if len(s) > 1:
                        var_scores.append((c, float(s.var())))
                except Exception:
                    pass
            var_scores.sort(key=lambda x: x[1], reverse=True)
            measure_columns = [c for c, _ in var_scores[:5]]
        
        # ── Dataset Health Score ──
        health_score = 100
        
        # Deductions for missing values
        if total_missing > 0:
            missing_penalty = min(missing_pct * 0.8, 25)
            health_score -= missing_penalty
        
        # Deductions for duplicates
        if duplicate_count > 0:
            dup_pct = duplicate_count / max(total_rows, 1) * 100
            dup_penalty = min(dup_pct * 0.6, 15)
            health_score -= dup_penalty
        
        health_score -= min((empty_columns / max(total_columns, 1)) * 25, 25)
        health_score -= min(100 - consistency_pct, 20)
        
        health_score = max(0, min(100, round(health_score)))
        
        # Classification
        if health_score >= 90:
            status = "Excellent"
        elif health_score >= 75:
            status = "Good"
        elif health_score >= 50:
            status = "Fair"
        else:
            status = "Poor"
        
        # ── Schema Details (per-column metadata) ──
        schema_details = []
        for col in df.columns:
            col_type = master_schema.get(col, "TEXT") if master_schema else "TEXT"
            null_count = int(df[col].isna().sum())
            unique_count = int(df[col].nunique())
            
            # SQLite type mapping
            sqlite_type = col_type
            if col_type == "NUM":
                sqlite_type = "REAL" if df[col].dropna().dtype.kind == 'f' else "INTEGER"
            elif col_type == "DATE":
                sqlite_type = "TEXT"
            else:
                sqlite_type = "TEXT"
            
            # Sample values (up to 3 non-null)
            samples = df[col].dropna().drop_duplicates().head(3).tolist()
            sample_strs = []
            for s in samples:
                try:
                    sv = str(s)
                    if len(sv) > 100:
                        sv = sv[:100] + "..."
                    sample_strs.append(sv)
                except Exception:
                    sample_strs.append(str(s))
            
            schema_details.append({
                "column_name": col,
                "sqlite_type": sqlite_type,
                "null_count": null_count,
                "unique_count": unique_count,
                "sample_values": sample_strs,
            })
        
        return {
            "success": True,
            "total_records": total_rows,
            "total_rows": total_rows,
            "total_columns": total_columns,
            "dataset_size": size_str,
            "dataset_size_mb": memory_mb,
            "column_types": {
                "numeric": numeric_count,
                "categorical": categorical_count,
                "date": date_count,
                "boolean": boolean_count,
            },
            "data_quality": {
                "total_missing_values": total_missing,
                "missing_percentage": missing_pct,
                "duplicate_records": duplicate_count,
                "duplicate_percentage": round(duplicate_count / max(total_rows, 1) * 100, 2),
                "empty_columns": empty_columns,
                "consistency_percentage": consistency_pct,
            },
            "key_fields": {
                "primary_id": id_column,
                "date_column": date_column,
                "measure_columns": measure_columns[:5],
            },
            "health_score": {
                "score": health_score,
                "status": status,
            },
            "column_names": list(df.columns),
            "schema_details": schema_details,
        }
    except Exception as e:
        import logging
        logger = logging.getLogger("insights_engine")
        logger.exception("compute_dataset_overview failed: %s", str(e))
        return {"success": False, "error": f"Overview computation failed: {str(e)}"}


def _pick_primary_metric(df: pd.DataFrame, numeric_cols: list[str]) -> str | None:
    if not numeric_cols:
        return None

    preferred = [
        "score", "mark", "grade", "gpa", "points", "total", "average",
        "attendance", "performance", "salary", "revenue", "sales", "profit",
        "revenue", "cost", "rate", "value", "amount", "price",
    ]

    for c in numeric_cols:
        lc = c.lower()
        if any(p in lc for p in preferred):
            return c

    best = None
    best_var = -1
    for c in numeric_cols:
        x = _safe_to_numeric(df[c])
        if x.dropna().shape[0] < 5:
            continue
        v = float(x.var()) if not math.isnan(float(x.var())) else 0.0
        if v > best_var:
            best_var = v
            best = c
    return best or numeric_cols[0]


def _to_jsonable(v):
    if v is None:
        return None
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv
    if isinstance(v, (np.bool_,)):
        return bool(v)
    if isinstance(v, (pd.Timestamp,)):
        return str(v)
    if isinstance(v, dict):
        return {str(k): _to_jsonable(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_to_jsonable(x) for x in v]
    if isinstance(v, (str, int, float, bool)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    return str(v)


def _compute_statistical_analysis(df: pd.DataFrame, numeric_cols: list[str]) -> list[dict]:
    stats = []
    for col in numeric_cols[:10]:
        s = _safe_to_numeric(df[col]).dropna()
        if s.empty:
            continue
        q1 = float(s.quantile(0.25))
        q2 = float(s.median())
        q3 = float(s.quantile(0.75))
        iqr = q3 - q1
        mean_val = float(s.mean())
        std_val = float(s.std())

        skewness = "Normal"
        if mean_val > q2:
            skewness = "Right-skewed (positive skew)"
        elif mean_val < q2:
            skewness = "Left-skewed (negative skew)"

        cv = std_val / mean_val if mean_val != 0 else 0
        variability = "High" if cv > 0.5 else "Medium" if cv > 0.2 else "Low"

        stats.append({
            "column": col,
            "count": int(s.count()),
            "mean": round(mean_val, 4),
            "median": round(q2, 4),
            "mode": round(float(s.mode().iloc[0]), 4) if not s.mode().empty else None,
            "std": round(std_val, 4),
            "variance": round(float(s.var()), 4),
            "min": round(float(s.min()), 4),
            "max": round(float(s.max()), 4),
            "q1": round(q1, 4),
            "q3": round(q3, 4),
            "iqr": round(iqr, 4),
            "skewness": skewness,
            "variability": variability,
        })
    return stats


def _compute_category_analysis(df: pd.DataFrame, cat_cols: list[str], numeric_cols: list[str], primary_metric: str | None) -> list[dict]:
    """Compute top/bottom categories and percentage contribution for categorical columns."""
    if not cat_cols:
        return []

    results = []
    for cat_col in cat_cols[:5]:
        if df[cat_col].nunique() < 2 or df[cat_col].nunique() > 50:
            continue

        vc = df[cat_col].value_counts()
        total = int(vc.sum())
        top_values = vc.head(10)
        bottom_values = vc.tail(10)

        top_items = []
        for name, count in top_values.items():
            pct = round(count / total * 100, 2) if total > 0 else 0
            top_items.append({"name": str(name), "count": int(count), "percentage": pct})

        bottom_items = []
        for name, count in bottom_values.items():
            pct = round(count / total * 100, 2) if total > 0 else 0
            bottom_items.append({"name": str(name), "count": int(count), "percentage": pct})

        # Concentration analysis
        top3_pct = sum(item["percentage"] for item in top_items[:3]) if len(top_items) >= 3 else 0
        concentration = "High" if top3_pct > 70 else "Medium" if top3_pct > 40 else "Low"

        entry = {
            "column": cat_col,
            "unique_values": int(df[cat_col].nunique()),
            "total_records": total,
            "top_categories": top_items[:5],
            "bottom_categories": bottom_items[:5],
            "top_3_concentration_pct": round(top3_pct, 2),
            "concentration": concentration,
        }

        # Metric-based analysis (if primary metric available)
        if primary_metric and primary_metric in df.columns:
            grp = df.groupby(cat_col)[primary_metric].agg(["sum", "mean", "count"]).reset_index()
            grp.columns = [cat_col, "sum", "mean", "count"]
            grp = grp.sort_values("mean", ascending=False)
            total_metric = float(grp["sum"].sum())
            if total_metric > 0:
                best = grp.iloc[0]
                worst = grp.iloc[-1]
                best_contribution = round(float(best["sum"]) / total_metric * 100, 2) if total_metric > 0 else 0
                entry["best_performer"] = {
                    "name": str(best[cat_col]),
                    "mean": round(float(best["mean"]), 4),
                    "sum": round(float(best["sum"]), 2),
                    "contribution_pct": best_contribution,
                }
                entry["worst_performer"] = {
                    "name": str(worst[cat_col]),
                    "mean": round(float(worst["mean"]), 4),
                    "sum": round(float(worst["sum"]), 2),
                }

        results.append(entry)

    return results


def _compute_performance_analysis(df: pd.DataFrame, numeric_cols: list[str], cat_cols: list[str], primary_metric: str | None) -> list[dict]:
    """Identify top/bottom performing records and segments."""
    results = []

    if primary_metric:
        s = _safe_to_numeric(df[primary_metric]).dropna()
        if not s.empty:
            # Top records
            top_n = df.nlargest(min(10, len(df)), primary_metric)[[primary_metric] + [c for c in cat_cols[:2] if c in df.columns]].reset_index(drop=True)
            bottom_n = df.nsmallest(min(10, len(df)), primary_metric)[[primary_metric] + [c for c in cat_cols[:2] if c in df.columns]].reset_index(drop=True)

            top_records = []
            for _, r in top_n.iterrows():
                record = {col: _to_jsonable(r[col]) for col in top_n.columns}
                top_records.append(record)

            bottom_records = []
            for _, r in bottom_n.iterrows():
                record = {col: _to_jsonable(r[col]) for col in bottom_n.columns}
                bottom_records.append(record)

            results.append({
                "metric": primary_metric,
                "total_records": int(len(df)),
                "top_records": top_records,
                "bottom_records": bottom_records,
                "top_mean": round(float(top_n[primary_metric].mean()), 4),
                "bottom_mean": round(float(bottom_n[primary_metric].mean()), 4),
                "gap": round(float(top_n[primary_metric].mean() - bottom_n[primary_metric].mean()), 4),
            })

    # Segment analysis by category
    if cat_cols and primary_metric:
        for cat_col in cat_cols[:3]:
            if df[cat_col].nunique() < 2 or df[cat_col].nunique() > 30:
                continue
            grp = df.groupby(cat_col)[primary_metric].agg(["mean", "sum", "count"]).reset_index()
            grp.columns = [cat_col, "mean", "sum", "count"]
            grp = grp.sort_values("mean", ascending=False)
            if len(grp) >= 2:
                results.append({
                    "segment_column": cat_col,
                    "metric": primary_metric,
                    "best_segment": str(grp.iloc[0][cat_col]),
                    "best_mean": round(float(grp.iloc[0]["mean"]), 4),
                    "worst_segment": str(grp.iloc[-1][cat_col]),
                    "worst_mean": round(float(grp.iloc[-1]["mean"]), 4),
                    "segment_count": len(grp),
                    "performance_gap": round(float(grp.iloc[0]["mean"] - grp.iloc[-1]["mean"]), 4),
                })

    return results


def _detect_outliers(df: pd.DataFrame, numeric_cols: list[str]) -> list[dict]:
    outliers = []
    for col in numeric_cols:
        s = _safe_to_numeric(df[col]).dropna()
        if s.shape[0] < 10:
            continue
        q1 = float(s.quantile(0.25))
        q3 = float(s.quantile(0.75))
        iqr = q3 - q1
        low = q1 - 1.5 * iqr
        high = q3 + 1.5 * iqr
        out_low = int((s < low).sum())
        out_high = int((s > high).sum())
        total_outliers = out_low + out_high
        outlier_pct = round(total_outliers / len(s) * 100, 2)

        if total_outliers > 0:
            severity = "HIGH" if outlier_pct > 10 else "MEDIUM" if outlier_pct > 5 else "LOW"
            outliers.append({
                "column": col,
                "low_outliers": out_low,
                "high_outliers": out_high,
                "total_outliers": total_outliers,
                "outlier_pct": outlier_pct,
                "low_threshold": round(low, 4),
                "high_threshold": round(high, 4),
                "q1": round(q1, 4),
                "q3": round(q3, 4),
                "iqr": round(iqr, 4),
                "severity": severity,
            })

    return outliers


def _compute_correlation_analysis(df: pd.DataFrame, numeric_cols: list[str]) -> dict:
    if len(numeric_cols) < 2:
        return {"matrix": [], "strong_positive": [], "strong_negative": [], "note": "Need at least 2 numeric columns"}

    cols = numeric_cols[:15]
    corr_df = df[cols].corr()

    matrix = []
    labels = cols
    for col1 in cols:
        row_data = []
        for col2 in cols:
            val = corr_df.loc[col1, col2]
            if isinstance(val, (float, np.floating)):
                row_data.append(round(float(val), 4))
            else:
                row_data.append(0)
        matrix.append(row_data)

    strong_positive = []
    strong_negative = []
    weak = []

    for i, col1 in enumerate(cols):
        for j, col2 in enumerate(cols):
            if i >= j:
                continue
            val = round(float(corr_df.loc[col1, col2]), 4)
            if val >= 0.5:
                strong_positive.append({"var1": col1, "var2": col2, "r": val})
            elif val <= -0.5:
                strong_negative.append({"var1": col1, "var2": col2, "r": val})
            elif abs(val) < 0.2:
                weak.append({"var1": col1, "var2": col2, "r": val})

    strong_positive = sorted(strong_positive, key=lambda x: abs(x["r"]), reverse=True)
    strong_negative = sorted(strong_negative, key=lambda x: abs(x["r"]), reverse=True)

    return {
        "matrix": matrix,
        "labels": labels,
        "strong_positive": strong_positive[:10],
        "strong_negative": strong_negative[:10],
        "weak_relationships": weak[:10],
        "note": None,
    }


def _compute_trends(df: pd.DataFrame, date_cols: list[str], numeric_cols: list[str]) -> list[dict]:
    if not date_cols or not numeric_cols:
        return []

    trends = []
    for dc in date_cols[:2]:
        for nc in numeric_cols[:3]:
            tmp = df[[dc, nc]].copy()
            tmp[dc] = pd.to_datetime(tmp[dc], errors="coerce")
            tmp[nc] = _safe_to_numeric(tmp[nc])
            tmp = tmp.dropna(subset=[dc, nc])
            if tmp.shape[0] < 15:
                continue

            tmp["__month"] = tmp[dc].dt.to_period("M").astype(str)
            monthly = tmp.groupby("__month")[nc].agg(["mean", "sum", "count"]).reset_index()
            monthly = monthly.sort_values("__month")

            if monthly.shape[0] < 3:
                continue

            y = monthly["mean"].values
            x_idx = list(range(len(y)))
            x_mean = sum(x_idx) / len(x_idx)
            y_mean = sum(y) / len(y)
            denom = sum((xi - x_mean) ** 2 for xi in x_idx) or 1
            slope = sum((x_idx[i] - x_mean) * (y[i] - y_mean) for i in range(len(x_idx))) / denom

            direction = "upward" if slope > 0 else "downward"
            strength = "strong" if abs(slope) > 1 else "moderate" if abs(slope) > 0.1 else "slight"

            # MoM analysis
            mom_changes = []
            monthly_vals = monthly["mean"].tolist()
            for i in range(1, len(monthly_vals)):
                prev = monthly_vals[i - 1]
                curr = monthly_vals[i]
                if prev != 0:
                    change_pct = round((curr - prev) / abs(prev) * 100, 2)
                else:
                    change_pct = 0
                mom_changes.append({
                    "period": monthly["__month"].iloc[i],
                    "change_pct": change_pct,
                    "direction": "up" if change_pct > 0 else "down" if change_pct < 0 else "flat",
                })

            # Detect seasonal pattern (check if highs cluster at certain times)
            seasonal = None
            if len(monthly_vals) >= 6:
                first_half_avg = sum(monthly_vals[:len(monthly_vals)//2]) / (len(monthly_vals)//2)
                second_half_avg = sum(monthly_vals[len(monthly_vals)//2:]) / (len(monthly_vals) - len(monthly_vals)//2)
                if second_half_avg > first_half_avg * 1.1:
                    seasonal = "Growth accelerated in later periods"
                elif first_half_avg > second_half_avg * 1.1:
                    seasonal = "Growth decelerated in later periods"

            labels = monthly["__month"].tolist()
            values = [round(float(v), 4) for v in monthly["mean"].tolist()]

            trends.append({
                "date_column": dc,
                "metric": nc,
                "direction": direction,
                "strength": strength,
                "slope": round(float(slope), 6),
                "periods": len(labels),
                "monthly_data": [{"period": str(b), "mean": round(float(m), 4)} for b, m in zip(labels, values)],
                "mom_analysis": mom_changes[-6:],  # last 6 MoM changes
                "seasonal_pattern": seasonal,
                "chart": {
                    "plotType": "line",
                    "title": f"Trend of {nc} over {dc}",
                    "labels": labels,
                    "series": [{"label": nc, "data": values, "labels": labels}],
                },
            })

    return trends


def _compute_data_quality(df: pd.DataFrame) -> dict:
    total_rows = len(df)

    missing_cols = []
    for c in df.columns:
        nulls = int(df[c].isna().sum())
        blanks = int(df[c].astype(str).str.strip().eq("").sum()) if df[c].dtype == "object" else 0
        total_missing = nulls + blanks
        pct = round(total_missing / total_rows * 100, 2) if total_rows > 0 else 0
        if total_missing > 0:
            severity = "HIGH" if pct > 20 else "MEDIUM" if pct > 5 else "LOW"
            missing_cols.append({
                "column": c,
                "nulls": nulls,
                "blanks": blanks,
                "total_missing": total_missing,
                "missing_pct": pct,
                "severity": severity,
            })

    dupes_count = int(df.duplicated().sum())
    dupe_pct = round(dupes_count / total_rows * 100, 2) if total_rows > 0 else 0

    constant_cols = []
    for c in df.columns:
        if df[c].nunique() == 1:
            constant_cols.append(c)

    empty_cols = [c for c in df.columns if df[c].isna().all() or df[c].nunique() == 0]

    # Data consistency issues
    consistency_issues = []
    for c in df.select_dtypes(include="object").columns[:10]:
        # Check for mixed types (numbers stored as text)
        sample = df[c].dropna().astype(str).head(50)
        numeric_count = sum(1 for v in sample if v.replace("-", "", 1).replace(".", "", 1).isdigit())
        total_sample = len(sample)
        if 0 < numeric_count < total_sample:
            consistency_issues.append(f"Column '{c}' contains mixed data types (numbers and text).")

        # Check for inconsistent formatting
        if df[c].nunique() <= 20 and df[c].nunique() >= 2:
            vals = df[c].dropna().unique()
            # Check for leading/trailing whitespace issues
            has_whitespace = any(str(v).strip() != str(v) for v in vals)
            if has_whitespace:
                consistency_issues.append(f"Column '{c}' has values with leading/trailing whitespace.")

    return {
        "total_rows": total_rows,
        "total_columns": len(df.columns),
        "missing_values": {
            "total_missing_cells": int(df.isna().sum().sum()),
            "columns_with_missing": len(missing_cols),
            "missing_pct": round(int(df.isna().sum().sum()) / (total_rows * len(df.columns)) * 100, 2) if total_rows * len(df.columns) > 0 else 0,
            "column_details": missing_cols,
        },
        "duplicates": {
            "total_duplicate_rows": dupes_count,
            "duplicate_pct": dupe_pct,
            "severity": "HIGH" if dupe_pct > 10 else "MEDIUM" if dupe_pct > 3 else "LOW",
        },
        "constant_columns": constant_cols,
        "empty_columns": empty_cols,
        "consistency_issues": consistency_issues,
    }


def _compute_anomaly_detection(df: pd.DataFrame, numeric_cols: list[str], date_cols: list[str], outliers: list[dict]) -> list[dict]:
    """Detect unusual patterns, spikes, drops, and data inconsistencies."""
    anomalies = []

    # Z-score based anomalies for numeric columns
    for col in numeric_cols[:5]:
        s = _safe_to_numeric(df[col]).dropna()
        if s.shape[0] < 15:
            continue
        mean = float(s.mean())
        std = float(s.std())
        if std == 0:
            continue
        z_scores = ((s - mean) / std).abs()
        extreme_count = int((z_scores > 3).sum())
        if extreme_count > 0:
            extreme_pct = round(extreme_count / len(s) * 100, 2)
            if extreme_pct > 0:
                anomalies.append({
                    "column": col,
                    "type": "extreme_value",
                    "description": f"{extreme_count} extreme values (z-score > 3) found in '{col}' ({extreme_pct}% of data).",
                    "severity": "HIGH" if extreme_pct > 5 else "MEDIUM" if extreme_pct > 2 else "LOW",
                    "impact": f"These extreme values may skew averages and affect model performance on '{col}'.",
                })

    # Spike detection in time series
    if date_cols and numeric_cols:
        for dc in date_cols[:1]:
            for nc in numeric_cols[:2]:
                tmp = df[[dc, nc]].copy()
                tmp[dc] = pd.to_datetime(tmp[dc], errors="coerce")
                tmp[nc] = _safe_to_numeric(tmp[nc])
                tmp = tmp.dropna(subset=[dc, nc])
                if tmp.shape[0] < 20:
                    continue
                tmp["__period"] = tmp[dc].dt.to_period("M").astype(str)
                monthly = tmp.groupby("__period")[nc].mean().reset_index()
                monthly = monthly.sort_values("__period")
                if len(monthly) < 4:
                    continue
                values = monthly[nc].values
                overall_mean = float(values.mean())
                for i in range(len(monthly)):
                    v = float(values[i])
                    if overall_mean != 0 and abs(v - overall_mean) / abs(overall_mean) > 0.5:
                        direction = "spike" if v > overall_mean else "drop"
                        anomalies.append({
                            "column": nc,
                            "type": f"{direction}_detected",
                            "description": f"{direction.capitalize()} detected in '{nc}' during period '{monthly.iloc[i]['__period']}': {v:.2f} vs avg {overall_mean:.2f} ({'+' if v > overall_mean else ''}{((v - overall_mean) / abs(overall_mean) * 100):.1f}%).",
                            "severity": "HIGH" if abs(v - overall_mean) / abs(overall_mean) > 1.0 else "MEDIUM",
                            "impact": f"This {direction} may indicate a seasonal effect or an external factor affecting '{nc}'.",
                        })

    # Unexpected zeros or negative values
    for col in numeric_cols:
        s = _safe_to_numeric(df[col])
        zero_count = int((s == 0).sum())
        neg_count = int((s < 0).sum())
        if zero_count > 0 and zero_count > len(s) * 0.5:
            anomalies.append({
                "column": col,
                "type": "excessive_zeros",
                "description": f"Column '{col}' has {zero_count} zero values ({round(zero_count / len(s) * 100, 2)}% of data).",
                "severity": "MEDIUM",
                "impact": f"Excessive zeros may indicate missing data or a default value being used for '{col}'.",
            })
        if neg_count > 0 and col.lower() not in ["temperature", "change", "difference", "balance", "net"]:
            neg_pct = round(neg_count / len(s) * 100, 2)
            if neg_pct > 1:
                anomalies.append({
                    "column": col,
                    "type": "negative_values",
                    "description": f"Column '{col}' has {neg_count} negative values ({neg_pct}% of data).",
                    "severity": "LOW",
                    "impact": f"Negative values in '{col}' may be valid or indicate data entry errors.",
                })

    # Use outlier data for additional anomaly context
    for o in outliers:
        if o["severity"] == "HIGH":
            anomalies.append({
                "column": o["column"],
                "type": "high_severity_outliers",
                "description": f"High-severity outliers detected in '{o['column']}': {o['total_outliers']} outliers ({o['outlier_pct']}%).",
                "severity": "HIGH",
                "impact": f"Outliers in '{o['column']}' may represent exceptional cases or data quality issues requiring investigation.",
            })

    return anomalies


def _compute_business_insights(df: pd.DataFrame, col_info: dict, primary_metric: str | None, trends: list[dict], cat_analysis: list[dict], outliers: list[dict], correlations: dict, anomalies: list[dict]) -> list[dict]:
    """Generate meaningful human-readable business insights based on data patterns."""
    insights = []
    numeric_cols = col_info["numeric_cols"]
    cat_cols = col_info["categorical_cols"]

    # Revenue/volume concentration insights
    for ca in cat_analysis:
        if ca.get("concentration") == "High":
            top_cat = ca["top_categories"][0]["name"] if ca["top_categories"] else "N/A"
            top_pct = ca["top_categories"][0]["percentage"] if ca["top_categories"] else 0
            insights.append({
                "type": "concentration_risk",
                "title": f"High concentration in '{ca['column']}'",
                "description": f"The top category '{top_cat}' represents {top_pct}% of records in '{ca['column']}'. Top 3 categories account for {ca['top_3_concentration_pct']}% of data.",
                "impact": "This concentration creates dependency risk. A shift in this segment could significantly impact overall performance.",
                "priority": "HIGH",
            })

    # Trend-based insights
    for t in trends:
        if t["direction"] == "upward":
            insights.append({
                "type": "growth_opportunity",
                "title": f"Positive trend in {t['metric']}",
                "description": f"'{t['metric']}' is showing a {t['strength']} upward trend over {t['date_column']} (slope: {t['slope']}). This indicates sustained growth.",
                "impact": "Continue investing in drivers that support this growth trajectory. Consider expanding successful strategies.",
                "priority": "HIGH" if t["strength"] == "strong" else "MEDIUM",
            })
        elif t["direction"] == "downward":
            insights.append({
                "type": "declining_trend",
                "title": f"Declining trend in {t['metric']}",
                "description": f"'{t['metric']}' is showing a {t['strength']} downward trend over {t['date_column']} (slope: {t['slope']}). Requires attention.",
                "impact": "Investigate root causes for the decline. Consider corrective actions to reverse this trajectory.",
                "priority": "HIGH" if t["strength"] == "strong" else "MEDIUM",
            })

        # MoM insight
        if t.get("mom_analysis"):
            recent_mom = t["mom_analysis"][-1] if t["mom_analysis"] else None
            if recent_mom and abs(recent_mom["change_pct"]) > 20:
                insights.append({
                    "type": "recent_change",
                    "title": f"Significant recent change in {t['metric']}",
                    "description": f"Month-over-month change for '{t['metric']}' in period '{recent_mom['period']}' was {recent_mom['change_pct']:+.2f}%.",
                    "impact": "This recent change may indicate a shift in market conditions or operational performance.",
                    "priority": "MEDIUM",
                })

    # Performance gap insights
    if primary_metric and cat_cols:
        for cat_col in cat_cols[:2]:
            grp = df[[cat_col, primary_metric]].copy()
            grp[primary_metric] = _safe_to_numeric(grp[primary_metric])
            grp = grp.dropna(subset=[primary_metric])
            if grp.empty:
                continue
            gstats = grp.groupby(cat_col)[primary_metric].mean().reset_index(name="__mean__")
            gstats = gstats.sort_values("__mean__", ascending=False)
            if len(gstats) >= 2:
                top = gstats.iloc[0]
                bottom = gstats.iloc[-1]
                gap = float(top["__mean__"]) - float(bottom["__mean__"])
                gap_pct = gap / float(bottom["__mean__"]) * 100 if float(bottom["__mean__"]) != 0 else 0
                if gap > 0 and gap_pct > 10:
                    insights.append({
                        "type": "performance_gap",
                        "title": f"Significant performance gap in '{cat_col}'",
                        "description": f"'{top[cat_col]}' outperforms '{bottom[cat_col]}' by {gap:.2f} ({gap_pct:.1f}%) in {primary_metric}.",
                        "impact": f"There is a {len(gstats)}-segment variance. Best practices from top performers could lift bottom segments.",
                        "priority": "HIGH" if gap_pct > 50 else "MEDIUM",
                    })

    # Skewness insight
    if primary_metric:
        s = _safe_to_numeric(df[primary_metric]).dropna()
        if not s.empty:
            mean_val = float(s.mean())
            median_val = float(s.median())
            if mean_val != 0 and abs(mean_val - median_val) / abs(mean_val) > 0.3:
                insights.append({
                    "type": "skewed_distribution",
                    "title": f"Skewed '{primary_metric}' distribution",
                    "description": f"The mean ({mean_val:.2f}) differs significantly from the median ({median_val:.2f}), indicating {primary_metric} is not evenly distributed.",
                    "impact": "Using median rather than mean for benchmarks would be more representative. A few high/low values may be skewing averages.",
                    "priority": "MEDIUM",
                })

    # Correlation insights
    for sp in correlations.get("strong_positive", [])[:2]:
        insights.append({
            "type": "correlation_opportunity",
            "title": f"Strong relationship: {sp['var1']} ↔ {sp['var2']}",
            "description": f"'{sp['var1']}' and '{sp['var2']}' have a strong positive correlation (r={sp['r']:.2f}). They tend to move together.",
            "impact": "Changes in one variable may predict changes in the other. Consider monitoring both for integrated decision-making.",
            "priority": "HIGH" if sp["r"] > 0.7 else "MEDIUM",
        })
    for sn in correlations.get("strong_negative", [])[:1]:
        insights.append({
            "type": "tradeoff_insight",
            "title": f"Inverse relationship: {sn['var1']} ↔ {sn['var2']}",
            "description": f"'{sn['var1']}' and '{sn['var2']}' have a strong negative correlation (r={sn['r']:.2f}).",
            "impact": "Improving one may come at the expense of the other. Look for an optimal balance point.",
            "priority": "MEDIUM",
        })

    # Outlier-based risk insights
    high_sev_outliers = [o for o in outliers if o["severity"] == "HIGH"]
    if high_sev_outliers:
        insights.append({
            "type": "data_quality_risk",
            "title": f"{len(high_sev_outliers)} high-severity outlier patterns detected",
            "description": f"Columns affected: {', '.join(o['column'] for o in high_sev_outliers[:3])}. These outliers may represent data errors or unusual business events.",
            "impact": "Investigate these outliers before using affected columns for forecasting or strategic decisions.",
            "priority": "HIGH",
        })

    # Anomaly-based insights
    high_sev_anomalies = [a for a in anomalies if a["severity"] == "HIGH"]
    if high_sev_anomalies:
        insights.append({
            "type": "anomaly_alert",
            "title": f"{len(high_sev_anomalies)} high-severity anomalies detected",
            "description": high_sev_anomalies[0]["description"],
            "impact": high_sev_anomalies[0]["impact"],
            "priority": "HIGH",
        })

    # Data quality insights
    if primary_metric:
        nulls_in_metric = int(df[primary_metric].isna().sum())
        if nulls_in_metric > 0:
            insights.append({
                "type": "missing_data_warning",
                "title": f"Missing values in key metric '{primary_metric}'",
                "description": f"Column '{primary_metric}' has {nulls_in_metric} missing values ({round(nulls_in_metric / len(df) * 100, 2)}% of records).",
                "impact": "Missing values in the primary metric can lead to incomplete analysis. Consider imputation or investigating why data is missing.",
                "priority": "MEDIUM",
            })

    # Segment diversity insight
    diverse_cols = [(c, df[c].nunique()) for c in cat_cols if 10 <= df[c].nunique() <= 100]
    if diverse_cols:
        diverse_cols.sort(key=lambda x: x[1], reverse=True)
        col_name, unique_count = diverse_cols[0]
        insights.append({
            "type": "segmentation_opportunity",
            "title": f"Rich segmentation possible with '{col_name}'",
            "description": f"Column '{col_name}' has {unique_count} unique values, offering granular segmentation for targeted analysis.",
            "impact": "Use this column for detailed customer/entity segmentation, personalized strategies, and micro-level performance analysis.",
            "priority": "MEDIUM",
        })

    return insights


def _compute_recommendations(df: pd.DataFrame, col_info: dict, primary_metric: str | None, trends: list[dict], cat_analysis: list[dict], outliers: list[dict], business_insights: list[dict], anomalies: list[dict], data_quality: dict) -> list[dict]:
    """Generate actionable recommendations based on all analysis results."""
    recommendations = []
    numeric_cols = col_info["numeric_cols"]
    cat_cols = col_info["categorical_cols"]

    # Data quality recommendations
    dq = data_quality
    if dq["missing_values"]["total_missing_cells"] > 0:
        pct = dq["missing_values"]["missing_pct"]
        if pct > 5:
            recommendations.append({
                "area": "Data Quality",
                "recommendation": "Address missing values in the dataset",
                "action": "Impute missing values using mean/median for numeric columns or mode for categorical columns. Consider using the 'clean' command: 'Fill missing values in [column] with [value]'.",
                "expected_impact": "Improved data completeness will lead to more accurate analysis and reliable insights.",
                "priority": "HIGH",
            })
        else:
            recommendations.append({
                "area": "Data Quality",
                "recommendation": "Monitor low-level missing values",
                "action": f"Only {pct}% of cells have missing values, which is acceptable. Verify the affected columns ({dq['missing_values']['columns_with_missing']} columns) to ensure missingness is random.",
                "expected_impact": "Prevent data quality from degrading over time.",
                "priority": "LOW",
            })

    if dq["duplicates"]["total_duplicate_rows"] > 0:
        recommendations.append({
            "area": "Data Quality",
            "recommendation": f"Remove {dq['duplicates']['total_duplicate_rows']} duplicate records",
            "action": "Use the 'Remove duplicate records' command to clean the dataset. This will improve accuracy of counts and aggregations.",
            "expected_impact": f"Cleaner data with {dq['duplicates']['duplicate_pct']}% fewer records, leading to more accurate analysis.",
            "priority": "HIGH" if dq["duplicates"]["severity"] == "HIGH" else "MEDIUM",
        })

    # Trend-based recommendations
    for t in trends:
        if t["direction"] == "downward" and t["strength"] in ("strong", "moderate"):
            recommendations.append({
                "area": "Performance",
                "recommendation": f"Investigate declining trend in '{t['metric']}'",
                "action": f"Analyze root causes for the downward trend in {t['metric']}. Consider querying: 'Show top 10 records by {t['metric']}' to identify where performance dropped most.",
                "expected_impact": "Reversing the decline could recover significant value. Target a return to previous performance levels.",
                "priority": "HIGH",
            })
        elif t["direction"] == "upward" and t["strength"] in ("strong", "moderate"):
            recommendations.append({
                "area": "Growth",
                "recommendation": f"Capitalize on positive trend in '{t['metric']}'",
                "action": f"Analyze what's driving the strong upward trend in {t['metric']}. Query: 'Show average {t['metric']} by key segments' to identify best performers.",
                "expected_impact": "Doubling down on successful strategies could accelerate growth further.",
                "priority": "MEDIUM",
            })

    # Category concentration recommendations
    for ca in cat_analysis:
        if ca.get("concentration") == "High":
            recommendations.append({
                "area": "Risk Management",
                "recommendation": f"Diversify concentration in '{ca['column']}'",
                "action": f"Top 3 categories in '{ca['column']}' represent {ca['top_3_concentration_pct']}% of data. Develop strategies to grow smaller segments to reduce dependency risk.",
                "expected_impact": "Lower concentration risk and more balanced portfolio across segments.",
                "priority": "HIGH",
            })

    # Outlier recommendations
    high_outliers = [o for o in outliers if o["severity"] == "HIGH"]
    if high_outliers:
        cols = ", ".join(o["column"] for o in high_outliers[:3])
        recommendations.append({
            "area": "Data Quality",
            "recommendation": f"Review high-severity outliers in {cols}",
            "action": f"Investigate the {len(high_outliers)} columns with high outlier percentages. Query: 'Show top 10 rows by {high_outliers[0]['column']}' to examine extreme values.",
            "expected_impact": "Identifying whether outliers are valid data or errors will improve analysis accuracy.",
            "priority": "MEDIUM",
        })

    # Performance gap recommendations
    for bi in business_insights:
        if bi["type"] == "performance_gap" and bi["priority"] == "HIGH":
            recommendations.append({
                "area": "Performance Improvement",
                "recommendation": bi["title"],
                "action": f"Analyze best practices from top-performing segments and apply to underperforming ones. Query: 'Show average {primary_metric} by segments' to identify specific gaps.",
                "expected_impact": "Closing performance gaps could significantly improve overall performance metrics.",
                "priority": "HIGH",
            })

    # Visualization recommendation
    if len(numeric_cols) >= 1 and len(cat_cols) >= 1:
        recommendations.append({
            "area": "Visualization",
            "recommendation": "Create visual dashboards for better monitoring",
            "action": f"Generate charts to visualize '{primary_metric or numeric_cols[0]}' across key categorical dimensions for faster pattern recognition.",
            "expected_impact": "Visual representations will help identify patterns and outliers more quickly than tabular data.",
            "priority": "MEDIUM",
        })

    # ML recommendation
    if len(numeric_cols) >= 3 and len(df) >= 100:
        recommendations.append({
            "area": "Advanced Analytics",
            "recommendation": "Consider predictive modeling for deeper insights",
            "action": f"With {len(numeric_cols)} numeric features and {len(df):,} records, you can build predictive models to forecast {primary_metric or numeric_cols[0]} or classify segments.",
            "expected_impact": "Predictive models can provide forward-looking insights for proactive decision-making.",
            "priority": "LOW",
        })

    # General recommendation if none triggered
    if not recommendations:
        if primary_metric:
            recommendations.append({
                "area": "Analysis",
                "recommendation": f"Explore {primary_metric} across different segments",
                "action": "Ask questions like: 'Show average " + str(primary_metric or "") + " by " + " or ".join(cat_cols[:2]) + "' to find performance patterns.",
                "expected_impact": "Deeper exploration can uncover hidden opportunities for improvement.",
                "priority": "MEDIUM",
            })
        else:
            recommendations.append({
                "area": "Exploration",
                "recommendation": "Explore the dataset further",
                "action": "Ask questions about specific columns to discover patterns and insights hidden in the data.",
                "expected_impact": "Further analysis will reveal actionable patterns and trends.",
                "priority": "LOW",
            })

    return recommendations


def _compute_executive_summary(df: pd.DataFrame, col_info: dict, primary_metric: str | None, trends: list[dict], outliers: list[dict], anomalies: list[dict], business_insights: list[dict], data_quality: dict, cat_analysis: list[dict], dataset_type: str) -> list[str]:
    """Generate a concise management-level executive summary."""
    numeric_cols = col_info["numeric_cols"]
    cat_cols = col_info["categorical_cols"]
    date_cols = col_info["date_cols"]
    total_rows = len(df)
    total_cols = len(df.columns)

    points = []

    # 1. What the dataset is
    points.append(
        f"This {dataset_type} dataset contains **{total_rows:,} records** across **{total_cols} columns** "
        f"({len(numeric_cols)} numeric, {len(cat_cols)} categorical, {len(date_cols)} date-based)."
    )

    # 2. Key metric
    if primary_metric:
        s = _safe_to_numeric(df[primary_metric]).dropna()
        if not s.empty:
            mean_val = float(s.mean())
            median_val = float(s.median())
            points.append(
                f"The primary metric **'{primary_metric}'** averages **{mean_val:.2f}** (median: {median_val:.2f}) across the dataset."
            )

    # 3. Data quality status
    missing = data_quality["missing_values"]["total_missing_cells"]
    dupes = data_quality["duplicates"]["total_duplicate_rows"]
    if missing == 0 and dupes == 0:
        points.append("Data quality is **excellent** — no missing values or duplicate records detected.")
    else:
        issues = []
        if missing > 0:
            issues.append(f"{missing:,} missing cells across {data_quality['missing_values']['columns_with_missing']} columns")
        if dupes > 0:
            issues.append(f"{dupes:,} duplicate records ({data_quality['duplicates']['duplicate_pct']}%)")
        points.append(f"Data quality requires attention: {' and '.join(issues)}.")

    # 4. Trend summary
    if trends:
        upward = [t for t in trends if t["direction"] == "upward"]
        downward = [t for t in trends if t["direction"] == "downward"]
        trend_parts = []
        if upward:
            trend_parts.append(f"{len(upward)} upward trend(s) detected in {', '.join(t['metric'] for t in upward[:2])}")
        if downward:
            trend_parts.append(f"{len(downward)} downward trend(s) in {', '.join(t['metric'] for t in downward[:2])}")
        if trend_parts:
            points.append(f"**Trends**: {'; '.join(trend_parts)}.")
    else:
        points.append("No time-series data available for trend analysis (no date columns detected).")

    # 5. Outlier/Anomaly risk
    high_out = len([o for o in outliers if o["severity"] == "HIGH"])
    high_anom = len([a for a in anomalies if a["severity"] == "HIGH"])
    total_risk = high_out + high_anom
    if total_risk > 0:
        points.append(f"⚠️ **Risks**: {total_risk} high-severity issues detected ({high_out} outlier patterns + {high_anom} anomalies) requiring investigation.")
    elif outliers:
        points.append(f"**Risks**: {len(outliers)} outlier patterns detected (low-to-medium severity).")

    # 6. Category concentration
    high_conc = [ca for ca in cat_analysis if ca.get("concentration") == "High"]
    if high_conc:
        points.append(f"**Concentration Risk**: {len(high_conc)} categorical columns show high concentration — top categories dominate in '{high_conc[0]['column']}' ({high_conc[0]['top_3_concentration_pct']}% in top 3).")

    # 7. Key insight highlights
    high_pri_insights = [bi for bi in business_insights if bi["priority"] == "HIGH"]
    if high_pri_insights:
        insight_summaries = []
        for bi in high_pri_insights[:2]:
            if bi["type"] == "growth_opportunity":
                insight_summaries.append(f"Growth opportunity identified")
            elif bi["type"] == "declining_trend":
                insight_summaries.append(f"Declining trend requires action")
            elif bi["type"] == "performance_gap":
                insight_summaries.append("Performance gap between segments")
            elif bi["type"] == "concentration_risk":
                insight_summaries.append("Revenue concentration risk")
            else:
                insight_summaries.append(bi["title"])
        if insight_summaries:
            points.append(f"**Key Insights**: {len(high_pri_insights)} high-priority findings: {'; '.join(insight_summaries)}.")

    # 8. Count of recommendations
    points.append(
        f"**Recommendations available**: tailored suggestions for improving data quality, performance, and strategic decision-making."
    )

    return points


def generate_insights() -> dict:
    """Generate comprehensive enterprise-grade insights for any dataset.
    Returns JSON with 12 sections of analysis matching the professional format.
    """

    # Cache (per-process) heavy results keyed by active dataset identity if available.
    try:
        from backend.utils.active_dataset_store import get_active_schema
        ds_key = None
        try:
            ds_key = str(get_active_schema())
        except Exception:
            ds_key = None
        if ds_key:
            cache = getattr(generate_insights, "_cache", {})
            if ds_key in cache:
                return _to_jsonable(cache[ds_key])
    except Exception:
        ds_key = None

    try:
        if not active_dataset_exists():
            return {"success": False, "error": "No active dataset."}
    except Exception:
        return {"success": False, "error": "No request context for active dataset."}

    conn = get_active_connection()
    try:
        df_full = pd.read_sql("SELECT * FROM dataset", conn)
    finally:
        conn.close()

    df = _maybe_sample(df_full)

    if df.empty:
        return {"success": False, "error": "Dataset is empty."}

    col_info = _classify_columns(df)
    numeric_cols = col_info["numeric_cols"]
    date_cols = col_info["date_cols"]
    cat_cols = col_info["categorical_cols"]
    primary_metric = _pick_primary_metric(df, numeric_cols)
    dataset_type = "Generic Tabular Dataset"

    # Detect dataset type
    all_cols_lower = " ".join(c.lower() for c in df.columns)
    sales_hints = ["revenue", "sales", "order", "product", "price", "quantity", "customer", "invoice", "transaction", "purchase"]
    finance_hints = ["salary", "budget", "expense", "income", "profit", "loss", "balance", "account", "payment", "tax", "interest"]
    edu_hints = ["student", "grade", "exam", "test", "score", "class", "teacher", "course", "subject", "attendance", "gpa", "semester", "marks"]
    hr_hints = ["employee", "department", "role", "hire", "salary", "job", "position", "manager", "attrition", "tenure", "leave"]
    mktg_hints = ["campaign", "click", "conversion", "impression", "channel", "ad", "social", "email", "lead", "traffic", "engagement"]
    health_hints = ["patient", "diagnosis", "treatment", "symptom", "blood", "bmi", "age", "gender", "hospital", "doctor"]

    if any(h in all_cols_lower for h in sales_hints):
        dataset_type = "Sales / E-commerce"
    elif any(h in all_cols_lower for h in finance_hints):
        dataset_type = "Finance"
    elif any(h in all_cols_lower for h in health_hints):
        dataset_type = "Healthcare"
    elif any(h in all_cols_lower for h in edu_hints):
        dataset_type = "Education"
    elif any(h in all_cols_lower for h in hr_hints):
        dataset_type = "HR / Workforce"
    elif any(h in all_cols_lower for h in mktg_hints):
        dataset_type = "Marketing"

    total_rows = len(df)
    total_cols = len(df.columns)
    memory_usage_bytes = df.memory_usage(deep=True).sum()
    memory_usage_mb = round(memory_usage_bytes / (1024 * 1024), 2)

    # ── Compute all analysis sections ──
    data_quality = _compute_data_quality(df)
    statistical_analysis = _compute_statistical_analysis(df, numeric_cols)
    outliers = _detect_outliers(df, numeric_cols)
    correlation_analysis = _compute_correlation_analysis(df, numeric_cols)
    trends = _compute_trends(df, date_cols, numeric_cols)
    cat_analysis = _compute_category_analysis(df, cat_cols, numeric_cols, primary_metric)
    performance_analysis = _compute_performance_analysis(df, numeric_cols, cat_cols, primary_metric)
    anomalies = _compute_anomaly_detection(df, numeric_cols, date_cols, outliers)
    business_insights = _compute_business_insights(df, col_info, primary_metric, trends, cat_analysis, outliers, correlation_analysis, anomalies)
    recommendations = _compute_recommendations(df, col_info, primary_metric, trends, cat_analysis, outliers, business_insights, anomalies, data_quality)
    exec_summary = _compute_executive_summary(df, col_info, primary_metric, trends, outliers, anomalies, business_insights, data_quality, cat_analysis, dataset_type)

    # ── 1. DATASET OVERVIEW ──
    dataset_overview = {
        "total_rows": total_rows,
        "total_columns": total_cols,
        "column_names": list(df.columns),
        "data_types": {col: str(df[col].dtype) for col in df.columns},
        "numeric_columns": len(numeric_cols),
        "numeric_column_names": numeric_cols,
        "categorical_columns": len(cat_cols),
        "categorical_column_names": cat_cols,
        "date_columns": len(date_cols),
        "date_column_names": date_cols,
        "total_missing_values": int(df.isna().sum().sum()),
        "total_duplicate_records": int(df.duplicated().sum()),
        "memory_usage_mb": memory_usage_mb,
        "dataset_type": dataset_type,
        "description": f"This dataset contains **{total_rows:,} records** across **{total_cols} columns**. "
                       f"Classified as a **{dataset_type}** dataset with "
                       f"{len(numeric_cols)} numeric, {len(cat_cols)} categorical, and {len(date_cols)} date columns.",
    }

    # ── 2. DATA QUALITY ASSESSMENT ──
    data_quality_assessment = {
        "total_rows": total_rows,
        "total_columns": total_cols,
        "missing_values_count": int(df.isna().sum().sum()),
        "missing_values_pct": round(int(df.isna().sum().sum()) / (total_rows * total_cols) * 100, 2) if total_rows * total_cols > 0 else 0,
        "missing_values_by_column": data_quality["missing_values"]["column_details"],
        "duplicate_records_count": data_quality["duplicates"]["total_duplicate_rows"],
        "duplicate_records_pct": data_quality["duplicates"]["duplicate_pct"],
        "empty_columns": data_quality["empty_columns"],
        "constant_columns": data_quality["constant_columns"],
        "consistency_issues": data_quality.get("consistency_issues", []),
        "data_quality_score": "EXCELLENT" if (data_quality["missing_values"]["total_missing_cells"] == 0 and data_quality["duplicates"]["total_duplicate_rows"] == 0)
                              else "GOOD" if (data_quality["missing_values"]["missing_pct"] < 5 and data_quality["duplicates"]["duplicate_pct"] < 3)
                              else "FAIR" if (data_quality["missing_values"]["missing_pct"] < 15 and data_quality["duplicates"]["duplicate_pct"] < 10)
                              else "POOR",
    }

    # ── 3. STATISTICAL SUMMARY ──
    notable_stats = []
    for stat in statistical_analysis:
        if stat.get("variability") == "High":
            notable_stats.append(f"'{stat['column']}' shows high variability (CV > 0.5) — values are widely dispersed.")
        if "skew" in stat.get("skewness", "").lower():
            notable_stats.append(f"'{stat['column']}' is {stat['skewness']} — the mean does not reflect the center.")

    # ── 4. OUTLIER ANALYSIS ──
    outlier_analysis = []
    for o in outliers:
        impact = ""
        if o["severity"] == "HIGH":
            impact = f"High-severity outliers may significantly impact averages and statistical models using '{o['column']}'."
        elif o["severity"] == "MEDIUM":
            impact = f"Moderate outliers in '{o['column']}' could affect analysis. Consider winsorization or transformation."
        else:
            impact = f"Low-severity outliers in '{o['column']}' — generally acceptable for most analyses."

        outlier_analysis.append({
            "column": o["column"],
            "total_outliers": o["total_outliers"],
            "outlier_pct": o["outlier_pct"],
            "low_outliers": o["low_outliers"],
            "high_outliers": o["high_outliers"],
            "severity": o["severity"],
            "low_threshold": o["low_threshold"],
            "high_threshold": o["high_threshold"],
            "iqr": o["iqr"],
            "business_impact": impact,
        })

    # ── 5. CORRELATION INSIGHTS ──
    correlation_insights = {
        "matrix_available": len(correlation_analysis.get("matrix", [])) > 0,
        "strong_positive_correlations": [],
        "strong_negative_correlations": [],
    }
    for sp in correlation_analysis.get("strong_positive", []):
        correlation_insights["strong_positive_correlations"].append({
            "variable_1": sp["var1"],
            "variable_2": sp["var2"],
            "correlation_coefficient": sp["r"],
            "interpretation": f"'{sp['var1']}' and '{sp['var2']}' increase together (r={sp['r']:.2f}). Changes in one are associated with similar changes in the other.",
        })
    for sn in correlation_analysis.get("strong_negative", []):
        correlation_insights["strong_negative_correlations"].append({
            "variable_1": sn["var1"],
            "variable_2": sn["var2"],
            "correlation_coefficient": sn["r"],
            "interpretation": f"'{sn['var1']}' and '{sn['var2']}' move in opposite directions (r={sn['r']:.2f}). As one increases, the other tends to decrease.",
        })

    # ── 6. TREND ANALYSIS ──
    trend_analysis = []
    for t in trends:
        trend_analysis.append({
            "date_column": t["date_column"],
            "metric": t["metric"],
            "direction": t["direction"],
            "strength": t["strength"],
            "slope": t["slope"],
            "periods_analyzed": t["periods"],
            "mom_changes": t.get("mom_analysis", []),
            "seasonal_pattern": t.get("seasonal_pattern"),
            "monthly_data": t["monthly_data"],
        })

    # Growth/decline summary
    growth_patterns = [t for t in trend_analysis if t["direction"] == "upward"]
    decline_patterns = [t for t in trend_analysis if t["direction"] == "downward"]

    # ── 7. CATEGORY ANALYSIS ──
    category_analysis = []
    for ca in cat_analysis:
        entry = {
            "column": ca["column"],
            "unique_values": ca["unique_values"],
            "top_categories": ca["top_categories"],
            "bottom_categories": ca["bottom_categories"],
            "top_3_concentration_pct": ca["top_3_concentration_pct"],
            "concentration_level": ca["concentration"],
        }
        if "best_performer" in ca:
            entry["best_performer"] = ca["best_performer"]
        if "worst_performer" in ca:
            entry["worst_performer"] = ca["worst_performer"]
        category_analysis.append(entry)

    # ── 8. PERFORMANCE ANALYSIS ──
    perf_analysis = performance_analysis

    # ── 9. ANOMALY DETECTION ──
    anomaly_detection = anomalies

    # ── 10. KEY BUSINESS INSIGHTS ──
    key_business_insights = business_insights

    # ── 11. RECOMMENDATIONS ──
    recommendations_data = recommendations

    # ── 12. EXECUTIVE SUMMARY ──
    executive_summary = exec_summary

    # ── Build Final Payload ──
    payload = {
        "success": True,
        "dataset_overview": dataset_overview,
        "data_quality_assessment": data_quality_assessment,
        "statistical_summary": {
            "columns_analyzed": len(statistical_analysis),
            "details": statistical_analysis,
            "notable_observations": notable_stats,
        },
        "outlier_analysis": {
            "total_columns_with_outliers": len(outlier_analysis),
            "details": outlier_analysis,
        },
        "correlation_insights": correlation_insights,
        "trend_analysis": {
            "total_trends_detected": len(trend_analysis),
            "growth_patterns": len(growth_patterns),
            "decline_patterns": len(decline_patterns),
            "details": trend_analysis,
        },
        "category_analysis": category_analysis,
        "performance_analysis": perf_analysis,
        "anomaly_detection": anomaly_detection,
        "business_insights": key_business_insights,
        "recommendations": recommendations_data,
        "executive_summary": executive_summary,
        "primary_metric": primary_metric,
        "dataset_type": dataset_type,
        "column_info": {
            "numeric": numeric_cols,
            "categorical": cat_cols,
            "date": date_cols,
        },
    }

    # Store cache if we had a key
    try:
        if ds_key:
            cache = getattr(generate_insights, "_cache", {})
            cache[ds_key] = payload
            generate_insights._cache = cache
    except Exception:
        pass

    return _to_jsonable(payload)
