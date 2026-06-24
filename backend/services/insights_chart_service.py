"""
Insights Chart Service — Aggregates data from SQLite to feed the mini evidence charts 
rendered inside AI Insight cards.
"""

from __future__ import annotations
import logging
from typing import Dict, List, Any
from backend.utils.active_dataset_store import get_active_connection, TABLE_NAME
from backend.services.recommender_service import build_where_clause

logger = logging.getLogger("insights_chart_service")

def resolve_column_name(col_name: str, schema: Dict[str, str]) -> str | None:
    """
    Fuzzy resolves a column name against the schema, ignoring casing, spaces, and underscores.
    """
    if not col_name or not schema:
        return None
    if col_name in schema:
        return col_name
    
    def standardize(s: str) -> str:
        return s.lower().replace("_", "").replace(" ", "")
        
    target = standardize(col_name)
    for col in schema.keys():
        if standardize(col) == target:
            return col
    return None

def get_insight_chart_series(
    metric: str, 
    dimension: str, 
    filters: Dict[str, Any], 
    schema: Dict[str, str],
    chart_type: str = "bar"
) -> Dict[str, Any]:
    """
    Queries the database and aggregates values for the given metric and dimension,
    applying filters, formatted as { labels: [], data: [] }.
    """
    if not schema:
        return {"labels": [], "data": []}

    filters = filters or {}
    
    # Fuzzy resolve metric and dimension
    resolved_metric = resolve_column_name(metric, schema)
    resolved_dimension = resolve_column_name(dimension, schema)

    # Smart fallback for dimensions if missing or set to "none"
    if not resolved_dimension or resolved_dimension == "none":
        # Try DATE columns first to show trend over time
        date_cols = [col for col, dtype in schema.items() if dtype == "DATE"]
        if date_cols:
            resolved_dimension = date_cols[0]
            chart_type = "line"
        else:
            # Try TEXT columns next
            text_cols = [col for col, dtype in schema.items() if dtype in ("TEXT", "MIXED")]
            if text_cols:
                resolved_dimension = text_cols[0]
                chart_type = "bar"
            else:
                # Fall back to any column that is not the resolved metric
                non_metric_cols = [col for col in schema.keys() if col != resolved_metric]
                if non_metric_cols:
                    resolved_dimension = non_metric_cols[0]
                else:
                    resolved_dimension = list(schema.keys())[0] if schema else None

    # If still no dimension resolved or not in schema, return empty
    if not resolved_dimension or resolved_dimension not in schema:
        return {"labels": [], "data": []}

    dimension = resolved_dimension
    metric = resolved_metric or "none"

    conn = get_active_connection()
    try:
        where_clause, params = build_where_clause(filters, schema)
        cur = conn.cursor()
        
        # Decide aggregation based on metric type
        if not metric or metric == "none" or metric not in schema:
            agg_expr = "COUNT(*)"
            metric_label = "Count"
        else:
            agg_expr = f'SUM("{metric}")'
            metric_label = metric.replace('_', ' ').title()

        # Handle chronological sorting for line charts on dates
        dim_type = schema.get(dimension)
        order_clause = ""
        if dim_type == "DATE" or chart_type == "line":
            order_clause = f'ORDER BY "{dimension}" ASC'
        else:
            order_clause = f'ORDER BY val DESC'

        query = f"""
            SELECT "{dimension}", {agg_expr} as val
            FROM {TABLE_NAME}
            {where_clause}
            GROUP BY "{dimension}"
            {order_clause}
            LIMIT 15
        """
        
        cur.execute(query, params)
        rows = cur.fetchall()
        
        labels = [str(r[0]) if r[0] is not None else "Null" for r in rows]
        values = [float(r[1]) if r[1] is not None else 0.0 for r in rows]
        
        return {
            "labels": labels,
            "data": values,
            "metric_label": metric_label,
            "dimension_label": dimension.replace('_', ' ').title()
        }
        
    except Exception as exc:
        logger.exception("Error aggregating insights chart data: %s", exc)
        return {"labels": [], "data": []}
    finally:
        conn.close()

