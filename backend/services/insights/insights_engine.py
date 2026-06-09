"""
Enterprise AI Insights Engine — generates comprehensive 12-section analysis
for any tabular dataset uploaded to the platform.
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
        # Deterministic-ish sampling by index hash (stable across runs for same load)
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


def _detect_dataset_type(df: pd.DataFrame, col_info: dict) -> str:
    all_cols_lower = " ".join(c.lower() for c in df.columns)

    sales_hints = ["revenue", "sales", "order", "product", "price", "quantity", "customer", "invoice", "transaction", "purchase"]
    if any(h in all_cols_lower for h in sales_hints):
        return "Sales / E-commerce"

    finance_hints = ["salary", "budget", "expense", "income", "profit", "loss", "balance", "account", "payment", "tax", "interest"]
    if any(h in all_cols_lower for h in finance_hints):
        return "Finance"

    health_hints = ["patient", "diagnosis", "treatment", "symptom", "disease", "blood", "heart", "bmi", "age", "gender", "hospital", "doctor"]
    if any(h in all_cols_lower for h in health_hints):
        return "Healthcare"

    edu_hints = ["student", "grade", "exam", "test", "score", "class", "teacher", "course", "subject", "attendance", "gpa", "semester", "marks"]
    if any(h in all_cols_lower for h in edu_hints):
        return "Education"

    hr_hints = ["employee", "department", "role", "hire", "salary", "job", "position", "manager", "attrition", "tenure", "leave"]
    if any(h in all_cols_lower for h in hr_hints):
        return "HR / Workforce"

    mktg_hints = ["campaign", "click", "conversion", "impression", "channel", "ad", "social", "email", "lead", "traffic", "engagement"]
    if any(h in all_cols_lower for h in mktg_hints):
        return "Marketing"

    inv_hints = ["stock", "inventory", "warehouse", "supplier", "supply", "sku", "bin", "shelf", "reorder"]
    if any(h in all_cols_lower for h in inv_hints):
        return "Inventory / Supply Chain"

    cust_hints = ["customer", "segment", "loyalty", "churn", "satisfaction", "nps", "feedback", "complaint"]
    if any(h in all_cols_lower for h in cust_hints):
        return "Customer Analytics"

    return "Generic Tabular Dataset"


def _chart_bar(labels, values, title, xLabel, yLabel):
    return {
        "plotType": "bar",
        "title": title,
        "xLabel": xLabel,
        "yLabel": yLabel,
        "labels": labels,
        "series": [{"label": yLabel, "data": values, "labels": labels}],
    }


def _chart_line(labels, values, title, xLabel, yLabel):
    return {
        "plotType": "line",
        "title": title,
        "xLabel": xLabel,
        "yLabel": yLabel,
        "labels": labels,
        "series": [{"label": yLabel, "data": values, "labels": labels}],
    }


def _chart_pie(labels, values, title):
    return {
        "plotType": "pie",
        "title": title,
        "labels": labels,
        "series": [{"label": "Distribution", "data": values, "labels": labels}],
    }


def _chart_histogram(values, col, bins=12):
    values = [v for v in values if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))]
    if not values:
        labels = ["\u2014"]
        counts = [0]
    else:
        mn = min(values)
        mx = max(values)
        if mn == mx:
            labels = [f"{mn:.2f}"]
            counts = [len(values)]
        else:
            b = min(bins, 20)
            bin_size = (mx - mn) / b
            counts = [0] * b
            for v in values:
                idx = int(min(b - 1, max(0, (v - mn) / bin_size)))
                counts[idx] += 1
            labels = [
                f"{mn + i*bin_size:.1f}\u2013{mn + (i+1)*bin_size:.1f}" for i in range(b)
            ]
    return {
        "plotType": "bar",
        "title": f"Distribution of {col}",
        "xLabel": col,
        "yLabel": "Count",
        "labels": labels,
        "series": [{"label": "Frequency", "data": counts, "labels": labels}],
    }


def _chart_heatmap(labels, data_matrix, title):
    return {
        "plotType": "heatmap",
        "title": title,
        "labels": labels,
        "matrix": data_matrix,
    }


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


def _compute_top_performers(df: pd.DataFrame, numeric_cols: list[str], cat_cols: list[str], primary_metric: str | None) -> list[dict]:
    if not primary_metric or not cat_cols:
        return []

    performers = []
    for cat_col in cat_cols[:5]:
        grp = df[[cat_col, primary_metric]].copy()
        grp[primary_metric] = _safe_to_numeric(grp[primary_metric])
        grp = grp.dropna(subset=[primary_metric])
        if grp.empty:
            continue

        gstats = grp.groupby(cat_col)[primary_metric].agg(["sum", "mean", "count"]).reset_index()
        # Flatten MultiIndex columns from agg()
        gstats.columns = [cat_col, "sum", "mean", "count"]
        gstats = gstats.sort_values("mean", ascending=False)
        total_sum = float(gstats["sum"].sum())

        top_n = gstats.head(10)
        items = []
        for _, r in top_n.iterrows():
            contribution = float(r["sum"]) / total_sum * 100 if total_sum > 0 else 0
            items.append({
                "name": str(r[cat_col]),
                "sum": round(float(r["sum"]), 2),
                "mean": round(float(r["mean"]), 4),
                "count": int(r["count"]),
                "contribution_pct": round(contribution, 2),
            })

        performers.append({
            "category_column": cat_col,
            "metric": primary_metric,
            "total": total_sum,
            "top_items": items,
        })

    return performers


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

            labels = monthly["__month"].tolist()
            values = [round(float(v), 4) for v in monthly["mean"].tolist()]

            trends.append({
                "date_column": dc,
                "metric": nc,
                "direction": direction,
                "strength": strength,
                "slope": round(float(slope), 6),
                "periods": len(labels),
                "monthly_data": [{"period": str(b), "mean": round(float(m), 4)} for b, m in zip(monthly["__month"].tolist(), monthly["mean"].tolist())],
                "chart": _chart_line(labels, values, f"Trend of {nc} over {dc}", dc, nc),
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

    return {
        "total_rows": total_rows,
        "total_columns": len(df.columns),
        "missing_values": {
            "total_missing_cells": int(df.isna().sum().sum()),
            "columns_with_missing": len(missing_cols),
            "column_details": missing_cols,
        },
        "duplicates": {
            "total_duplicate_rows": dupes_count,
            "duplicate_pct": dupe_pct,
            "severity": "HIGH" if dupe_pct > 10 else "MEDIUM" if dupe_pct > 3 else "LOW",
        },
        "constant_columns": constant_cols,
        "empty_columns": empty_cols,
    }


def _compute_business_insights(df: pd.DataFrame, col_info: dict, primary_metric: str | None, trends: list[dict]) -> list[dict]:
    insights = []
    numeric_cols = col_info["numeric_cols"]
    cat_cols = col_info["categorical_cols"]

    for t in trends:
        if t["direction"] == "upward":
            insights.append({
                "type": "growth_opportunity",
                "title": f"Positive trend in {t['metric']}",
                "description": f"Your {t['metric']} is showing a {t['strength']} {t['direction']} trend over {t['date_column']}. This indicates growth potential.",
                "action": f"Continue investing in drivers that support {t['metric']} growth.",
                "priority": "HIGH" if t["strength"] == "strong" else "MEDIUM",
            })
            break

    for t in trends:
        if t["direction"] == "downward":
            insights.append({
                "type": "cost_reduction",
                "title": f"Declining trend in {t['metric']}",
                "description": f"Your {t['metric']} is showing a {t['strength']} {t['direction']} trend. This may require attention.",
                "action": f"Investigate root causes for the decline in {t['metric']} and develop mitigation strategies.",
                "priority": "HIGH" if t["strength"] == "strong" else "MEDIUM",
            })
            break

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
                if gap > 0:
                    insights.append({
                        "type": "performance_improvement",
                        "title": f"Performance gap in {cat_col}",
                        "description": f"'{top[cat_col]}' outperforms '{bottom[cat_col]}' by {gap:.2f} in {primary_metric}. There is a {len(gstats)}-segment variance.",
                        "action": f"Analyze what makes '{top[cat_col]}' successful and apply those practices to other segments.",
                        "priority": "HIGH" if gap > float(top["__mean__"]) * 0.5 else "MEDIUM",
                    })

    if primary_metric:
        s = _safe_to_numeric(df[primary_metric]).dropna()
        if not s.empty:
            mean_val = float(s.mean())
            median_val = float(s.median())
            if abs(mean_val - median_val) / (mean_val + 0.001) > 0.3:
                insights.append({
                    "type": "resource_optimization",
                    "title": f"Skewed {primary_metric} distribution",
                    "description": f"The mean ({mean_val:.2f}) differs significantly from the median ({median_val:.2f}), indicating a skewed distribution.",
                    "action": "Consider using median instead of mean for performance benchmarks and resource allocation decisions.",
                    "priority": "MEDIUM",
                })

    if len(numeric_cols) >= 2:
        corr_result = _compute_correlation_analysis(df, numeric_cols)
        for sp in corr_result["strong_positive"][:2]:
            insights.append({
                "type": "customer_insight",
                "title": f"Strong relationship: {sp['var1']} and {sp['var2']}",
                "description": f"'{sp['var1']}' and '{sp['var2']}' have a strong positive correlation (r={sp['r']:.2f}).",
                "action": f"Leverage the relationship between {sp['var1']} and {sp['var2']} for cross-promotion or bundled strategies.",
                "priority": "HIGH" if sp["r"] > 0.7 else "MEDIUM",
            })

    return insights


def generate_insights() -> dict:
    """Generate comprehensive enterprise-grade insights for any dataset.
    Returns JSON with 12 sections of analysis.
    """

    # Cache (per-process) heavy results keyed by active dataset identity if available.
    # This avoids recomputation when user clicks AI Insights repeatedly.
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

    # Performance guard: heavy analyses use bounded sample for large datasets
    df = _maybe_sample(df_full)


    if df.empty:
        return {"success": False, "error": "Dataset is empty."}

    col_info = _classify_columns(df)
    numeric_cols = col_info["numeric_cols"]
    date_cols = col_info["date_cols"]
    cat_cols = col_info["categorical_cols"]
    primary_metric = _pick_primary_metric(df, numeric_cols)
    dataset_type = _detect_dataset_type(df, col_info)

    total_rows = len(df)
    total_cols = len(df.columns)
    memory_usage_bytes = df.memory_usage(deep=True).sum()
    memory_usage_mb = round(memory_usage_bytes / (1024 * 1024), 2)
    total_missing = int(df.isna().sum().sum())
    total_duplicates = int(df.duplicated().sum())

    # ── SECTION 1: DATASET OVERVIEW ──
    dataset_overview = {
        "total_rows": total_rows,
        "total_columns": total_cols,
        "dataset_type": dataset_type,
        "numeric_columns": len(numeric_cols),
        "categorical_columns": len(cat_cols),
        "date_columns": len(date_cols),
        "total_missing_values": total_missing,
        "total_duplicate_records": total_duplicates,
        "memory_usage_mb": memory_usage_mb,
        "column_names": list(df.columns),
        "numeric_column_names": numeric_cols,
        "categorical_column_names": cat_cols,
        "date_column_names": date_cols,
        "description": f"This dataset contains {total_rows:,} records across {total_cols} columns. "
                       f"It has been classified as a **{dataset_type}** dataset with "
                       f"{len(numeric_cols)} numeric, {len(cat_cols)} categorical, and {len(date_cols)} date columns.",
    }

    # ── SECTION 2: KEY FINDINGS ──
    key_findings = []

    for cat_col in cat_cols[:3]:
        if 2 <= df[cat_col].nunique() <= 20:
            top_val = df[cat_col].value_counts().index[0]
            top_pct = round(df[cat_col].value_counts(normalize=True).iloc[0] * 100, 2)
            if top_pct > 20:
                key_findings.append({
                    "title": f"Majority segment in '{cat_col}'",
                    "explanation": f"'{top_val}' is the most common value, representing {top_pct}% of all records.",
                    "confidence": "HIGH",
                    "type": "segment",
                })

    if primary_metric:
        s = _safe_to_numeric(df[primary_metric]).dropna()
        if not s.empty:
            mean_val = float(s.mean())
            median_val = float(s.median())
            key_findings.append({
                "title": f"Average {primary_metric} is {mean_val:.2f}",
                "explanation": f"The average {primary_metric} across the dataset is {mean_val:.2f}, with a median of {median_val:.2f}.",
                "confidence": "HIGH",
                "type": "metric",
            })

    if total_missing > 0:
        worst_col = df.isna().sum().idxmax()
        worst_count = int(df[worst_col].isna().sum())
        key_findings.append({
            "title": f"Data quality attention needed in '{worst_col}'",
            "explanation": f"Column '{worst_col}' has {worst_count} missing values, the highest among all columns.",
            "confidence": "HIGH",
            "type": "warning",
        })

    if total_duplicates > 0:
        dupe_pct = round(total_duplicates / total_rows * 100, 2)
        key_findings.append({
            "title": f"{total_duplicates:,} duplicate records found",
            "explanation": f"There are {total_duplicates:,} duplicate rows ({dupe_pct}% of data).",
            "confidence": "HIGH",
            "type": "warning",
        })

    if cat_cols:
        diverse_cols = [(c, df[c].nunique()) for c in cat_cols if df[c].nunique() >= 10]
        if diverse_cols:
            diverse_cols.sort(key=lambda x: x[1], reverse=True)
            col_name, unique_count = diverse_cols[0]
            key_findings.append({
                "title": f"High diversity in '{col_name}'",
                "explanation": f"Column '{col_name}' has {unique_count} unique values, making it a strong candidate for segmentation.",
                "confidence": "MEDIUM",
                "type": "discovery",
            })

    if len(key_findings) < 5 and numeric_cols:
        for nc in numeric_cols[:1]:
            s = _safe_to_numeric(df[nc]).dropna()
            if not s.empty:
                key_findings.append({
                    "title": f"Range of {nc}: {float(s.min()):.2f} to {float(s.max()):.2f}",
                    "explanation": f"The '{nc}' column spans from {float(s.min()):.2f} to {float(s.max()):.2f} with mean {float(s.mean()):.2f}.",
                    "confidence": "HIGH",
                    "type": "metric",
                })
    if len(key_findings) < 5 and date_cols:
        key_findings.append({
            "title": f"Time dimension available: '{date_cols[0]}'",
            "explanation": f"The dataset includes a date column '{date_cols[0]}', enabling time-series analysis.",
            "confidence": "HIGH",
            "type": "discovery",
        })

    # ── SECTION 3: STATISTICAL ANALYSIS ──
    statistical_analysis = _compute_statistical_analysis(df, numeric_cols)
    notable_stats = []
    for stat in statistical_analysis:
        if stat.get("variability") == "High":
            notable_stats.append(f"'{stat['column']}' shows high variability (CV > 0.5).")
        if "skew" in stat.get("skewness", "").lower():
            notable_stats.append(f"'{stat['column']}' is {stat['skewness']}.")

    # ── SECTION 4: TRENDS & PATTERNS ──
    trends = _compute_trends(df, date_cols, numeric_cols)

    # ── SECTION 5: TOP PERFORMERS ──
    top_performers = _compute_top_performers(df, numeric_cols, cat_cols, primary_metric)

    # ── SECTION 6: OUTLIERS & ANOMALIES ──
    outliers = _detect_outliers(df, numeric_cols)

    # ── SECTION 7: CORRELATION ANALYSIS ──
    correlation_analysis = _compute_correlation_analysis(df, numeric_cols)

    # ── SECTION 8: DATA QUALITY REPORT ──
    data_quality = _compute_data_quality(df)

    # ── SECTION 9: VISUAL INSIGHTS ──
    visual_insights = []

    for cat_col in cat_cols[:2]:
        if 2 <= df[cat_col].nunique() <= 20:
            value_counts = df[cat_col].value_counts().head(10)
            labels = value_counts.index.tolist()
            values = value_counts.values.tolist()
            visual_insights.append({
                "chart_type": "bar",
                "title": f"Top categories in '{cat_col}'",
                "x_label": cat_col,
                "y_label": "Count",
                "chart_data": _chart_bar(labels, values, f"Top categories in '{cat_col}'", cat_col, "Count"),
            })
            break

    if primary_metric:
        s = _safe_to_numeric(df[primary_metric]).dropna()
        if not s.empty:
            visual_insights.append({
                "chart_type": "histogram",
                "title": f"Distribution of {primary_metric}",
                "x_label": primary_metric,
                "y_label": "Frequency",
                "chart_data": _chart_histogram(s.tolist(), primary_metric, bins=15),
            })

    if cat_cols and 2 <= df[cat_cols[0]].nunique() <= 10:
        value_counts = df[cat_cols[0]].value_counts().head(8)
        visual_insights.append({
            "chart_type": "pie",
            "title": f"Distribution of '{cat_cols[0]}'",
            "x_label": cat_cols[0],
            "y_label": "Proportion",
            "chart_data": _chart_pie(value_counts.index.tolist(), value_counts.values.tolist(), f"Distribution of '{cat_cols[0]}'"),
        })

    if 2 <= len(numeric_cols) <= 10:
        corr_mat = correlation_analysis.get("matrix", [])
        visual_insights.append({
            "chart_type": "heatmap",
            "title": "Correlation Matrix",
            "x_label": "Variables",
            "y_label": "Variables",
            "chart_data": _chart_heatmap(correlation_analysis.get("labels", []), corr_mat, "Correlation Matrix"),
        })

    for t in trends[:1]:
        visual_insights.append({
            "chart_type": "line",
            "title": t["chart"]["title"],
            "x_label": t["date_column"],
            "y_label": t["metric"],
            "chart_data": t["chart"],
        })
        break

    if statistical_analysis:
        box_data = []
        for s in statistical_analysis[:5]:
            box_data.append({
                "column": s["column"],
                "min": s["min"],
                "q1": s["q1"],
                "median": s["median"],
                "q3": s["q3"],
                "max": s["max"],
            })
        visual_insights.append({
            "chart_type": "box",
            "title": "Statistical distribution overview",
            "chart_data": {"boxes": box_data},
        })

    # ── SECTION 10: BUSINESS INSIGHTS ──
    business_insights = _compute_business_insights(df, col_info, primary_metric, trends)

    # ── SECTION 11: PREDICTIVE OPPORTUNITIES ──
    predictive_opportunities = []

    if primary_metric and len(numeric_cols) >= 2:
        predictive_opportunities.append({
            "type": "regression",
            "title": "Value Prediction",
            "description": f"Predict '{primary_metric}' using other numeric features. Possible with Linear Regression, Random Forest, or XGBoost.",
            "required_features": [c for c in numeric_cols if c != primary_metric][:5],
            "target": primary_metric,
            "feasibility": "HIGH" if len(numeric_cols) >= 3 else "MEDIUM",
        })

    if date_cols and primary_metric:
        predictive_opportunities.append({
            "type": "forecasting",
            "title": "Time Series Forecast",
            "description": f"Forecast future '{primary_metric}' values using '{date_cols[0]}' with ARIMA, Prophet, or LSTM models.",
            "required_features": [date_cols[0]],
            "target": primary_metric,
            "feasibility": "HIGH" if len(df) >= 50 else "MEDIUM",
        })

    if cat_cols and primary_metric:
        predictive_opportunities.append({
            "type": "classification",
            "title": "Segment Classification",
            "description": f"Build a classifier to categorize records into {cat_cols[0]} segments based on other features.",
            "target": cat_cols[0],
            "feasibility": "HIGH" if df[cat_cols[0]].nunique() <= 10 else "MEDIUM",
        })

    if len(cat_cols) >= 2 and len(df) >= 50:
        predictive_opportunities.append({
            "type": "clustering",
            "title": "Customer/Entity Segmentation",
            "description": "Use K-Means or DBSCAN to automatically segment records into natural groups based on similar characteristics.",
            "required_features": numeric_cols[:5],
            "feasibility": "HIGH" if len(numeric_cols) >= 2 else "LOW",
        })

    if len(df[cat_cols].columns) > 0 and df[cat_cols].nunique().sum() > 50 and numeric_cols:
        predictive_opportunities.append({
            "type": "recommendation",
            "title": "Recommendation System",
            "description": "Collaborative or content-based filtering to recommend items based on user behavior patterns.",
            "feasibility": "MEDIUM",
        })

    # ── SECTION 12: EXECUTIVE SUMMARY ──
    exec_summary_points = [
        f"**Dataset Overview**: This {dataset_type} dataset contains {total_rows:,} records with {total_cols} columns "
        f"({len(numeric_cols)} numeric, {len(cat_cols)} categorical, {len(date_cols)} date-based).",
    ]

    if primary_metric:
        s = _safe_to_numeric(df[primary_metric]).dropna()
        mean_val = float(s.mean()) if not s.empty else 0
        exec_summary_points.append(
            f"**Key Metric**: The primary measure '{primary_metric}' averages {mean_val:.2f} across all records."
        )

    if key_findings and len(key_findings) > 1:
        exec_summary_points.append(
            f"**Major Findings**: {len(key_findings)} key patterns discovered. "
            f"{key_findings[0]['title']} is the most significant observation."
        )

    high_sev_outliers = [o for o in outliers if o["severity"] == "HIGH"]
    if high_sev_outliers:
        exec_summary_points.append(
            f"\u26a0\ufe0f **Risks Detected**: {len(high_sev_outliers)} high-severity outlier patterns found, "
            f"particularly in '{high_sev_outliers[0]['column']}' column."
        )
    elif outliers:
        exec_summary_points.append(
            f"**Risks**: {len(outliers)} outlier patterns detected across numeric columns."
        )

    if total_missing > 0:
        exec_summary_points.append(
            f"**Data Quality**: {total_missing:,} missing values across {data_quality['missing_values']['columns_with_missing']} columns "
            f"and {total_duplicates:,} duplicate records require attention."
        )
    else:
        exec_summary_points.append(
            "**Data Quality**: Excellent - no missing values or quality issues detected."
        )

    if trends:
        exec_summary_points.append(
            f"**Trends**: {len(trends)} meaningful temporal pattern(s) identified, "
            f"with the strongest being '{trends[0]['metric']}' showing a {trends[0]['direction']} trend."
        )

    high_fea = [p for p in predictive_opportunities if p["feasibility"] == "HIGH"]
    if high_fea:
        exec_summary_points.append(
            f"**Opportunities**: {len(high_fea)} high-feasibility ML opportunities identified, "
            f"including {high_fea[0]['title'].lower()}."
        )
    elif predictive_opportunities:
        exec_summary_points.append(
            f"**Opportunities**: {len(predictive_opportunities)} ML/AI opportunities identified."
        )

    high_pri = [i for i in business_insights if i["priority"] == "HIGH"]
    if business_insights:
        exec_summary_points.append(
            f"**Recommendations**: {len(business_insights)} actionable business insights generated."
            + (f" {len(high_pri)} high-priority actions recommended." if high_pri else "")
        )

    # ── Build Final Payload ──
    payload = {
        "success": True,
        "dataset_overview": dataset_overview,
        "key_findings": key_findings[:10],
        "statistical_analysis": statistical_analysis,
        "notable_statistics": notable_stats,
        "trends": trends,
        "top_performers": top_performers,
        "outliers_anomalies": outliers,
        "correlation_analysis": correlation_analysis,
        "data_quality_report": data_quality,
        "visual_insights": visual_insights,
        "business_insights": business_insights,
        "predictive_opportunities": predictive_opportunities,
        "executive_summary": exec_summary_points,
        "primary_metric": primary_metric,
        "dataset_type": dataset_type,
        "column_info": {
            "numeric": numeric_cols,
            "categorical": cat_cols,
            "date": date_cols,
        },
        "insights": [],
    }

    # Store cache if we had a key; cache hit should still preserve JSON-safe output.
    try:
        if ds_key:
            cache = getattr(generate_insights, "_cache", {})
            cache[ds_key] = payload
            generate_insights._cache = cache
    except Exception:
        pass

    return _to_jsonable(payload)
