from __future__ import annotations

import math
import pandas as pd

from backend.utils.active_dataset_store import get_active_connection, active_dataset_exists


def _safe_to_numeric(s: pd.Series) -> pd.Series:
    return pd.to_numeric(s, errors="coerce")


def _classify_columns(df: pd.DataFrame) -> dict:
    numeric_cols = df.select_dtypes(include="number").columns.tolist()

    # Also try to detect numeric-looking object columns
    for c in df.columns:
        if c in numeric_cols:
            continue
        if df[c].dtype == "object":
            num = pd.to_numeric(df[c], errors="coerce")
            if num.notna().sum() >= max(10, int(0.3 * len(df))):
                numeric_cols.append(c)

    numeric_cols = list(dict.fromkeys(numeric_cols))

    # date detection: try parse for object columns (limit cost)
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

    # Heuristic: prefer columns with a name hint
    preferred = [
        "score", "mark", "grade", "gpa", "points", "total", "average",
        "attendance", "performance", "salary", "revenue", "sales", "profit",
        "revenue", "cost", "profit", "rate", "value", "amount",
    ]

    for c in numeric_cols:
        lc = c.lower()
        if any(p in lc for p in preferred):
            return c

    # Else choose the numeric column with highest variance
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


def _chart_bar(labels, values, title, xLabel, yLabel):
    return {
        "plotType": "bar",
        "title": title,
        "xLabel": xLabel,
        "yLabel": yLabel,
        "labels": labels,
        "series": [{"label": yLabel, "data": values, "labels": labels}],
    }


def _chart_scatter(points, title, xLabel, yLabel):
    return {
        "plotType": "scatter",
        "title": title,
        "xLabel": xLabel,
        "yLabel": yLabel,
        "points": points,
    }


def _chart_histogram(values, col, bins=12):
    values = [v for v in values if v is not None and not (isinstance(v, float) and (math.isnan(v) or math.isinf(v)))]
    if not values:
        labels = ["—"]
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
                f"{mn + i*bin_size:.1f}–{mn + (i+1)*bin_size:.1f}" for i in range(b)
            ]
    return {
        "plotType": "bar",
        "title": f"Distribution of {col}",
        "xLabel": col,
        "yLabel": "Count",
        "labels": labels,
        "series": [{"label": "Frequency", "data": counts, "labels": labels}],
    }


def _insight_base(i: int, *, category: str, title: str, impact: str, confidence: str, chart_type: str, chart_data: dict):
    return {
        "id": f"ins-{i}",
        "category": category,
        "title": title,
        "summary": "",
        "explanation": "",
        "impact": impact,
        "confidence": confidence,
        "chart_type": chart_type,
        "chart_data": chart_data,
        "evidence": {},
        "recommendation": "",
    }


def _to_jsonable(v):
    import numpy as np
    import pandas as pd

    if v is None:
        return None
    # numpy scalars
    if isinstance(v, (np.integer,)):
        return int(v)
    if isinstance(v, (np.floating,)):
        fv = float(v)
        if math.isnan(fv) or math.isinf(fv):
            return None
        return fv
    if isinstance(v, (np.bool_,)):
        return bool(v)

    # pandas scalars
    if isinstance(v, (pd.Timestamp,)):
        return str(v)

    if isinstance(v, dict):
        return {str(k): _to_jsonable(val) for k, val in v.items()}
    if isinstance(v, (list, tuple)):
        return [_to_jsonable(x) for x in v]

    # basic scalars
    if isinstance(v, (str, int, float, bool)):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v

    return str(v)


def generate_insights() -> dict:

    """Compute a set of insight objects with evidence + chart data.

    Returns JSON ONLY.
    """
    # active_dataset_store relies on Flask request/session context.
    # If called without a request (tests/CLI), return a safe JSON shape.
    try:
        if not active_dataset_exists():
            return {"success": False, "insights": [], "error": "No active dataset."}
    except Exception:
        return {"success": False, "insights": [], "error": "No request context for active dataset."}


    conn = get_active_connection()
    try:
        df = pd.read_sql("SELECT * FROM dataset", conn)
    finally:
        conn.close()

    if df.empty:
        return {"dataset_summary": {"rows": 0, "columns": 0}, "insights": [], "executive_summary": {}, "recommendations": []}

    col_info = _classify_columns(df)
    numeric_cols = col_info["numeric_cols"]
    date_cols = col_info["date_cols"]
    cat_cols = col_info["categorical_cols"]

    primary_metric = _pick_primary_metric(df, numeric_cols)

    insights: list[dict] = []
    idx = 1

    # 1) Data quality insights: missingness for primary metric + overall
    total_rows = len(df)
    missing_rate = {}
    for c in df.columns:
        na = int(df[c].isna().sum())
        missing_rate[c] = na / total_rows if total_rows else 0

    worst_missing = sorted(missing_rate.items(), key=lambda x: x[1], reverse=True)[:1]
    if worst_missing and worst_missing[0][1] > 0:
        c, r = worst_missing[0]
        evidence = {"column": c, "missing_count": int(df[c].isna().sum()), "missing_rate": round(r, 4)}
        chart = _chart_bar([c], [int(df[c].isna().sum())], "Missing values", "Column", "Missing Count")
        ins = _insight_base(
            idx,
            category="data_quality",
            title=f"Missing values detected in '{c}'",
            impact="MEDIUM",
            confidence="HIGH",
            chart_type="bar",
            chart_data=chart,
        )
        ins["summary"] = f"Column '{c}' has significant missingness ({evidence['missing_rate']*100:.2f}%)."
        ins["explanation"] = "Missing values can distort averages, correlations, and risk thresholds."
        ins["evidence"] = evidence
        ins["recommendation"] = f"Handle missing values in '{c}' (impute or filter) before modeling."
        insights.append(ins)
        idx += 1

    # 2) Distribution insight for primary metric
    if primary_metric:
        x = _safe_to_numeric(df[primary_metric]).dropna().tolist()
        chart = _chart_histogram(x, primary_metric, bins=12)
        ins = _insight_base(
            idx,
            category="distribution",
            title=f"Distribution of {primary_metric}",
            impact="MEDIUM",
            confidence="HIGH",
            chart_type="histogram",
            chart_data=chart,
        )
        series = pd.Series(x)
        evidence = {
            "metric": primary_metric,
            "count": int(series.shape[0]),
            "mean": round(float(series.mean()), 4) if series.shape[0] else None,
            "median": round(float(series.median()), 4) if series.shape[0] else None,
            "min": round(float(series.min()), 4) if series.shape[0] else None,
            "max": round(float(series.max()), 4) if series.shape[0] else None,
            "std": round(float(series.std()), 4) if series.shape[0] else None,
        }
        ins["summary"] = f"{primary_metric} spans [{evidence['min']}, {evidence['max']}] with mean {evidence['mean']}."
        ins["explanation"] = "Understanding distribution helps validate thresholds and identifies skew/outliers."
        ins["evidence"] = evidence
        ins["recommendation"] = "Validate any risk threshold against the observed distribution; avoid assuming normality."
        insights.append(ins)
        idx += 1

    # 3) Correlation insights: strongest correlations with primary metric
    if primary_metric and len(numeric_cols) >= 2:
        y = _safe_to_numeric(df[primary_metric])
        corrs = []
        for c in numeric_cols:
            if c == primary_metric:
                continue
            x = _safe_to_numeric(df[c])
            tmp = pd.concat([x, y], axis=1).dropna()
            if tmp.shape[0] < 5:
                continue
            corr = float(tmp.iloc[:, 0].corr(tmp.iloc[:, 1]))
            corrs.append((c, corr, int(tmp.shape[0])))

        corrs_sorted = sorted(corrs, key=lambda t: abs(t[1]), reverse=True)[:5]
        if corrs_sorted:
            labels = [c for c, _, _ in corrs_sorted]
            values = [round(v, 4) for _, v, _ in corrs_sorted]
            chart = _chart_bar(labels, values, "Top correlations", "Variable", "Pearson r")
            best = corrs_sorted[0]
            ins = _insight_base(
                idx,
                category="correlation",
                title=f"Strongest correlation with {primary_metric}",
                impact="HIGH" if abs(best[1]) >= 0.5 else "MEDIUM",
                confidence="MEDIUM",
                chart_type="bar",
                chart_data=chart,
            )
            ins["summary"] = f"{best[0]} shows the strongest Pearson correlation with {primary_metric} (r={best[1]:.2f})."
            ins["explanation"] = "Correlations suggest relationships, but do not imply causality."
            ins["evidence"] = {
                "primary_metric": primary_metric,
                "top_correlations": [
                    {"variable": c, "pearson_r": round(r, 4), "n": n}
                    for c, r, n in corrs_sorted
                ],
            }
            ins["recommendation"] = "Prioritize correlated variables for deeper segmentation and feature engineering."
            insights.append(ins)
            idx += 1

    # 4) Performance/Top segment insight: if there is a categorical column, rank segments by mean primary metric
    if primary_metric and cat_cols:
        # heuristic: prefer department/gender-like columns
        def score_name(c: str):
            lc = c.lower()
            if "gender" in lc or "sex" in lc:
                return 3
            if "department" in lc or "dept" in lc or "cse" in lc or "mech" in lc or "ece" in lc or "civil" in lc:
                return 2
            return 1

        cat_sorted = sorted(cat_cols, key=score_name, reverse=True)[:3]
        for c in cat_sorted[:1]:
            grp = df[[c, primary_metric]].copy()
            grp[primary_metric] = _safe_to_numeric(grp[primary_metric])
            grp = grp.dropna(subset=[primary_metric])
            if grp.shape[0] == 0:
                continue
            gstats = grp.groupby(c)[primary_metric].agg(['mean', 'count']).reset_index()
            gstats = gstats.sort_values('mean', ascending=False)
            top = gstats.head(5)
            if top.shape[0] >= 2:
                labels = top[c].astype(str).tolist()
                values = [round(v, 4) for v in top['mean'].tolist()]
                chart = _chart_bar(labels, values, f"Top {c} by mean {primary_metric}", c, "Mean")
                ins = _insight_base(
                    idx,
                    category="segment",
                    title=f"Top {c} segments for {primary_metric}",
                    impact="HIGH",
                    confidence="MEDIUM",
                    chart_type="bar",
                    chart_data=chart,
                )
                ins["summary"] = f"Best-performing {c} segment is '{labels[0]}' with mean {primary_metric}={values[0]}."
                ins["explanation"] = "Segment averages highlight where outcomes are strongest for targeted best-practice replication."
                ins["evidence"] = {
                    "primary_metric": primary_metric,
                    "segment_column": c,
                    "top_segments": [
                        {"segment": str(r[c]), "mean": round(float(r['mean']), 4), "n": int(r['count'])}
                        for _, r in top.iterrows()
                    ],
                }
                ins["recommendation"] = "Investigate operational drivers behind the top segment and replicate them in lower segments."
                insights.append(ins)
                idx += 1

    # 5) Outlier/risk insight: IQR outliers in primary metric
    if primary_metric:
        x = _safe_to_numeric(df[primary_metric])
        x_clean = x.dropna()
        if x_clean.shape[0] >= 10:
            q1 = float(x_clean.quantile(0.25))
            q3 = float(x_clean.quantile(0.75))
            iqr = q3 - q1
            low = q1 - 1.5 * iqr
            high = q3 + 1.5 * iqr
            out_low = int((x_clean < low).sum())
            out_high = int((x_clean > high).sum())

            # chart: histogram again but evidence-focused
            chart = _chart_histogram(x_clean.tolist(), primary_metric, bins=12)
            ins = _insight_base(
                idx,
                category="outlier",
                title=f"Outliers detected in {primary_metric} (IQR rule)",
                impact="HIGH" if out_low + out_high > 0 else "LOW",
                confidence="HIGH",
                chart_type="histogram",
                chart_data=chart,
            )
            ins["summary"] = f"IQR method flags {out_low} low outliers and {out_high} high outliers in {primary_metric}."
            ins["explanation"] = "IQR outliers identify unusually low/high values relative to the interquartile range."
            ins["evidence"] = {
                "metric": primary_metric,
                "n": int(x_clean.shape[0]),
                "q1": round(q1, 4),
                "q3": round(q3, 4),
                "iqr": round(iqr, 4),
                "low_threshold": round(low, 4),
                "high_threshold": round(high, 4),
                "low_outliers": out_low,
                "high_outliers": out_high,
            }
            ins["recommendation"] = "Review outlier rows for data issues or exceptional cases; apply targeted interventions to low outliers."
            insights.append(ins)
            idx += 1

    # 6) Trend/anomaly: if date columns exist, bucket and look for trend via slope
    if date_cols and primary_metric:
        dc = date_cols[0]
        tmp = df[[dc, primary_metric]].copy()
        tmp[dc] = pd.to_datetime(tmp[dc], errors="coerce")
        tmp[primary_metric] = _safe_to_numeric(tmp[primary_metric])
        tmp = tmp.dropna(subset=[dc, primary_metric])
        if tmp.shape[0] >= 20:
            tmp["__bucket"] = tmp[dc].dt.to_period("M").astype(str)
            trend = tmp.groupby("__bucket")[primary_metric].mean().reset_index()
            if trend.shape[0] >= 4:
                # compute simple linear trend on index vs mean
                y = trend[primary_metric].astype(float).values
                x = list(range(len(y)))
                # slope using least squares
                x_mean = sum(x)/len(x)
                y_mean = sum(y)/len(y)
                denom = sum((xi-x_mean)**2 for xi in x) or 1
                slope = sum((x[i]-x_mean)*(y[i]-y_mean) for i in range(len(x))) / denom

                chart_labels = trend["__bucket"].tolist()
                chart_vals = [round(v, 4) for v in trend[primary_metric].tolist()]
                chart = {
                    "plotType": "line",
                    "title": f"Trend of {primary_metric} over time",
                    "xLabel": dc,
                    "yLabel": "Mean",
                    "labels": chart_labels,
                    "series": [{"label": primary_metric, "data": chart_vals, "labels": chart_labels}],
                }

                ins = _insight_base(
                    idx,
                    category="trend",
                    title=f"Trend detected in {primary_metric} over {dc}",
                    impact="HIGH" if abs(slope) > 0.01 else "MEDIUM",
                    confidence="MEDIUM",
                    chart_type="line",
                    chart_data=chart,
                )
                ins["summary"] = f"Average {primary_metric} changes over time with estimated slope={slope:.4f} per bucket index."
                ins["explanation"] = "We bucketed the timeline (monthly) and computed a simple linear trend over the bucket means."
                ins["evidence"] = {
                    "date_column": dc,
                    "bucket_count": int(trend.shape[0]),
                    "buckets": [
                        {"bucket": str(b), "mean": round(float(m), 4)}
                        for b, m in zip(trend["__bucket"].tolist(), trend[primary_metric].tolist())
                    ],
                    "trend_slope": round(float(slope), 6),
                }
                ins["recommendation"] = "Validate the trend with domain context (policy changes, curriculum changes, seasonality) and replicate drivers of improvements."
                insights.append(ins)
                idx += 1

    # Ensure at least some insights
    if not insights:
        # generic fallback: basic stats bar for numeric cols
        topn = []
        for c in numeric_cols[:5]:
            s = _safe_to_numeric(df[c])
            s = s.dropna()
            if s.empty:
                continue
            topn.append((c, float(s.mean()), int(s.shape[0])))
        labels = [c for c, _, _ in topn]
        values = [round(v, 4) for _, v, _ in topn]
        chart = _chart_bar(labels, values, "Numeric column means", "Column", "Mean")
        ins = _insight_base(
            idx,
            category="performance",
            title="Key numeric metrics overview",
            impact="LOW",
            confidence="LOW",
            chart_type="bar",
            chart_data=chart,
        )
        ins["summary"] = "Generated from numeric column means (dataset-wide overview)."
        ins["explanation"] = "Provides a quick snapshot of central tendencies for numeric fields."
        ins["evidence"] = {
            "means": [
                {"column": c, "mean": round(m, 4), "n": n}
                for c, m, n in topn
            ]
        }
        ins["recommendation"] = "Ask a follow-up to drill into a specific metric and segmentation."
        insights.append(ins)

    # Executive summary + recommendations placeholders
    # (insights already contain enough evidence; keep these computed/derivable)
    high = [i for i in insights if str(i.get("impact", "LOW")).upper() == "HIGH"]
    exec_summary = {
        "dataset_overview": {"rows": int(len(df)), "columns": int(df.shape[1])},
        "top_findings": [i["title"] for i in insights[:3]],
        "key_risks": [i["title"] for i in insights if i.get("category") in ("outlier", "data_quality", "risk")][:2],
        "opportunities": [i["title"] for i in insights if i.get("category") in ("segment", "opportunity")][:2],
        "recommendations": [i["recommendation"] for i in insights[:3]],
    }
    recommendations = [
        {"recommendation": i["recommendation"], "impact": i["impact"], "confidence": i["confidence"], "insight_id": i["id"]}
        for i in insights[:5]
    ]

    # Final JSON-safety pass
    payload = {
        "dataset_summary": {
            "rows": int(len(df)),
            "columns": int(df.shape[1]),
            "numeric_cols": numeric_cols,
            "categorical_cols": cat_cols,
            "date_cols": date_cols,
            "primary_metric": primary_metric,
        },
        "insights": insights,
        "executive_summary": exec_summary,
        "recommendations": recommendations,
    }

    return _to_jsonable(payload)


