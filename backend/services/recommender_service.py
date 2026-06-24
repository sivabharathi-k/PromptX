"""
Chart Recommender Service — Centralized heuristics for auto chart selection.

Automatically inspects the dataset schema, identifies optimal combinations of 
temporal, categorical, and numerical columns, and compiles aggregated data 
from SQLite (applying active dashboard filters) to output Chart.js specs.
"""

from __future__ import annotations
import logging
import sqlite3
from typing import Dict, List, Any, Tuple
from backend.utils.active_dataset_store import get_active_connection, TABLE_NAME

logger = logging.getLogger("recommender_service")

def build_where_clause(filters: Dict[str, Any], schema: Dict[str, str]) -> Tuple[str, List[Any]]:
    """
    Build a safe parameterized SQL WHERE clause and parameter list from active filters.
    filters: { col_name: [val1, val2] or {"start": val, "end": val} or single val }
    schema: master schema mapping col_name to type (NUM, TEXT, DATE, BOOL, MIXED)
    """
    if not filters:
        return "", []
    
    where_parts = []
    params = []
    
    for col, val in filters.items():
        # Ensure column exists in schema to prevent SQL injection
        if col not in schema:
            continue
        
        if val is None or val == "" or val == []:
            continue

        col_type = schema[col]
        
        if isinstance(val, dict):
            # Range filter (e.g., date range or numeric range)
            start = val.get("start")
            end = val.get("end")
            if start is not None and start != "":
                where_parts.append(f'"{col}" >= ?')
                params.append(start)
            if end is not None and end != "":
                where_parts.append(f'"{col}" <= ?')
                params.append(end)
        elif isinstance(val, list):
            if len(val) == 1:
                where_parts.append(f'"{col}" = ?')
                params.append(val[0])
            elif len(val) > 1:
                placeholders = ", ".join(["?"] * len(val))
                where_parts.append(f'"{col}" IN ({placeholders})')
                params.extend(val)
        else:
            where_parts.append(f'"{col}" = ?')
            params.append(val)
            
    if not where_parts:
        return "", []
        
    return "WHERE " + " AND ".join(where_parts), params

def get_recommended_charts(schema: Dict[str, str], filters: Dict[str, Any] = None) -> List[Dict[str, Any]]:
    """
    Scans the schema, applies rules, queries the filtered SQLite dataset,
    and returns 3 to 6 chart recommendations.
    """
    if not schema:
        return []
        
    filters = filters or {}
    conn = get_active_connection()
    try:
        where_clause, params = build_where_clause(filters, schema)
        
        # Categorize columns
        num_cols = [c for c, t in schema.items() if t == "NUM"]
        text_cols = [c for c, t in schema.items() if t in ("TEXT", "MIXED")]
        date_cols = [c for c, t in schema.items() if t == "DATE"]
        bool_cols = [c for c, t in schema.items() if t == "BOOL"]
        
        recommendations = []
        chart_idx = 1
        
        # Rule 1: Temporal Trend (Line Chart)
        # Conditions: 1 DATE column + 1 NUM column. If multiple NUM cols, pick the first 1-2.
        if date_cols and num_cols:
            date_col = date_cols[0]
            num_col = num_cols[0]
            
            # Fetch aggregated timeline
            query = f"""
                SELECT "{date_col}", SUM("{num_col}")
                FROM {TABLE_NAME}
                {where_clause}
                GROUP BY "{date_col}"
                ORDER BY "{date_col}" ASC
                LIMIT 50
            """
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            
            if len(rows) > 1:
                labels = [str(r[0]) if r[0] is not None else "Null" for r in rows]
                values = [float(r[1]) if r[1] is not None else 0.0 for r in rows]
                
                title = f"{num_col.replace('_', ' ').title()} Trend Over Time"
                recommendations.append({
                    "id": f"rec_chart_{chart_idx}",
                    "title": title,
                    "type": "line",
                    "x_column": date_col,
                    "y_column": num_col,
                    "spec": {
                        "labels": labels,
                        "series": [{
                            "label": num_col.replace("_", " ").title(),
                            "data": values
                        }]
                    },
                    "reason": f"Line chart shows the historical and progression trend of {num_col.replace('_', ' ').title()} chronologically by {date_col.replace('_', ' ').title()}."
                })
                chart_idx += 1
                
        # Rule 2: Categorical Distribution (Bar Chart / Pie Chart)
        # For each text column (up to 3), match with the first numeric column
        for text_col in text_cols[:3]:
            if not num_cols:
                # Fallback: categorical frequency (count)
                query = f"""
                    SELECT "{text_col}", COUNT(*) as cnt
                    FROM {TABLE_NAME}
                    {where_clause}
                    GROUP BY "{text_col}"
                    ORDER BY cnt DESC
                    LIMIT 15
                """
                cur = conn.cursor()
                cur.execute(query, params)
                rows = cur.fetchall()
                
                if len(rows) > 1:
                    labels = [str(r[0]) if r[0] is not None else "Missing" for r in rows]
                    values = [int(r[1]) for r in rows]
                    
                    recommendations.append({
                        "id": f"rec_chart_{chart_idx}",
                        "title": f"Frequency distribution of {text_col.replace('_', ' ').title()}",
                        "type": "bar",
                        "x_column": text_col,
                        "y_column": "count",
                        "spec": {
                            "labels": labels,
                            "series": [{
                                "label": "Record Count",
                                "data": values
                            }]
                        },
                        "reason": f"Bar chart compares the occurrence frequency of items within different {text_col.replace('_', ' ').title()} categories."
                    })
                    chart_idx += 1
            else:
                num_col = num_cols[0]
                # Query aggregate values
                query = f"""
                    SELECT "{text_col}", SUM("{num_col}") as total
                    FROM {TABLE_NAME}
                    {where_clause}
                    GROUP BY "{text_col}"
                    ORDER BY total DESC
                """
                cur = conn.cursor()
                cur.execute(query, params)
                rows = cur.fetchall()
                
                if len(rows) > 1:
                    # Check cardinality for Pie/Doughnut Recommendation
                    # 2 to 6 categories: Pie Chart. More: Bar Chart (limit to top 10, group remainder as 'Others')
                    if len(rows) <= 6:
                        labels = [str(r[0]) if r[0] is not None else "Null" for r in rows]
                        values = [float(r[1]) if r[1] is not None else 0.0 for r in rows]
                        
                        recommendations.append({
                            "id": f"rec_chart_{chart_idx}",
                            "title": f"Share of {num_col.replace('_', ' ').title()} by {text_col.replace('_', ' ').title()}",
                            "type": "pie",
                            "x_column": text_col,
                            "y_column": num_col,
                            "spec": {
                                "labels": labels,
                                "series": [{
                                    "label": num_col.replace("_", " ").title(),
                                    "data": values
                                }]
                            },
                            "reason": f"Pie chart displays the composition breakdown and relative percentage share of {num_col.replace('_', ' ').title()} across {text_col.replace('_', ' ').title()} segments."
                        })
                        chart_idx += 1
                    else:
                        # Bar chart for higher cardinality
                        top_rows = rows[:10]
                        labels = [str(r[0]) if r[0] is not None else "Null" for r in top_rows]
                        values = [float(r[1]) if r[1] is not None else 0.0 for r in top_rows]
                        
                        # Add 'Others' if there are more than 10 rows
                        if len(rows) > 10:
                            others_sum = sum(float(r[1]) if r[1] is not None else 0.0 for r in rows[10:])
                            labels.append("Others")
                            values.append(others_sum)
                            
                        recommendations.append({
                            "id": f"rec_chart_{chart_idx}",
                            "title": f"Total {num_col.replace('_', ' ').title()} by {text_col.replace('_', ' ').title()}",
                            "type": "bar",
                            "x_column": text_col,
                            "y_column": num_col,
                            "spec": {
                                "labels": labels,
                                "series": [{
                                    "label": num_col.replace("_", " ").title(),
                                    "data": values
                                }]
                            },
                            "reason": f"Bar chart compares the aggregate {num_col.replace('_', ' ').title()} across different {text_col.replace('_', ' ').title()} categories."
                        })
                        chart_idx += 1

        # Rule 3: Scatter Plot for two numeric columns (Correlation)
        if len(num_cols) >= 2:
            num1, num2 = num_cols[0], num_cols[1]
            # Fetch up to 300 records to plot scatter coordinates (safe performance rendering)
            query = f"""
                SELECT "{num1}", "{num2}"
                FROM {TABLE_NAME}
                {where_clause}
                LIMIT 300
            """
            cur = conn.cursor()
            cur.execute(query, params)
            rows = cur.fetchall()
            
            if len(rows) > 5:
                # Format for Chart.js scatter: data array of {x, y} objects
                xy_points = [{"x": float(r[0]) if r[0] is not None else 0.0, "y": float(r[1]) if r[1] is not None else 0.0} for r in rows if r[0] is not None and r[1] is not None]
                
                recommendations.append({
                    "id": f"rec_chart_{chart_idx}",
                    "title": f"{num2.replace('_', ' ').title()} vs {num1.replace('_', ' ').title()} Correlation",
                    "type": "scatter",
                    "x_column": num1,
                    "y_column": num2,
                    "spec": {
                        "series": [{
                            "label": f"{num2.replace('_', ' ').title()} vs {num1.replace('_', ' ').title()}",
                            "data": xy_points
                        }]
                    },
                    "reason": f"Scatter plot displays direct data point distribution to analyze the correlation, outliers, and cluster density between {num1.replace('_', ' ').title()} and {num2.replace('_', ' ').title()}."
                })
                chart_idx += 1

        # Rule 4: Grouped/Stacked Area Chart (Date + Text + Num)
        if date_cols and text_cols and num_cols:
            date_col = date_cols[0]
            text_col = text_cols[0]
            num_col = num_cols[0]
            
            # Check cardinality of category col - needs to be small to stack nicely
            cur = conn.cursor()
            cur.execute(f"SELECT COUNT(DISTINCT \"{text_col}\") FROM {TABLE_NAME} {where_clause}", params)
            distinct_count = cur.fetchone()[0]
            
            if 2 <= distinct_count <= 5:
                # Query dates and breakdown
                query = f"""
                    SELECT "{date_col}", "{text_col}", SUM("{num_col}")
                    FROM {TABLE_NAME}
                    {where_clause}
                    GROUP BY "{date_col}", "{text_col}"
                    ORDER BY "{date_col}" ASC
                """
                cur.execute(query, params)
                rows = cur.fetchall()
                
                if len(rows) > 4:
                    # Pivot in python
                    dates = sorted(list(set(str(r[0]) if r[0] is not None else "Null" for r in rows)))
                    categories = sorted(list(set(str(r[1]) if r[1] is not None else "Null" for r in rows)))
                    
                    pivot_data = {cat: [0.0] * len(dates) for cat in categories}
                    date_to_idx = {d: i for i, d in enumerate(dates)}
                    
                    for r_date, r_cat, r_val in rows:
                        d_str = str(r_date) if r_date is not None else "Null"
                        c_str = str(r_cat) if r_cat is not None else "Null"
                        if d_str in date_to_idx and c_str in pivot_data:
                            pivot_data[c_str][date_to_idx[d_str]] = float(r_val) if r_val is not None else 0.0
                            
                    series = [{"label": cat.replace("_", " ").title(), "data": vals} for cat, vals in pivot_data.items()]
                    
                    recommendations.append({
                        "id": f"rec_chart_{chart_idx}",
                        "title": f"{num_col.replace('_', ' ').title()} Composition by {text_col.replace('_', ' ').title()} Over Time",
                        "type": "area",
                        "x_column": date_col,
                        "y_column": num_col,
                        "spec": {
                            "labels": dates,
                            "series": series
                        },
                        "reason": f"Stacked area chart depicts how the total composition and category share of {num_col.replace('_', ' ').title()} by {text_col.replace('_', ' ').title()} shifts over chronological periods of {date_col.replace('_', ' ').title()}."
                    })
                    chart_idx += 1

        return recommendations[:6]  # Ensure 3 to 6 charts maximum
        
    except Exception as exc:
        logger.exception("Error generating chart recommendations: %s", exc)
        return []
    finally:
        conn.close()
