"""
Insight Engine Service — Centrally computes statistical insights from the active dataset.

Generates 3 to 5 plain-language insights based on:
1. Outlier detection using the IQR rule.
2. Category concentration analysis (>40% dominance).
3. Pearson correlation coefficients between numeric fields.
4. Trend detection using a linear slope (regression) over time.
5. Column completeness and data quality alerts.
"""

from __future__ import annotations
import logging
import numpy as np
import pandas as pd
from typing import Dict, List, Any
from backend.utils.active_dataset_store import get_active_connection, TABLE_NAME
from backend.services.recommender_service import build_where_clause

logger = logging.getLogger("insight_engine_service")

def generate_dashboard_insights(schema: Dict[str, str], filters: Dict[str, Any] = None) -> List[str]:
    """
    Analyzes the filtered dataset in SQLite, evaluates statistics in Pandas,
    and returns 3 to 5 plain-language insight strings.
    """
    if not schema:
        return ["No dataset schema found. Please upload a dataset first."]

    filters = filters or {}
    conn = get_active_connection()
    try:
        where_clause, params = build_where_clause(filters, schema)
        
        # Load filtered data into a pandas DataFrame
        query = f"SELECT * FROM {TABLE_NAME} {where_clause}"
        df = pd.read_sql_query(query, conn, params=params)
        
        if df.empty:
            return ["No data available for the selected filters."]
            
        insights = []
        
        num_cols = [c for c, t in schema.items() if t == "NUM" and c in df.columns]
        text_cols = [c for c, t in schema.items() if t in ("TEXT", "MIXED") and c in df.columns]
        date_cols = [c for c, t in schema.items() if t == "DATE" and c in df.columns]
        bool_cols = [c for c, t in schema.items() if t == "BOOL" and c in df.columns]

        # 1. Column Quality Alerts (Missing Data & Duplicates)
        total_rows = len(df)
        for col in df.columns:
            null_count = df[col].isna().sum()
            if null_count > 0:
                pct = (null_count / total_rows) * 100
                if pct > 5.0:
                    insights.append(
                        f"Quality Alert: Column '{col}' has {null_count:,} missing values "
                        f"({pct:.1f}% of total rows). Consider using data cleaning options."
                    )
        
        # Duplicates check
        dupes = df.duplicated().sum()
        if dupes > 0:
            pct_dupe = (dupes / total_rows) * 100
            if pct_dupe > 1.0:
                insights.append(
                    f"Quality Alert: Found {dupes:,} duplicate rows "
                    f"({pct_dupe:.1f}% of dataset)."
                )

        # 2. Outlier Detection (using IQR)
        for col in num_cols[:2]:  # check first two numeric columns
            series = df[col].dropna()
            if len(series) > 10:
                q1 = series.quantile(0.25)
                q3 = series.quantile(0.75)
                iqr = q3 - q1
                lower_bound = q1 - 1.5 * iqr
                upper_bound = q3 + 1.5 * iqr
                
                outliers = series[(series < lower_bound) | (series > upper_bound)]
                if len(outliers) > 0:
                    insights.append(
                        f"Outliers: Detected {len(outliers):,} outlier values in '{col}' "
                        f"(values outside the range {lower_bound:.2f} to {upper_bound:.2f}). "
                        f"Max outlier value is {outliers.max():,}."
                    )

        # 3. Category Concentration Analysis
        if num_cols and text_cols:
            num_col = num_cols[0]
            for text_col in text_cols[:2]:
                grouped = df.groupby(text_col)[num_col].sum()
                total_sum = grouped.sum()
                if total_sum > 0:
                    grouped_sorted = grouped.sort_values(ascending=False)
                    top_cat = grouped_sorted.index[0]
                    top_val = grouped_sorted.iloc[0]
                    share = (top_val / total_sum) * 100
                    
                    if share > 40.0:
                        insights.append(
                            f"Concentration: The '{top_cat}' category is highly dominant in '{text_col}', "
                            f"accounting for {share:.1f}% of all {num_col.replace('_', ' ').title()} "
                            f"({top_val:,.2f} of {total_sum:,.2f})."
                        )

        # 4. Correlation Testing (Pearson correlation)
        if len(num_cols) >= 2:
            # Calculate correlation matrix
            corr_df = df[num_cols[:4]].corr()  # check top 4 numeric columns
            checked_pairs = set()
            for col1 in corr_df.columns:
                for col2 in corr_df.columns:
                    if col1 != col2 and (col2, col1) not in checked_pairs:
                        checked_pairs.add((col1, col2))
                        r_val = corr_df.loc[col1, col2]
                        if not pd.isna(r_val) and abs(r_val) >= 0.70:
                            strength = "strong positive" if r_val > 0 else "strong negative"
                            insights.append(
                                f"Correlation: There is a {strength} relationship (r = {r_val:.2f}) "
                                f"between '{col1}' and '{col2}'."
                            )

        # 5. Trend Detection over time
        if date_cols and num_cols:
            date_col = date_cols[0]
            num_col = num_cols[0]
            
            # Aggregate by date
            agg = df.groupby(date_col)[num_col].sum().reset_index()
            # Clean values
            agg = agg.dropna()
            
            if len(agg) >= 4:
                # Try to fit a simple linear slope
                # Convert dates to sequential integer indices for slope calculation
                x = np.arange(len(agg))
                y = agg[num_col].values
                
                try:
                    slope, intercept = np.polyfit(x, y, 1)
                    first_val = y[0]
                    last_val = y[-1]
                    
                    if first_val > 0:
                        change_pct = ((last_val - first_val) / first_val) * 100
                        direction = "upward" if slope > 0 else "downward"
                        insights.append(
                            f"Trend: '{num_col}' shows a general {direction} trend over time, "
                            f"changing by {change_pct:+.1f}% from the first recorded date "
                            f"({agg[date_col].iloc[0]}) to the last ({agg[date_col].iloc[-1]})."
                        )
                except Exception:
                    pass

        # Ensure we always return at least some descriptive insights
        if not insights:
            insights.append(
                f"Summary: The dataset contains {total_rows:,} rows across {len(schema)} columns. "
                "No extreme statistical outliers, heavy dominance, or strong numerical correlations were detected."
            )
            
        return insights[:5]  # Limit to 3 to 5 insights

    except Exception as exc:
        logger.exception("Error in insight generator service: %s", exc)
        return ["Unable to compile statistical insights due to data parsing error."]
    finally:
        conn.close()
