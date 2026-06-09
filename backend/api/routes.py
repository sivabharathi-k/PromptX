"""
API routes — all HTTP endpoints registered on a Flask Blueprint.
"""

import io
import json
import logging
import re

import pandas as pd
from flask import Blueprint, jsonify, request, send_file, session
from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.services.export_service import to_excel, to_image, to_pdf, to_word
from backend.services.query_service import execute_sql, generate_sql
from backend.services.visualization_profile_service import VisualizationProfileService
from backend.services.chart_recommendation_service import ChartRecommendationService
from backend.services.visualization_preparation_service import VisualizationPreparationService
from backend.services.chart_recommender import ChartRecommender
from backend.services.insights.insights_engine import generate_insights as generate_insights_engine



from backend.utils.db_utils import get_schema, load_dataframe
from backend.utils.file_utils import read_csv
from backend.utils.active_dataset_store import (
    load_dataframe_into_active_db, get_active_schema, active_dataset_exists, get_active_connection,
    get_master_schema, get_master_schema_formatted
)
from backend.services.insert_service import insert_rows
from backend.services.update_service import update_rows
from backend.services.delete_service import preview_delete as preview_delete_service, delete_rows as delete_rows_service
from backend.services.schema_service import (
    add_column as add_column_service, rename_column as rename_column_service, remove_column as remove_column_service,
    _call_llm as schema_call_llm
)
from backend.services.cleaning_service import clean as clean_service
from backend.services.transformation_service import transform as transform_service
from backend.services.audit_service import create_snapshot_for_undo, undo_last_operation
from backend.services.relevance_validator import RelevanceValidator, _normalize

logger = logging.getLogger("routes")
_relevance_validator = RelevanceValidator()
api    = Blueprint("api", __name__)

_client = Groq(api_key=GROQ_API_KEY)


def _clean_rows(rows: list) -> list:
    """Replace NaN/Infinity float values with None so JSON serialization never breaks."""
    import math
    def _fix(v):
        if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
            return None
        return v
    return [{k: _fix(v) for k, v in row.items()} for row in rows]

_CLASSIFY_SYSTEM_PROMPT = """
You are an AI assistant that classifies user intents for a dataset application.
The user is interacting with a single table named "dataset".

Classify the user's input into one of these 4 intents:
1. "query" - The user is asking a question about the data, requesting a calculation, filtering, summarizing, or querying the dataset without modifying the dataset or requesting a chart.
2. "edit" - The user wants to modify the dataset (inserting, updating, deleting records, adding/renaming/removing columns, cleaning duplicates/nulls, running transformations, or undoing an operation).
3. "visualization" - The user explicitly requests a chart, plot, or visual representation (e.g. "plot X by Y", "show bar chart of X", "pie chart of Y").
4. "schema" - The user wants to inspect the columns, schema, datatypes, metadata, or description of the dataset (e.g. "show columns", "describe dataset", "what are the columns").

Return ONLY a JSON object with:
{{
  "intent": "query" | "edit" | "visualization" | "schema",
  "explanation": "Short sentence explaining why",
  "details": {{
    "operation_type": "insert" | "update" | "delete" | "schema_add" | "schema_rename" | "schema_remove" | "clean" | "transform" | "undo" | "save_subset" | null,
    "chart_type": "bar" | "line" | "pie" | "donut" | "scatter" | "area" | "histogram" | null,
    "x_column": "exact X column name if mentioned or null",
    "y_column": "exact Y column name if mentioned or null"
  }}
}}

Use the following ACTIVE SCHEMA to verify column names for visualization or edit details if needed:
{schema}
"""


def _pandas_fallback(df: pd.DataFrame, question: str) -> pd.DataFrame | None:
    """
    Rule-based pandas fallback when SQL generation fails.
    Covers the most common question patterns without any LLM call.
    """
    q = question.lower().strip()
    num_cols  = df.select_dtypes(include="number").columns.tolist()
    text_cols = df.select_dtypes(include="object").columns.tolist()

    # count / total rows
    if any(w in q for w in ("count", "how many", "total rows", "number of rows")):
        return pd.DataFrame({"total_rows": [len(df)]})

    # top N
    top_match = re.search(r"top\s*(\d+)", q)
    n = int(top_match.group(1)) if top_match else 10
    if any(w in q for w in ("top", "first", "head", "preview", "show")):
        if num_cols and not any(w in q for w in ("first", "preview", "show all", "show me")):
            col = num_cols[0]
            return df.nlargest(min(n, len(df)), col).reset_index(drop=True)
        return df.head(n).reset_index(drop=True)

    # duplicates
    if any(w in q for w in ("duplicate", "duplicated", "repeated")):
        dupes = df[df.duplicated(keep=False)]
        return dupes.reset_index(drop=True) if not dupes.empty else pd.DataFrame({"result": ["No duplicates found"]})

    # missing / null
    if any(w in q for w in ("missing", "null", "empty", "blank")):
        counts = df.isnull().sum()
        return pd.DataFrame({"column": counts.index, "missing_count": counts.values})

    # unique / distinct
    if any(w in q for w in ("unique", "distinct")):
        for col in text_cols + num_cols:
            if col.lower() in q or any(w in col.lower() for w in q.split()):
                return pd.DataFrame({col: df[col].dropna().unique()})
        if text_cols:
            return pd.DataFrame({text_cols[0]: df[text_cols[0]].dropna().unique()})

    # highest / maximum
    if any(w in q for w in ("highest", "maximum", "max", "largest", "most")):
        if num_cols:
            col = num_cols[0]
            return df.nlargest(10, col)[[col] + text_cols[:2]].reset_index(drop=True)

    # lowest / minimum
    if any(w in q for w in ("lowest", "minimum", "min", "smallest", "least")):
        if num_cols:
            col = num_cols[0]
            return df.nsmallest(10, col)[[col] + text_cols[:2]].reset_index(drop=True)

    # average / mean
    if any(w in q for w in ("average", "mean", "avg")):
        if num_cols:
            avgs = df[num_cols].mean().round(2).reset_index()
            avgs.columns = ["column", "average"]
            return avgs

    # keyword search across all columns
    words = [w for w in q.split() if len(w) > 2]
    for word in words:
        for col in text_cols:
            mask = df[col].astype(str).str.contains(word, case=False, na=False)
            if mask.any():
                return df[mask].reset_index(drop=True)

    # final fallback: return first 50 rows
    return df.head(50).reset_index(drop=True)


def get_active_dataset_preview(limit: int = 50) -> dict:
    """Get the first N rows of the active dataset table directly from SQLite."""
    import math
    conn = get_active_connection()
    try:
        cur = conn.cursor()
        cols = [r[1] for r in cur.execute("PRAGMA table_info(dataset)").fetchall()]
        rows = cur.execute(f'SELECT * FROM dataset LIMIT {int(limit)}').fetchall()
        def _fix(v):
            if isinstance(v, float) and (math.isnan(v) or math.isinf(v)):
                return None
            return v
        row_dicts = [{cols[i]: _fix(r[i]) for i in range(len(cols))} for r in rows]
        total = cur.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]
        return {
            "columns": cols,
            "rows": row_dicts,
            "total": total
        }
    finally:
        conn.close()


def sync_active_db_to_session():
    """Sync the updated SQLite table back to session['last_result'] for downloads/visualization."""
    conn = get_active_connection()
    try:
        df = pd.read_sql("SELECT * FROM dataset", conn)
        session["last_result"] = df.to_json(orient="split")
        session.modified = True
    finally:
        conn.close()


def generate_schema_description() -> str:
    """Generate a markdown description of the dataset schema."""
    conn = get_active_connection()
    try:
        cur = conn.cursor()
        cols = cur.execute("PRAGMA table_info(dataset)").fetchall()
        total_rows = cur.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]

        md = "### 📊 Dataset Schema Summary\n"
        md += f"- **Total Columns**: {len(cols)}\n"
        md += f"- **Total Rows**: {total_rows}\n\n"
        md += "| Column Name | SQLite Data Type | Sample Values (up to 3) |\n"
        md += "| :--- | :--- | :--- |\n"

        for col in cols:
            col_id, name, col_type, notnull, default_val, pk = col
            sample_rows = cur.execute(f'SELECT DISTINCT "{name}" FROM dataset WHERE "{name}" IS NOT NULL LIMIT 3').fetchall()
            samples = ", ".join([str(r[0]) for r in sample_rows])
            md += f"| `{name}` | `{col_type or 'TEXT'}` | {samples or '*None*'} |\n"

        return md
    finally:
        conn.close()


def generate_data_quality_report() -> str:
    """Generate a rich data quality report in markdown."""
    conn = get_active_connection()
    try:
        cur = conn.cursor()
        cols = cur.execute("PRAGMA table_info(dataset)").fetchall()
        col_names = [r[1] for r in cols]

        total_rows = cur.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]

        col_list_str = ", ".join([f'"{c}"' for c in col_names])
        dupe_query = f"SELECT COUNT(*) FROM (SELECT 1 FROM dataset GROUP BY {col_list_str} HAVING COUNT(*) > 1)"
        dupes_count = cur.execute(dupe_query).fetchone()[0]

        missing_report = []
        for c in col_names:
            nulls = cur.execute(f'SELECT COUNT(*) FROM dataset WHERE "{c}" IS NULL').fetchone()[0]
            blanks = cur.execute(f'SELECT COUNT(*) FROM dataset WHERE TRIM(CAST("{c}" AS TEXT)) = \'\'').fetchone()[0]
            missing_report.append({
                "column": c,
                "nulls": nulls,
                "blanks": blanks,
                "total_missing": nulls + blanks
            })

        md = "## 🔍 Data Quality & Health Report\n\n"
        md += f"- **Total Rows**: {total_rows}\n"
        md += f"- **Duplicate Records (Groups)**: {dupes_count} row groups are duplicated.\n\n"

        md += "### Column Missing / Empty Values Analysis\n\n"
        md += "| Column Name | Nulls | Empty Strings | Total Missing | Missing % |\n"
        md += "| :--- | :---: | :---: | :---: | :---: |\n"
        for item in missing_report:
            pct = round((item["total_missing"] / total_rows) * 100, 2) if total_rows > 0 else 0
            md += f"| `{item['column']}` | {item['nulls']} | {item['blanks']} | **{item['total_missing']}** | {pct}% |\n"

        md += "\n> [!TIP]\n"
        if dupes_count > 0:
            md += "> - You have duplicate records! Ask me to **'Remove duplicate records'** to clean them up.\n"
        has_missing = any(item["total_missing"] > 0 for item in missing_report)
        if has_missing:
            md += "> - You have missing values. You can ask me to **'Fill missing values in Column with X'** or **'Remove null rows'**.\n"
        if not has_missing and dupes_count == 0:
            md += "> - Your dataset looks exceptionally clean! No missing or duplicate values found.\n"

        return md
    finally:
        conn.close()


# NOTE: legacy LLM-based insights generator removed.
# The new enterprise insight engine lives in:
#   backend/services/insights/insights_engine.py




def _parse_user_chart_type(question: str) -> str | None:
    """Extract explicitly requested chart type from the question string."""
    q = question.lower()
    mapping = [
        ("donut",     "donut"),
        ("doughnut",  "donut"),
        ("pie",       "pie"),
        ("scatter",   "scatter"),
        ("histogram", "histogram"),
        ("area",      "area"),
        ("line",      "line"),
        ("bar",       "bar"),
    ]
    for keyword, chart in mapping:
        if keyword in q:
            return chart
    return None


def auto_generate_visualization(question: str, schema: str, df: pd.DataFrame) -> dict:
    """AI-powered chart recommendation — no extra LLM call needed."""
    try:
        profile_service = VisualizationProfileService()
        prep_service    = VisualizationPreparationService()
        recommender     = ChartRecommender()

        profile = profile_service.profile(df)

        # Honour explicit user chart type (Mode 1) or let AI decide (Mode 2)
        user_chart = _parse_user_chart_type(question)
        rec = recommender.recommend(df, profile, question=question, user_requested_chart=user_chart)

        chart_type = rec["recommended_chart"]
        x_col      = rec["x_axis"]
        y_col      = rec["y_axis"]

        # Validate columns still exist in df
        if x_col and x_col not in df.columns:
            x_col = df.columns[0] if len(df.columns) > 0 else None
        if y_col and y_col not in df.columns:
            y_col = None

        spec = prep_service.render_with_axes(
            df=df, chart_type=chart_type, profile=profile,
            x_column=x_col, y_column=y_col
        )

        return {
            "spec":               spec,
            "plotType":           spec.get("plotType"),
            "chart_type":         chart_type,
            "x_column":           x_col,
            "y_column":           y_col,
            "reason":             rec["reason"],
            "all_types":          rec["all_types"],
            "insights":           rec["insights"],
        }
    except Exception as e:
        logger.exception("Failed to auto-generate visualization: %s", str(e))
        return None


def execute_confirmed_operation(op_type: str, question: str) -> tuple:
    """Execute a destructive delete or drop operation once confirmed."""
    schema = get_active_schema()
    snapshot_id = create_snapshot_for_undo(operation_type=op_type, affected_rows=0, details={"question": question})
    try:
        if op_type == "delete":
            res = delete_rows_service(question=question, schema=schema)
            msg = res.get("message") or f"Successfully deleted {res.get('deletedRows', 0)} rows."
        elif op_type == "schema_remove":
            res = remove_column_service(question=question, schema=schema)
            msg = res.get("message") or f"Successfully dropped column."
        else:
            return jsonify({"error": "Unknown pending operation type."}), 400

        sync_active_db_to_session()
        preview = get_active_dataset_preview()
        return jsonify({
            "type": "edit",
            "message": f"✅ {msg} (Undo ID: {snapshot_id})",
            "columns": preview["columns"],
            "rows": preview["rows"],
            "total": preview["total"]
        })
    except Exception as e:
        undo_last_operation(operation_id=snapshot_id)
        return jsonify({"error": f"Operation failed and was reverted: {str(e)}"}), 400


@api.route("/insights", methods=["POST"])
def insights():
    """Enterprise dataset-wide insights (structured JSON only)."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset. Please upload a CSV file first."}), 400

    try:
        payload = generate_insights_engine()
        # Always return a JSON object with a stable shape
        if isinstance(payload, dict):
            if "success" not in payload:
                payload["success"] = True
        return jsonify(payload)
    except Exception as e:
        import traceback
        tb = traceback.format_exc()
        logger.exception("Insights generation failed: %s", str(e))
        return jsonify({
            "success": False,
            "error": f"Insights generation failed: {str(e)}",
            "debug": tb,
        }), 500




@api.route("/schema", methods=["GET"])
def get_schema_endpoint():
    """Return the master schema dict (NUM/TEXT/DATE) for the active dataset."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    master = get_master_schema()
    if not master:
        return jsonify({"error": "No schema detected yet."}), 400

    return jsonify({
        "schema": master,
        "columns": list(master.keys()),
    })


@api.route("/upload", methods=["POST"])
def upload():
    """Validate and store an uploaded CSV file."""

    df, error = read_csv(request.files.get("file"))

    if error:
        logger.warning("Upload rejected: %s", error)
        return jsonify({"error": error}), 400

    filename = request.files.get("file").filename

    # Wipe every trace of the previous dataset before storing the new one.
    session.clear()
    session["file_name"] = filename
    session.modified     = True

    # SQLite is the source of truth (also stores master schema)
    load_dataframe_into_active_db(df, if_exists="replace")

    # Set initial query results preview
    session["last_result"] = df.to_json(orient="split")
    session["last_query_sql"] = "SELECT * FROM dataset"
    session.modified = True

    # Get the master schema that was just detected
    master_schema = get_master_schema()

    logger.info(
        "Dataset uploaded — file: '%s' | rows: %d | columns: %d | cols: %s",
        filename, len(df), len(df.columns), list(df.columns),
    )

    return jsonify({
        "message": f"'{filename}' uploaded successfully.",
        "rows":    len(df),
        "columns": list(df.columns),
        "schema":  master_schema,  # Include master schema in upload response
    })


@api.route("/query", methods=["POST"])
def query():
    """Unified conversational entry point."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset. Please upload a CSV file first."}), 400

    question = (request.json or {}).get("question", "").strip()
    if not question:
        return jsonify({"error": "Please enter a question."}), 400

    question_lower = question.lower()

    # ── 1. Destructive confirmation intercept ─────────────────────────
    if question_lower == "confirm" or "confirm" in question_lower:
        pending = session.get("pending_operation")
        if pending:
            pending_question = pending["question"]
            pending_type = pending["type"]
            session.pop("pending_operation", None)
            session.modified = True
            return execute_confirmed_operation(pending_type, pending_question)

    # Any other query cancels a pending operation
    if "pending_operation" in session:
        session.pop("pending_operation", None)
        session.modified = True

    # Get active schema & connection
    schema = get_active_schema()
    conn = get_active_connection()

    try:
        # ── 2. Route Data Quality/Insights manually if detected ─────────
        if any(w in question_lower for w in ("quality report", "missing values report", "duplicate report", "quality health")):
            report = generate_data_quality_report()
            preview = get_active_dataset_preview()
            return jsonify({
                "type": "schema",
                "message": report,
                "columns": preview["columns"],
                "rows": preview["rows"],
                "total": preview["total"]
            })

        # NOTE: AI Insights are now a dedicated endpoint.
        # Do not generate structured insights inside the chat flow.


        # ── 3. Classify intent via LLM ─────────────────────────────────
        classification = classify_intent(question, schema)
        intent = classification.get("intent", "query")
        details = classification.get("details") or {}
        op_type = details.get("operation_type")

        # ── 4. Process visualization intent ────────────────────────────
        if intent == "visualization":
            if "last_result" not in session:
                return jsonify({"error": "No data to visualize yet. Run a query first."}), 400
            df = pd.read_json(io.StringIO(session["last_result"]), orient="split")
            viz_data = auto_generate_visualization(question, schema, df)
            if viz_data:
                user_chart = _parse_user_chart_type(question)
                mode_note  = f"You requested a **{user_chart}** chart." if user_chart else "AI selected the best chart type for your data."
                return jsonify({
                    "type":          "visualization",
                    "message":       mode_note,
                    "visualization": viz_data,
                    "columns":       list(df.columns),
                    "rows":          _clean_rows(df.head(100).to_dict(orient="records")),
                    "total":         len(df),
                })
            else:
                return jsonify({"error": "Could not generate chart spec."}), 422

        # ── 5. Process schema intent ───────────────────────────────────
        if intent == "schema":
            report = generate_schema_description()
            preview = get_active_dataset_preview()
            return jsonify({
                "type": "schema",
                "message": report,
                "columns": preview["columns"],
                "rows": preview["rows"],
                "total": preview["total"]
            })

        # ── 6. Process edit intent ─────────────────────────────────────
        if intent == "edit" and op_type:
            # Check destructive confirmation requirement
            if op_type == "delete":
                preview = preview_delete_service(question=question, schema=schema)
                affected_rows = preview.get("affectedRows", 0)
                if affected_rows > 0:
                    session["pending_operation"] = {"type": "delete", "question": question}
                    session.modified = True
                    return jsonify({
                        "type": "delete_confirm",
                        "message": f"⚠️ This operation will delete **{affected_rows}** rows. Type **CONFIRM** to proceed.",
                        "requires_confirm": True
                    })

            if op_type == "schema_remove":
                spec = schema_call_llm(question=question, schema=schema)
                rm = spec.get("removeColumn")
                if rm:
                    col_name = rm["name"]
                    session["pending_operation"] = {"type": "schema_remove", "question": question}
                    session.modified = True
                    return jsonify({
                        "type": "delete_confirm",
                        "message": f"⚠️ This operation will drop column **'{col_name}'**. Type **CONFIRM** to proceed.",
                        "requires_confirm": True
                    })

            # Non-destructive or confirmed edits
            snapshot_id = create_snapshot_for_undo(operation_type=op_type, affected_rows=0, details={"question": question})
            try:
                if op_type == "insert":
                    res = insert_rows(question=question, schema=schema)
                    msg = f"Successfully inserted row(s)."
                elif op_type == "update":
                    res = update_rows(question=question, schema=schema)
                    msg = f"Successfully updated {res.get('updatedRows', 0)} rows."
                elif op_type == "schema_add":
                    res = add_column_service(question=question, schema=schema)
                    msg = f"Successfully added column '{res.get('column')}'."
                elif op_type == "schema_rename":
                    res = rename_column_service(question=question, schema=schema)
                    msg = f"Successfully renamed column '{res.get('from')}' to '{res.get('to')}'."
                elif op_type == "clean":
                    res = clean_service(question=question, schema=schema)
                    msg = f"Cleaning completed: {res.get('operation')}."
                elif op_type == "transform":
                    res = transform_service(question=question, schema=schema)
                    msg = f"Transformation completed."
                elif op_type == "undo":
                    res = undo_last_operation()
                    if not res.get("undone"):
                        return jsonify({"error": res.get("error") or "Undo failed."}), 400
                    msg = "Last action undone."
                elif op_type == "save_subset":
                    sql = session.get("last_query_sql")
                    if not sql:
                        return jsonify({"error": "No query subset available. Run a query first."}), 400
                    cur = conn.cursor()
                    cur.execute("DROP TABLE IF EXISTS dataset__tmp__")
                    cur.execute(f"CREATE TABLE dataset__tmp__ AS {sql}")
                    cur.execute("DROP TABLE dataset")
                    cur.execute("ALTER TABLE dataset__tmp__ RENAME TO dataset")
                    conn.commit()
                    msg = "Subset successfully saved as current active dataset."
                else:
                    return jsonify({"error": "Unsupported edit operation type."}), 400

                sync_active_db_to_session()
                preview = get_active_dataset_preview()
                return jsonify({
                    "type": "edit",
                    "message": f"✅ {msg} (Undo ID: {snapshot_id})",
                    "columns": preview["columns"],
                    "rows": preview["rows"],
                    "total": preview["total"]
                })
            except Exception as edit_err:
                undo_last_operation(operation_id=snapshot_id)
                logger.exception("Edit failed: %s", str(edit_err))
                return jsonify({"error": f"Operation failed and reverted: {str(edit_err)}"}), 400

        # ── 7. Relevance validation before SQL generation ────────────────
        rel = _relevance_validator.validate(question=question, schema=schema)
        if not rel.relevant:
            return jsonify({
                "type":        "irrelevant",
                "message":     rel.reason,
                "suggestions": rel.suggestions,
            })

        # ── 8. Process query / analysis intent ───────────────────────────
        sql = generate_sql(question, schema)
        logger.info("Generated SQL: %s", sql)

        result, err = execute_sql(sql, conn, question=question, schema=schema)

        if err:
            logger.warning("SQL failed (%s) — running pandas fallback", err)
            df_active = pd.read_sql("SELECT * FROM dataset", conn)
            result = _pandas_fallback(df_active, question)
            if result is None or result.empty:
                return jsonify({"error": f"Could not answer: {err}"}), 500

        if result.empty:
            return jsonify({"error": "No results found for your question."}), 404

        session["last_result"] = result.to_json(orient="split")
        session["last_query_sql"] = sql
        session.modified = True

        return jsonify({
            "type": "query",
            "columns": list(result.columns),
            "rows": _clean_rows(result.to_dict(orient="records")),
            "total": len(result)
        })

    except Exception as e:
        logger.exception("Unexpected error: %s", str(e))
        return jsonify({"error": f"Unexpected error: {str(e)}"}), 500
    finally:
        if conn:
            conn.close()


def _fast_classify(question: str) -> dict | None:
    """Rule-based intent detection — returns result instantly, no LLM call.
    Returns None if the question is ambiguous and needs LLM classification.
    """
    q = _normalize(question)  # normalize first: "five" -> "5", synonyms expanded

    # ── Visualization keywords (high confidence) ──────────────
    viz_words = (
        "plot", "chart", "bar chart", "pie chart", "line chart",
        "scatter", "histogram", "visualize", "visualise", "visualize it",
        "visualise it", "visualize this", "visualise this",
        "graph", "donut", "area chart", "show graph",
        "show chart", "create chart", "create a chart", "plot data",
        "analyze visually", "analyse visually", "visual", "draw chart",
        "generate chart", "make chart", "show plot",
        "show me a chart", "show a chart", "give me a chart",
    )
    if any(w in q for w in viz_words):
        return {"intent": "visualization", "details": {"operation_type": None}}

    # ── Schema / describe keywords ────────────────────────────
    schema_words = ("show columns", "list columns", "describe", "what columns",
                    "column names", "data types", "schema", "metadata",
                    "what are the columns", "show schema")
    if any(w in q for w in schema_words):
        return {"intent": "schema", "details": {"operation_type": None}}

    # ── Edit: undo ────────────────────────────────────────────
    if q in ("undo", "undo last", "revert", "undo last action"):
        return {"intent": "edit", "details": {"operation_type": "undo"}}

    # ── Edit: clean operations ────────────────────────────────
    clean_words = ("remove duplicate", "drop duplicate", "fill null",
                   "fill missing", "remove null", "drop null",
                   "trim spaces", "uppercase", "lowercase")
    if any(w in q for w in clean_words):
        return {"intent": "edit", "details": {"operation_type": "clean"}}

    # ── Pure query keywords (high confidence — skip LLM classify) ──
    query_words = (
        "show", "display", "give", "send", "fetch", "list", "view", "get",
        "first", "last", "top", "bottom", "sample", "preview", "example",
        "count", "average", "total", "sum", "minimum", "maximum",
        "highest", "lowest", "best", "worst", "filter", "where",
        "group by", "order by", "sort", "distinct", "unique",
        "missing", "null", "duplicate", "rows", "records", "entries",
        "select", "how many", "show all",
    )
    if any(w in q for w in query_words):
        return {"intent": "query", "details": {"operation_type": None}}

    # Ambiguous — let LLM decide
    return None


def classify_intent(question: str, schema: str) -> dict:
    """Classify user intent: fast rule-based first, LLM only if ambiguous."""
    # Try fast path first — no LLM latency
    fast = _fast_classify(question)
    if fast is not None:
        logger.info("classify_intent: fast-path -> %s", fast["intent"])
        return fast

    # LLM fallback for ambiguous cases
    prompt = _CLASSIFY_SYSTEM_PROMPT.format(schema=schema)
    try:
        resp = _client.chat.completions.create(
            model=GROQ_MODEL,
            messages=[
                {"role": "system", "content": prompt},
                {"role": "user", "content": question}
            ],
            temperature=0.0,
            response_format={"type": "json_object"},
            max_tokens=150,
        )
        return json.loads(resp.choices[0].message.content.strip())
    except Exception as e:
        logger.warning("Intent classification LLM failed: %s", str(e))
        q = question.lower()
        if any(w in q for w in ("insert", "update", "delete", "rename", "transform")):
            op = "update"
            if "delete" in q: op = "delete"
            if "insert" in q: op = "insert"
            if "rename" in q: op = "schema_rename"
            if "transform" in q: op = "transform"
            return {"intent": "edit", "details": {"operation_type": op}}
        return {"intent": "query", "details": {"operation_type": None}}


@api.route("/visualize/recommend", methods=["POST"])
def visualize_recommend():
    """Return AI chart recommendation for the last result without rendering a spec.
    Used by the frontend viz-picker to auto-select the best chart type.
    """
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400
    if "last_result" not in session:
        return jsonify({"error": "No results yet. Run a query first."}), 400

    body            = request.json or {}
    user_chart_type = body.get("chart_type")   # optional user override
    question        = body.get("question", "")

    try:
        df      = pd.read_json(io.StringIO(session["last_result"]), orient="split")
        profile = VisualizationProfileService().profile(df)
        rec     = ChartRecommender().recommend(
            df, profile,
            question=question,
            user_requested_chart=user_chart_type or None,
        )
        return jsonify(rec)
    except Exception as e:
        logger.exception("Recommendation failed: %s", str(e))
        return jsonify({"error": f"Recommendation failed: {str(e)}"}), 500


@api.route("/visualize/profile", methods=["POST"])
def visualize_profile():
    """Return column profile of the last result for axis selection."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    if "last_result" not in session:
        return jsonify({"error": "No results yet. Run a query first."}), 400

    try:
        df = pd.read_json(io.StringIO(session["last_result"]), orient="split")
        profile_service = VisualizationProfileService()
        profile = profile_service.profile(df)
        column_profile = {col: profile["columns"][col] for col in df.columns}
        return jsonify({
            "columns": list(df.columns),
            "columnProfile": column_profile,
            "total": len(df),
        })
    except Exception as e:
        logger.exception("Profile failed: %s", str(e))
        return jsonify({"error": f"Profile failed: {str(e)}"}), 500


@api.route("/visualize/render", methods=["POST"])
def visualize_render():
    """Render a chart spec from last result with explicit X/Y columns."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    if "last_result" not in session:
        return jsonify({"error": "No results yet. Run a query first."}), 400

    body = request.json or {}
    chart_type = body.get("type", "bar")
    x_column = body.get("xColumn")
    y_column = body.get("yColumn")

    try:
        df = pd.read_json(io.StringIO(session["last_result"]), orient="split")
        profile_service = VisualizationProfileService()
        prep_service = VisualizationPreparationService()
        profile = profile_service.profile(df)

        if x_column and x_column not in df.columns:
            x_column = df.columns[0]
        if y_column and y_column not in df.columns:
            y_column = None

        spec = prep_service.render_with_axes(
            df=df, chart_type=chart_type, profile=profile,
            x_column=x_column, y_column=y_column
        )
        return jsonify({"spec": spec})
    except Exception as e:
        logger.exception("Render failed: %s", str(e))
        return jsonify({"error": f"Render failed: {str(e)}"}), 500


@api.route("/download-excel", methods=["GET"])
def download_excel():
    """Legacy Excel download — kept for backwards compatibility."""
    return _download("xlsx")


@api.route("/download/<fmt>", methods=["GET"])
def download(fmt: str):
    """Export the last query result in the requested format."""
    return _download(fmt)


# ── Internal Helpers ───────────────────────────────────────────
_FORMATS = {
    "xlsx": ("query_result.xlsx",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "png":  ("query_result.png",  "image/png"),
    "jpg":  ("query_result.jpg",  "image/jpeg"),
    "pdf":  ("query_result.pdf",  "application/pdf"),
    "docx": ("query_result.docx",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
}


def _download(fmt: str):
    fmt = fmt.lower()
    if fmt not in _FORMATS:
        return jsonify({"error": f"Unsupported format '{fmt}'. Choose: xlsx, png, jpg, pdf, docx."}), 400

    if "last_result" not in session:
        return jsonify({"error": "No results to download. Run a query first."}), 400

    try:
        df = pd.read_json(io.StringIO(session["last_result"]), orient="split")

        if fmt == "xlsx":
            buffer = to_excel(df)
        elif fmt in ("png", "jpg"):
            buffer = to_image(df, fmt=fmt)
        elif fmt == "pdf":
            buffer = to_pdf(df)
        elif fmt == "docx":
            buffer = to_word(df)

        filename, mimetype = _FORMATS[fmt]
        logger.info("Download served — format: %s | rows: %d", fmt, len(df))
        return send_file(buffer, as_attachment=True,
                         download_name=filename, mimetype=mimetype)

    except Exception as e:
        logger.exception("Export failed: %s", str(e))
        return jsonify({"error": f"Export failed: {str(e)}"}), 500
