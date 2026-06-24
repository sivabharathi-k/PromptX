"""
Analytical Engine — Upgrade version.
Calculates core statistics in Python (Trust Scores, Outliers, Trends, Forecast safety) 
and calls Groq (Llama 3) strictly as an explanation/translation layer.
"""

from __future__ import annotations
import json
import logging
import re
import math
import datetime
import numpy as np
import pandas as pd
from groq import Groq

from backend.config.settings import GROQ_API_KEY
GROQ_MODEL = "llama-3.3-70b-versatile"
from backend.utils.active_dataset_store import get_active_connection, active_dataset_exists, get_master_schema

logger = logging.getLogger("analytical_engine")
_client = Groq(api_key=GROQ_API_KEY)

SYSTEM_PROMPT = """You are an elite business intelligence AI embedded in an analytics platform.
Your job is to act strictly as an EXPLANATION and TRANSLATION layer. You will take raw statistics, 
outliers, trust flags, and trends computed in Python and explain them in clear, user-friendly 
business insights answering six critical questions:

| # | Question | Category | Your job |
|---|---|---|---|
| 1 | **What happened?** | WHAT_HAPPENED | Facts — major changes, trends, performance updates |
| 2 | **Why did it happen?** | WHY_IT_HAPPENED | Root causes — driver analysis, category breakdowns |
| 3 | **What should I do?** | WHAT_TO_DO | Actions — data-backed suggestions to optimize outcomes |
| 4 | **What will happen next?** | WHAT_NEXT | Trajectory — projections, risk flags, and opportunities |
| 5 | **What is unusual?** | WHAT_IS_UNUSUAL | Anomalies — outlier values, statistical spikes or drops |
| 6 | **Can I trust this?** | CAN_I_TRUST | Reliability — dataset completeness, formats, quality flags |

---

## OUTPUT FORMAT

Return ONLY this JSON object. No reasoning, no prose, no markdown, no explanation outside the JSON.
Start your response directly with `{` and end with `}`.

```json
{
  "dataset_summary": {
    "domain": "e.g. retail sales / HR / logistics",
    "row_count": 0,
    "col_count": 0,
    "date_range": "YYYY-MM-DD to YYYY-MM-DD",
    "grain": "e.g. daily sales by region",
    "metrics": ["revenue", "units_sold"],
    "dimensions": ["region", "product_category"],
    "trust_score": 92,
    "forecast_safety_status": "e.g. Safe / Insufficient Periods",
    "data_quality_flags": ["5% null values in column margin", "3 duplicate rows removed"]
  },
  "insights": [
    {
      "id": "INS-001",
      "question": "WHAT_HAPPENED | WHY_IT_HAPPENED | WHAT_TO_DO | WHAT_NEXT | WHAT_IS_UNUSUAL | CAN_I_TRUST",
      "type": "ANOMALY | CHANGE | TREND | PATTERN | ROOT_CAUSE | CORRELATION | RECOMMENDATION | FORECAST | RISK | OPPORTUNITY | TRUST_WARNING | TRUST_CONFIRM",
      "severity": "HIGH | MEDIUM | LOW",
      "title": "Max 10 words — specific and factual",
      "description": "2-3 sentences maximum. Specific numbers mandatory. Frame facts in past tense, predictions in future tense.",
      "metric": "the primary metric name or 'none'",
      "dimension": "the primary dimension name or 'none'",
      "magnitude": "e.g. +23.4% or -$14,200 or 'none'",
      "period": "e.g. 2026-Q3 vs 2026-Q2 or 'none'",
      "evidence": "Grounded statistical observation proving this insight.",
      "confidence": "HIGH | MEDIUM | LOW",
      "next_action": "Clear action verb or 'none'",
      "chart_type": "bar | line | pie | scatter | none",
      "filters": {},
      "timestamp": "ISO 8601 string"
    }
  ]
}
```

---

## RULES FOR INSIGHT CATEGORIES

1. **WHAT_IS_UNUSUAL**: Focus on explaining the outliers computed by Python's IQR test (outside the lower/upper thresholds). Give clear details of which point exceeded the boundary.
2. **CAN_I_TRUST**: Explain the trust score calculated by Python. If trust is high (>85%), confirm reliability. If trust is low, alert the user about null rates, duplicates, or type inconsistencies.
3. **WHAT_NEXT**: Enforce the Python forecast safety warning. If Python flags it as unsafe (insufficient date periods), generate a RISK insight explaining why forecasting is disabled.
4. **WHAT_TO_DO**: Recommendations must match the filters and findings of WHAT_HAPPENED/WHY_IT_HAPPENED.
5. **No Hallucinations**: Write explanations using ONLY the facts and variables provided. Do not invent any periods, segments, or magnitudes not present in the user content.
"""

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

def generate_analytical_insights() -> dict:
    """
    Computes trust scores, anomaly thresholds, and trends in Python,
    then uses Groq strictly to formulate natural language insights.
    """
    try:
        from backend.utils.active_dataset_store import get_active_schema
        ds_key = None
        try:
            ds_key = str(get_active_schema())
        except Exception:
            ds_key = None
        if ds_key:
            cache = getattr(generate_analytical_insights, "_cache", {})
            if ds_key in cache:
                return cache[ds_key]
    except Exception:
        ds_key = None

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
    col_count = len(df.columns)
    master_schema = get_master_schema() or {}

    numeric_cols = [c for c, t in master_schema.items() if t == "NUM"]
    categorical_cols = [c for c, t in master_schema.items() if t not in ("NUM", "DATE")]
    date_cols = [c for c, t in master_schema.items() if t == "DATE"]

    # 1. Deterministic Trust Scoring Engine
    null_count = int(df.isna().sum().sum())
    total_cells = total_rows * col_count
    null_ratio = null_count / total_cells if total_cells > 0 else 0.0
    null_penalty = min(20.0, null_ratio * 200.0)  # up to 20% penalty

    dupes = int(df.duplicated().sum())
    dupe_ratio = dupes / total_rows if total_rows > 0 else 0.0
    dupe_penalty = min(10.0, dupe_ratio * 200.0)  # up to 10% penalty

    size_penalty = 20.0 if total_rows < 30 else 0.0  # 20% penalty if small sample

    consistency_penalty = 0.0
    dq_flags = []
    
    # Check date column consistency
    if date_cols:
        date_col = date_cols[0]
        try:
            parsed_dates = pd.to_datetime(df[date_col], errors="coerce")
            null_parsed = int(parsed_dates.isna().sum())
            null_raw = int(df[date_col].isna().sum())
            if null_parsed > null_raw:
                consistency_penalty = 10.0
                dq_flags.append(f"Mixed date formatting detected in '{date_col}' column.")
        except Exception:
            consistency_penalty = 10.0
            dq_flags.append(f"Inconsistent datetime structure in '{date_col}'.")

    # Format specific null messages
    for col in df.columns:
        c_nulls = int(df[col].isna().sum())
        if c_nulls > 0:
            c_pct = (c_nulls / total_rows) * 100
            dq_flags.append(f"{c_pct:.1f}% null values in '{col}' column.")
            
    if dupes > 0:
        dq_flags.append(f"{dupes:,} duplicate rows detected.")

    trust_score = max(0, int(100 - (null_penalty + dupe_penalty + size_penalty + consistency_penalty)))

    # 2. Forecast Safety Rules
    forecast_available = True
    forecast_reason = "Dataset contains sufficient chronological data."
    if not date_cols:
        forecast_available = False
        forecast_reason = "No DATE/time column found in dataset."
    elif total_rows < 10:
        forecast_available = False
        forecast_reason = "Dataset size is too small (minimum 10 rows required)."
    else:
        date_col = date_cols[0]
        try:
            distinct_periods = df[date_col].dropna().nunique()
            if distinct_periods < 4:
                forecast_available = False
                forecast_reason = f"Only {distinct_periods} distinct period intervals found (minimum 4 periods required)."
        except Exception:
            forecast_available = False
            forecast_reason = "Error converting date intervals for forecasting."

    # 3. Precomputed Outliers & Anomaly Thresholds
    outliers_summary = {}
    for col in numeric_cols:
        series = df[col].dropna()
        if len(series) > 5:
            q1 = float(series.quantile(0.25))
            q3 = float(series.quantile(0.75))
            iqr = q3 - q1
            lower_bound = q1 - 1.5 * iqr
            upper_bound = q3 + 1.5 * iqr
            outlier_series = series[(series < lower_bound) | (series > upper_bound)]
            
            if len(outlier_series) > 0:
                outliers_summary[col] = {
                    "q1": q1,
                    "q3": q3,
                    "iqr": iqr,
                    "lower_threshold": lower_bound,
                    "upper_threshold": upper_bound,
                    "outliers_count": len(outlier_series),
                    "max_outlier": float(outlier_series.max()),
                    "min_outlier": float(outlier_series.min())
                }

    # Compile date range
    date_range = "N/A"
    if date_cols:
        try:
            times = pd.to_datetime(df[date_cols[0]], errors="coerce").dropna()
            if not times.empty:
                date_range = f"{times.min().strftime('%Y-%m-%d')} to {times.max().strftime('%Y-%m-%d')}"
        except Exception:
            pass

    # Build prompt context
    user_content = f"""Here is the dataset statistics. Translate this statistical proof into grounded, evidence-based insights.

METADATA:
- File Name: {ds_key or 'Dataset'}
- Row Count: {total_rows}
- Column Count: {col_count}
- Date Range: {date_range}
- Metrics: {numeric_cols}
- Dimensions: {categorical_cols + date_cols}

PRECOMPUTED SYSTEM RESULTS:
- Trust Score: {trust_score}%
- Initial Quality Flags: {dq_flags}
- Forecast Safety: Available={forecast_available}, Reason='{forecast_reason}'
- IQR Outlier Thresholds: {json.dumps(outliers_summary)}

DATA SAMPLE (First 20 rows):
{df.head(20).to_csv(index=False)}
"""

    current_iso = datetime.datetime.utcnow().isoformat() + "Z"

    try:
        response = _client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT + f"\n\nCRITICAL: DO NOT use markdown code block wrappers in your response. Output the JSON object directly. Use the timestamp '{current_iso}' for all generated insights."},
                {"role": "user", "content": user_content}
            ],
            temperature=0.1,
            max_tokens=4000,
            response_format={"type": "json_object"}
        )
        
        resp_text = response.choices[0].message.content.strip()
        
        # Clean JSON fences if LLM accidentally outputs them
        if resp_text.startswith("```"):
            resp_text = re.sub(r"^```(?:json)?\s*", "", resp_text)
            resp_text = re.sub(r"\s*```$", "", resp_text)
        resp_text = resp_text.strip()

        try:
            payload = json.loads(resp_text)
        except json.JSONDecodeError as e:
            return {"success": False, "error": f"JSON parse failed: {str(e)}", "insights": []}

        # Override or enrich keys to guarantee Python precomputations stay the source of truth
        summary = payload.setdefault("dataset_summary", {})
        summary["row_count"] = total_rows
        summary["col_count"] = col_count
        summary["date_range"] = date_range
        summary["metrics"] = numeric_cols
        summary["dimensions"] = categorical_cols + date_cols
        summary["trust_score"] = trust_score
        summary["forecast_safety_status"] = "Safe" if forecast_available else forecast_reason
        summary["data_quality_flags"] = dq_flags
        
        # Inject thresholds to details
        payload["anomaly_bounds"] = outliers_summary
        payload["success"] = True

        # Cache results if active schema key is present
        if ds_key:
            cache = getattr(generate_analytical_insights, "_cache", {})
            cache[ds_key] = payload
            generate_analytical_insights._cache = cache

        return _to_jsonable(payload)

    except Exception as exc:
        logger.exception("Failed calling Groq or parsing insights: %s", exc)
        return {"success": False, "error": f"Failed to generate insights: {exc}"}
