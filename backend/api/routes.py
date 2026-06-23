"""
API routes — all HTTP endpoints registered on a Flask Blueprint.
"""

import base64
import io
import json
import logging
import re
import threading

import pandas as pd
from flask import Blueprint, jsonify, request, send_file, session
from groq import Groq

from backend.config.settings import GROQ_API_KEY, GROQ_MODEL
from backend.services.export_service import (
    to_chart_excel, to_chart_pdf, to_chart_word, to_excel, to_image, to_pdf, to_word,
)
from backend.services.query_service import execute_sql, generate_sql
from backend.services.visualization_profile_service import VisualizationProfileService
from backend.services.visualization_preparation_service import VisualizationPreparationService

from backend.utils.db_utils import get_schema, load_dataframe
from backend.utils.file_utils import read_uploaded_file
from backend.utils.active_dataset_store import (
    load_dataframe_into_active_db, get_active_schema, active_dataset_exists, 
    get_active_connection, get_master_schema, get_master_schema_formatted
)
from backend.utils.dataset_cache import get_active_dataframe_and_profile
from backend.services.relevance_validator import RelevanceValidator, _normalize
from backend.services.insights.insights_engine import compute_dataset_overview
from backend.error_handler import safe_route, safe_get

logger = logging.getLogger("routes")
_relevance_validator = RelevanceValidator()
api = Blueprint("api", __name__)

_client = Groq(api_key=GROQ_API_KEY)


# ═══════════════════════════════════════════════════════════════
#  PER-CARD RESULT STORE
#  Thread-safe in-memory store mapping resultId → {columns, rows}
#  Results stored on each query, retrieved on export.
#  Max 200 results; oldest evicted when limit exceeded.
# ═══════════════════════════════════════════════════════════════

_RESULT_STORE = {}
_RESULT_STORE_LOCK = threading.Lock()
_MAX_RESULTS = 200


def _store_result(result_id: str, columns: list, rows: list) -> None:
    """Store result data keyed by resultId (thread-safe)."""
    with _RESULT_STORE_LOCK:
        _RESULT_STORE[result_id] = {"columns": columns, "rows": rows}
        # Evict oldest results when over capacity
        if len(_RESULT_STORE) > _MAX_RESULTS:
            keys = list(_RESULT_STORE.keys())
            for k in keys[:-100]:
                del _RESULT_STORE[k]


def _get_stored_result(result_id: str) -> dict | None:
    """Retrieve result data by resultId (thread-safe)."""
    with _RESULT_STORE_LOCK:
        return _RESULT_STORE.get(result_id)


# ── Export format definitions ────────────────────────────────────
_EXPORT_FORMATS = {
    "csv":  ("query_result.csv",  "text/csv"),
    "json": ("query_result.json", "application/json"),
    "xlsx": ("query_result.xlsx",
             "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    "pdf":  ("query_result.pdf",  "application/pdf"),
    "docx": ("query_result.docx",
             "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "png":  ("query_result.png",  "image/png"),
    "jpg":  ("query_result.jpg",  "image/jpeg"),
}


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

Classify the user's input into one of these 2 intents:
1. "query" - The user is asking a question about the data, requesting a calculation, filtering, summarizing, or querying the dataset, including cases where they request a chart or visualization.
2. "schema" - The user wants to inspect the columns, schema, datatypes, metadata, or description of the dataset (e.g. "show columns", "describe dataset", "what are the columns").

Return ONLY a JSON object with:
{{
  "intent": "query" | "schema",
  "explanation": "Short sentence explaining why",
  "details": {{}}
}}

Use the following ACTIVE SCHEMA:
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


def generate_schema_description() -> str:
    """Generate a markdown description of the dataset schema."""
    conn = get_active_connection()
    try:
        cur = conn.cursor()
        cols = cur.execute("PRAGMA table_info(dataset)").fetchall()
        total_rows = cur.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]

        md = "### Dataset Schema Summary\n"
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

        md = "## Data Quality & Health Report\n\n"
        md += f"- **Total Rows**: {total_rows}\n"
        md += f"- **Duplicate Records (Groups)**: {dupes_count} row groups are duplicated.\n\n"

        md += "### Column Missing / Empty Values Analysis\n\n"
        md += "| Column Name | Nulls | Empty Strings | Total Missing | Missing % |\n"
        md += "| :--- | :---: | :---: | :---: | :---: |\n"
        for item in missing_report:
            pct = round((item["total_missing"] / total_rows) * 100, 2) if total_rows > 0 else 0
            md += f"| `{item['column']}` | {item['nulls']} | {item['blanks']} | **{item['total_missing']}** | {pct}% |\n"

        md += "\n> [!TIP]\n"
        md += "> - This report provides a read-only view of your dataset quality.\n"

        return md
    finally:
        conn.close()


def _parse_user_chart_type(question: str) -> str | None:
    """Extract explicitly requested chart type from the question string."""
    q = question.lower()
    mapping = [
        ("column",    "column"),
        ("bar",       "bar"),
        ("line",      "line"),
        ("pie",       "pie"),
        ("doughnut",  "pie"),
        ("donut",     "pie"),
        ("scatter",   "scatter"),
    ]
    for keyword, chart in mapping:
        if keyword in q:
            return chart
    return None


# auto_generate_visualization removed


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


@api.route("/dataset-overview", methods=["GET"])
def dataset_overview_endpoint():
    """Return the enhanced Dataset Overview for the active dataset."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    overview = compute_dataset_overview()
    if not overview.get("success"):
        return jsonify({"error": overview.get("error", "Failed to compute overview.")}), 500

    return jsonify(overview)


def _overview_export_dataframe(overview: dict) -> pd.DataFrame:
    """Flatten overview sections into the table shape used by existing exporters."""
    rows = [
        ("Dataset Summary", "Total Records", overview["total_records"]),
        ("Dataset Summary", "Total Rows", overview["total_rows"]),
        ("Dataset Summary", "Total Columns", overview["total_columns"]),
        ("Dataset Summary", "Dataset Size", overview["dataset_size"]),
        ("Column Distribution", "Numeric Columns", overview["column_types"]["numeric"]),
        ("Column Distribution", "Categorical Columns", overview["column_types"]["categorical"]),
        ("Column Distribution", "Date/Time Columns", overview["column_types"]["date"]),
        ("Column Distribution", "Boolean Columns", overview["column_types"]["boolean"]),
        ("Data Quality", "Total Missing Values", overview["data_quality"]["total_missing_values"]),
        ("Data Quality", "Missing Value Percentage", f'{overview["data_quality"]["missing_percentage"]}%'),
        ("Data Quality", "Duplicate Record Count", overview["data_quality"]["duplicate_records"]),
        ("Data Quality", "Empty Columns", overview["data_quality"]["empty_columns"]),
        ("Data Quality", "Data Consistency", f'{overview["data_quality"]["consistency_percentage"]}%'),
        ("Key Columns", "Primary Identifier", overview["key_fields"]["primary_id"] or "Not detected"),
        ("Key Columns", "Date Column", overview["key_fields"]["date_column"] or "Not detected"),
        ("Key Columns", "Main Measures", ", ".join(overview["key_fields"]["measure_columns"]) or "Not detected"),
    ]
    rows.extend(
        (
            "Schema Summary",
            item["column_name"],
            f'{item["sqlite_type"]} | Samples: {", ".join(item["sample_values"]) or "None"}',
        )
        for item in overview["schema_details"]
    )
    return pd.DataFrame(rows, columns=["Section", "Metric / Column", "Value"])


@api.route("/dataset-overview/download/<fmt>", methods=["GET"])
def download_dataset_overview(fmt: str):
    """Export Dataset Overview through the existing export service."""
    fmt = fmt.lower()
    if fmt not in _EXPORT_FORMATS:
        return jsonify({"error": f"Unsupported format '{fmt}'."}), 400

    overview = compute_dataset_overview()
    if not overview.get("success"):
        return jsonify({"error": overview.get("error", "Failed to compute overview.")}), 400

    try:
        report = _overview_export_dataframe(overview)
        if fmt == "xlsx":
            buffer = to_excel(report)
        elif fmt in ("png", "jpg"):
            buffer = to_image(report, fmt=fmt)
        elif fmt == "pdf":
            buffer = to_pdf(report, title="Dataset Overview")
        else:
            buffer = to_word(report, title="Dataset Overview")

        _, mimetype = _EXPORT_FORMATS[fmt]
        return send_file(
            buffer,
            as_attachment=True,
            download_name=f"dataset_overview.{fmt}",
            mimetype=mimetype,
        )
    except Exception as exc:
        logger.exception("Dataset overview export failed: %s", exc)
        return jsonify({"error": f"Export failed: {exc}"}), 500


@api.route("/insights", methods=["GET"])
def get_insights():
    """Return structured executive AI insights for the active dataset."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    try:
        from backend.services.insights.analytical_engine import generate_analytical_insights
        payload = generate_analytical_insights()
        if not payload.get("success", True):
            return jsonify({"error": payload.get("error", "Failed to generate insights.")}), 500
        return jsonify(payload)
    except Exception as exc:
        logger.exception("AI insights generation failed: %s", exc)
        return jsonify({"error": f"Failed to generate insights: {exc}"}), 500


@api.route("/upload", methods=["POST"])
def upload():
    """Validate and store an uploaded CSV file."""

    df, error = read_uploaded_file(request.files.get("file"))

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

    # Build preview rows (first 50 rows) for frontend chart builder
    PREVIEW_LIMIT = 50
    preview_rows = _clean_rows(df.head(PREVIEW_LIMIT).to_dict(orient="records"))
    preview_row_count = len(preview_rows)
    preview_truncated = len(df) > PREVIEW_LIMIT

    return jsonify({
        "message": f"'{filename}' uploaded successfully.",
        "rows":    len(df),
        "columns": list(df.columns),
        "schema":  master_schema,
        "preview_rows": preview_rows,
        "preview_row_count": preview_row_count,
        "preview_truncated": preview_truncated,
    })


@api.route("/query", methods=["POST"])
def query():
    """Unified conversational entry point."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset. Please upload a CSV file first."}), 400

    body = request.json or {}
    question = body.get("question", "").strip()
    result_id = body.get("resultId", "")

    if not question:
        return jsonify({"error": "Please enter a question."}), 400

    question_lower = question.lower()

    # Get active schema & connection
    schema = get_active_schema()
    conn = get_active_connection()

    try:
        # ── 1. Route Data Quality/Insights manually if detected ─────────
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

        # ── 2. Classify intent via LLM ─────────────────────────────────
        classification = classify_intent(question, schema)
        intent = classification.get("intent", "query")
        details = classification.get("details") or {}

        # intent 'visualization' removed

        # ── 4. Process schema intent ───────────────────────────────────
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

        # ── 5. Relevance validation before SQL generation ──────────────
        rel = _relevance_validator.validate(question=question, schema=schema)
        if not rel.relevant:
            return jsonify({
                "type":        "irrelevant",
                "message":     rel.reason,
                "suggestions": rel.suggestions,
            })

        # ── 6. Process query / analysis intent ─────────────────────────
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

        # ── 7. Store result in per-card store for export ───────────────
        columns_list = list(result.columns)
        rows_list = _clean_rows(result.to_dict(orient="records"))
        if result_id:
            _store_result(result_id, columns_list, rows_list)

        return jsonify({
            "type": "query",
            "columns": columns_list,
            "rows": rows_list,
            "total": len(result),
            "resultId": result_id,
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
    q = _normalize(question)

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
        return {"intent": "query", "details": {"operation_type": None}}

    # ── Schema / describe keywords ────────────────────────────
    schema_words = ("show columns", "list columns", "describe", "what columns",
                    "column names", "data types", "schema", "metadata",
                    "what are the columns", "show schema")
    if any(w in q for w in schema_words):
        return {"intent": "schema", "details": {"operation_type": None}}

    # ── Pure query keywords (high confidence) ──
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
        return {"intent": "query", "details": {"operation_type": None}}



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


@api.route("/visualize/custom-render", methods=["POST"])
def visualize_custom_render():
    """Render a chart spec from the full dataset with aggregation pipeline.
    
    Supports all 5 chart types: column, bar, line, pie, scatter.
    Validates all inputs before rendering.
    """
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset. Please upload a dataset first."}), 400

    body = request.json or {}
    chart_type = (body.get("chart_type", "") or "").strip().lower()
    x_column = (body.get("xColumn", "") or "").strip()
    y_column = (body.get("yColumn", "") or "").strip()
    aggregation = (body.get("aggregation", "") or "").strip().lower()

    # ── Validate chart type ──
    valid_chart_types = {"column", "bar", "line", "pie", "scatter"}
    if not chart_type:
        return jsonify({"error": "Chart type is required. Please select a chart type from: Column, Bar, Line, Pie, or Scatter."}), 400
    if chart_type not in valid_chart_types:
        return jsonify({"error": f"Unsupported chart type '{chart_type}'. Choose: Column, Bar, Line, Pie, or Scatter."}), 400

    # ── Validate aggregation ──
    valid_aggs = {"sum", "avg", "count", "max", "min"}
    if not aggregation:
        return jsonify({"error": "Aggregation type is required. Choose: Sum, Average, Count, Maximum, or Minimum."}), 400
    if aggregation not in valid_aggs:
        return jsonify({"error": f"Unsupported aggregation '{aggregation}'. Choose: Sum, Average, Count, Maximum, or Minimum."}), 400

    try:
        df, profile = get_active_dataframe_and_profile()

        if df.empty:
            return jsonify({"error": "The dataset is empty. Please upload a valid dataset with data."}), 400

        dataset_rows = len(df)
        prep_service = VisualizationPreparationService()
        cols = list(df.columns)

        # ── Validate columns exist ──
        if x_column and x_column not in cols:
            return jsonify({"error": f"X-Axis column '{x_column}' not found in the dataset. Available columns: {', '.join(cols)}"}), 400
        if y_column and y_column not in cols:
            return jsonify({"error": f"Y-Axis column '{y_column}' not found in the dataset. Available columns: {', '.join(cols)}"}), 400

        # ── Validate required columns per chart type ──
        if not x_column:
            return jsonify({"error": "Please select an X-Axis column (Category/Label)."}), 400

        if chart_type != "pie" and not y_column:
            return jsonify({"error": f"{chart_type.capitalize()} Chart requires both X-Axis and Y-Axis columns. Please select a Y-Axis column."}), 400

        if chart_type != "pie" and x_column == y_column:
            return jsonify({"error": "X-Axis and Y-Axis must be different columns. They cannot be the same."}), 400

        # For scatter, ensure both columns have numeric data
        if chart_type == "scatter":
            num_profile_cols = [c for c, p in profile.get("columns", {}).items() if p.get("kind") == "numeric"]
            if x_column not in num_profile_cols:
                # Try to coerce and check
                pass  # Let the service handle it with a clear error

        spec = prep_service.render_with_axes(
            df=df, chart_type=chart_type, profile=profile,
            x_column=x_column, y_column=y_column,
            aggregation=aggregation,
        )

        professional_insights = _build_professional_insights(
            spec, df, chart_type, x_column, y_column, aggregation, dataset_rows
        )

        return jsonify({
            "spec": spec,
            "insights": professional_insights,
            "columns": cols,
            "total": len(df),
        })
    except ValueError as ve:
        # Catch validation errors from the preparation service
        logger.warning("Custom render validation error: %s", str(ve))
        return jsonify({"error": str(ve)}), 400
    except Exception as e:
        logger.exception("Custom render failed: %s", str(e))
        return jsonify({"error": f"Chart generation failed: {str(e)}"}), 500


def _build_professional_insights(spec, df, chart_type, x_col, y_col, agg, total_rows):
    """Build professional-grade chart insights with summary, trends, and recommendations."""
    insights = []
    try:
        data_values = []
        labels = []
        if spec.get("series") and spec["series"][0]:
            data_values = spec["series"][0].get("data", [])
            labels = spec["series"][0].get("labels", spec.get("labels", []))

        if not data_values:
            return ["Chart Summary: No data available for analysis."]

        if chart_type == "scatter":
            return _build_scatter_insights(data_values, x_col, y_col, total_rows)

        values = [float(v) for v in data_values if v is not None]
        if not values:
            return ["Chart Summary: No numeric values to analyze."]

        max_val = max(values)
        min_val = min(values)
        sum_val = sum(values)
        avg_val = sum_val / len(values)

        max_idx = values.index(max_val)
        min_idx = values.index(min_val)
        max_label = labels[max_idx] if max_idx < len(labels) else "—"
        min_label = labels[min_idx] if min_idx < len(labels) else "—"

        chart_labels = {
            "column": "Column Chart",
            "bar": "Bar Chart",
            "line": "Line Chart",
            "pie": "Pie Chart",
            "scatter": "Scatter Plot"
        }
        chart_name = chart_labels.get(chart_type, chart_type.upper())
        insights.append(f"Summary: {chart_name} showing {agg.upper()}({y_col or 'Count'}) by {x_col}. "
                       f"Analyzing {len(values):,} data points from {total_rows:,} total rows.")

        if max_val == min_val and len(values) >= 2:
            insights.append(f"Distribution: All {len(values)} categories have the same value "
                           f"({_fmt_value(max_val)})")
        else:
            if max_label and max_val > 0:
                if sum_val > 0:
                    pct = round(100 * max_val / sum_val, 1)
                    insights.append(f"Highest: {max_label} with {_fmt_value(max_val)} ({pct}% of total)")
                else:
                    insights.append(f"Highest: {max_label} ({_fmt_value(max_val)})")

            if min_label:
                insights.append(f"Lowest: {min_label} ({_fmt_value(min_val)})")

        if chart_type in ("column", "bar", "pie") and sum_val > 0 and len(values) >= 3:
            sorted_vals = sorted(values, reverse=True)
            top3_sum = sum(sorted_vals[:3])
            top3_pct = round(100 * top3_sum / sum_val, 1)
            others_pct = round(100 - top3_pct, 1)
            insights.append(f"Concentration: Top 3 categories contribute **{top3_pct}%** "
                           f"of total (others: {others_pct}%)")
            if max_val > 0 and min_val > 0:
                ratio = round(max_val / min_val, 1) if min_val > 0 else float('inf')
                if ratio > 10:
                    insights.append(f"Variance: Large variance detected — highest is {ratio}x the lowest")

        if chart_type == "line" and len(values) >= 3:
            first_half = sum(values[:len(values)//2]) / max(len(values[:len(values)//2]), 1)
            second_half = sum(values[len(values)//2:]) / max(len(values[len(values)//2:]), 1)
            if second_half > first_half * 1.05:
                change = round(100 * (second_half - first_half) / max(first_half, 0.001), 1)
                insights.append(f"Trend: Upward trend — values increased by ~{change}%")
            elif first_half > second_half * 1.05:
                change = round(100 * (first_half - second_half) / max(first_half, 0.001), 1)
                insights.append(f"Trend: Downward trend — values decreased by ~{change}%")
            else:
                insights.append(f"Trend: Relatively stable over the period")

        insights.append(f"Average: {_fmt_value(avg_val)} across {len(values)} categories")
        insights.append(f"Total: {_fmt_value(sum_val)}")

        if chart_type == "pie" and len(values) >= 3:
            top_pct = round(100 * max_val / sum_val, 1)
            if top_pct > 50:
                insights.append(f"Dominance: '{max_label}' alone accounts for {top_pct}% — "
                               f"consider a Bar Chart for better comparison")
            elif top_pct < 10 and len(values) > 5:
                insights.append(f"Distribution: Values are relatively evenly distributed")

        if chart_type == "pie" and len(labels) > 8:
            insights.append(f"Recommendation: Pie chart has {len(labels)} slices — consider Column or Bar Chart for clarity")
        elif chart_type in ("column", "bar") and len(labels) > 25:
            insights.append(f"Recommendation: {len(labels)} categories may be crowded — consider a different layout for clarity")
        elif chart_type == "line" and x_col:
            insights.append(f"Recommendation: Use this trend to identify seasonal patterns or anomalies in {x_col}")
        else:
            insights.append(f"Recommendation: Use aggregation and axis selection to focus on the most impactful categories")

        return insights[:10]

    except Exception:
        return ["Chart Summary: Analysis completed on the selected data."]


def _build_scatter_insights(points, x_col, y_col, total_rows):
    """Build insights for scatter plots, whose data points are {x, y} dicts."""
    try:
        xs = [float(p["x"]) for p in points if p and p.get("x") is not None and p.get("y") is not None]
        ys = [float(p["y"]) for p in points if p and p.get("x") is not None and p.get("y") is not None]
        if not xs:
            return ["Chart Summary: No numeric values to analyze."]

        insights = [
            f"Summary: Scatter Plot showing {y_col} vs {x_col}. "
            f"Analyzing {len(xs):,} data points from {total_rows:,} total rows.",
            f"{x_col} range: {_fmt_value(min(xs))} to {_fmt_value(max(xs))} "
            f"(mean: {_fmt_value(sum(xs) / len(xs))})",
            f"{y_col} range: {_fmt_value(min(ys))} to {_fmt_value(max(ys))} "
            f"(mean: {_fmt_value(sum(ys) / len(ys))})",
        ]

        if len(xs) >= 5:
            corr = pd.Series(xs).corr(pd.Series(ys))
            if pd.notna(corr):
                direction = "positive" if corr > 0 else "negative"
                strength = "strong" if abs(corr) > 0.7 else "moderate" if abs(corr) > 0.3 else "weak"
                insights.append(f"Correlation: {strength.capitalize()} {direction} correlation "
                                f"(r={corr:.2f}) between {x_col} and {y_col}")

        insights.append("Recommendation: Add a trend line to quantify the correlation strength")
        return insights[:10]
    except Exception:
        return ["Chart Summary: Analysis completed on the selected data."]


def _fmt_value(v):
    """Format values for display in insights."""
    try:
        fv = float(v)
        if abs(fv) >= 1_000_000:
            return f"{fv / 1_000_000:.2f}M"
        if abs(fv) >= 1_000:
            return f"{fv / 1_000:.1f}K"
        if fv == int(fv):
            return f"{int(fv):,}"
        return f"{fv:.2f}"
    except:
        return str(v)


@api.route("/download-excel", methods=["GET"])
def download_excel():
    """Legacy Excel download — kept for backwards compatibility."""
    return _download("xlsx")


# ── NEW EXPORT API (Phase 3) ─────────────────────────────────
# POST /api/export-result
# Receives { resultId, format }
# Looks up result data from _RESULT_STORE, generates file, returns download
# ─────────────────────────────────────────────────────────────
@api.route("/api/export-result", methods=["POST"])
def export_result():
    """
    Export per-card result data by resultId.
    Request: { "resultId": "msg-xxx", "format": "csv" }
    Response: File download with proper Content-Type and Content-Disposition
    """
    body = request.get_json(silent=True) or {}
    result_id = body.get("resultId", "").strip()
    fmt = body.get("format", "").strip().lower()

    # ── Validate inputs ──────────────────────────────────────
    if not result_id:
        return jsonify({"error": "Missing resultId. Each export must specify a resultId."}), 400

    if not fmt:
        return jsonify({"error": "Missing format. Choose: csv, xlsx, pdf, docx, json."}), 400

    if fmt not in _EXPORT_FORMATS:
        return jsonify({"error": f"Unsupported format '{fmt}'. Supported: csv, xlsx, pdf, docx, json."}), 400

    # ── Look up result data ──────────────────────────────────
    result = _get_stored_result(result_id)

    if not result:
        logger.warning("Export failed: resultId '%s' not found in store", result_id)
        return jsonify({"error": f"Export data not found for resultId: {result_id}. The result may have expired or the query hasn't completed yet."}), 404

    columns = result.get("columns")
    rows = result.get("rows")

    if not columns or rows is None:
        return jsonify({"error": "No data available for this result (empty columns/rows)."}), 404

    # ── Build DataFrame ──────────────────────────────────────
    try:
        df = pd.DataFrame(rows, columns=columns)
    except Exception as e:
        logger.exception("Failed to build DataFrame from result data: %s", str(e))
        return jsonify({"error": f"Invalid result data: {str(e)}"}), 500

    if df.empty:
        return jsonify({"error": "Result data is empty. Nothing to export."}), 400

    # ── Generate file ────────────────────────────────────────
    try:
        fmt_info = _EXPORT_FORMATS[fmt]

        if fmt == "csv":
            from backend.services.export_service import to_csv
            buffer = to_csv(df)
        elif fmt == "json":
            from backend.services.export_service import to_json
            buffer = to_json(df)
        elif fmt == "xlsx":
            from backend.services.export_service import to_excel
            buffer = to_excel(df)
        elif fmt == "pdf":
            from backend.services.export_service import to_pdf
            buffer = to_pdf(df)
        elif fmt == "docx":
            from backend.services.export_service import to_word
            buffer = to_word(df)

        filename, mimetype = fmt_info
        logger.info(
            "Export succeeded — resultId: %s | format: %s | rows: %d | cols: %d",
            result_id, fmt, len(df), len(columns),
        )
        return send_file(
            buffer,
            as_attachment=True,
            download_name=filename,
            mimetype=mimetype,
        )

    except Exception as e:
        logger.exception("Export generation failed for resultId '%s' format '%s': %s", result_id, fmt, str(e))
        return jsonify({"error": f"Export generation failed: {str(e)}"}), 500


# ── LEGACY EXPORT ENDPOINT (kept for backward compatibility) ──
@api.route("/export/<fmt>", methods=["POST"])
def export_per_card(fmt: str):
    """Export per-card query result data (columns + rows) in the requested format.
    This endpoint receives the exact data from a specific result card,
    eliminating the global state dependency bug.

    DEPRECATED: Use POST /api/export-result with { resultId, format } instead.
    """
    fmt = fmt.lower()
    if fmt not in _EXPORT_FORMATS:
        return jsonify({"error": f"Unsupported format '{fmt}'."}), 400

    body = request.get_json(silent=True) or {}
    columns = body.get("columns")
    rows = body.get("rows")

    if not columns or rows is None:
        return jsonify({"error": "Missing 'columns' or 'rows' in request body."}), 400

    try:
        df = pd.DataFrame(rows, columns=columns)
    except Exception as e:
        return jsonify({"error": f"Invalid data: {str(e)}"}), 400

    try:
        fmt_info = _EXPORT_FORMATS[fmt]
        if fmt == "csv":
            from backend.services.export_service import to_csv
            buffer = to_csv(df)
        elif fmt == "json":
            from backend.services.export_service import to_json
            buffer = to_json(df)
        elif fmt == "xlsx":
            from backend.services.export_service import to_excel
            buffer = to_excel(df)
        elif fmt == "pdf":
            from backend.services.export_service import to_pdf
            buffer = to_pdf(df)
        elif fmt == "docx":
            from backend.services.export_service import to_word
            buffer = to_word(df)

        filename, mimetype = fmt_info
        logger.info("Per-card export served (legacy) — format: %s | rows: %d | cols: %d", fmt, len(df), len(columns))
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype=mimetype)

    except Exception as e:
        logger.exception("Per-card export failed: %s", str(e))
        return jsonify({"error": f"Export failed: {str(e)}"}), 500


@api.route("/download/<fmt>", methods=["GET"])
def download(fmt: str):
    """Export the last query result in the requested format."""
    return _download(fmt)


_CHART_EXPORT_FORMATS = {
    "pdf":  ("chart.pdf",  "application/pdf"),
    "docx": ("chart.docx", "application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    "xlsx": ("chart.xlsx", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
}


@api.route("/visualize/export-chart/<fmt>", methods=["POST"])
def export_chart(fmt: str):
    """Export a rendered chart (image + insights + underlying data) as PDF, Word or Excel."""
    fmt = fmt.lower()
    if fmt not in _CHART_EXPORT_FORMATS:
        return jsonify({"error": f"Unsupported chart export format '{fmt}'. Choose: pdf, docx, xlsx."}), 400

    body = request.get_json(silent=True) or {}
    title        = (body.get("title") or "Chart").strip()
    x_label      = body.get("x_label") or ""
    y_label      = body.get("y_label") or ""
    series_label = body.get("series_label") or ""
    labels       = body.get("labels") or []
    data         = body.get("data") or []
    insights     = body.get("insights") or []
    image_data   = body.get("image") or ""

    if "," not in image_data or not image_data.startswith("data:image"):
        return jsonify({"error": "A chart image is required to export."}), 400

    try:
        image_bytes = base64.b64decode(image_data.split(",", 1)[1])
    except (ValueError, TypeError):
        return jsonify({"error": "Invalid chart image data."}), 400

    try:
        if fmt == "pdf":
            buffer = to_chart_pdf(title, image_bytes, x_label, y_label, labels, data, series_label, insights)
        elif fmt == "docx":
            buffer = to_chart_word(title, image_bytes, x_label, y_label, labels, data, series_label, insights)
        else:
            buffer = to_chart_excel(title, image_bytes, x_label, y_label, labels, data, series_label, insights)

        filename, mimetype = _CHART_EXPORT_FORMATS[fmt]
        logger.info("Chart export served — format: %s | title: %s", fmt, title)
        return send_file(buffer, as_attachment=True, download_name=filename, mimetype=mimetype)
    except Exception as e:
        logger.exception("Chart export failed: %s", str(e))
        return jsonify({"error": f"Chart export failed: {str(e)}"}), 500


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


# ═══════════════════════════════════════════════════════════════
#  REPLACE NULL OR EMPTY VALUES — API endpoints
# ═══════════════════════════════════════════════════════════════

def _is_missing(val) -> bool:
    """Check if a value is missing (NULL, empty string, NaN, undefined)."""
    import math
    if val is None:
        return True
    if isinstance(val, float) and math.isnan(val):
        return True
    if isinstance(val, str) and val.strip() == '':
        return True
    if val == 'undefined' or val == 'None' or val == 'nan':
        return True
    return False


def _compute_missing_stats(conn) -> dict:
    """Compute missing value stats for all columns."""
    import math
    cur = conn.cursor()
    cols_info = cur.execute("PRAGMA table_info(dataset)").fetchall()
    col_names = [r[1] for r in cols_info]
    total_rows = cur.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]

    missing_columns = []
    total_missing = 0
    master_schema = get_master_schema() or {}

    for col in cols_info:
        col_name = col[1]
        col_type = col[2].upper() if col[2] else 'TEXT'

        # Count missing values
        try:
            missing_count = cur.execute(
                f'SELECT COUNT(*) FROM dataset WHERE "{col_name}" IS NULL '
                f'OR TRIM(CAST("{col_name}" AS TEXT)) = \'\' '
                f'OR CAST("{col_name}" AS TEXT) = \'nan\' '
                f'OR CAST("{col_name}" AS TEXT) = \'undefined\''
            ).fetchone()[0]
        except Exception:
            missing_count = 0

        if missing_count > 0:
            total_missing += missing_count
            master_type = master_schema.get(col_name, 'TEXT')
            # Determine display type
            if master_type == 'NUM':
                display_type = 'Numeric'
            elif master_type == 'DATE':
                display_type = 'Date'
            else:
                display_type = 'Categorical'

            missing_columns.append({
                "column_name": col_name,
                "data_type": display_type,
                "missing_count": missing_count,
                "total_rows": total_rows,
            })

    return {
        "missing_columns": missing_columns,
        "total_missing": total_missing,
        "total_rows": total_rows,
    }


def _get_column_detail(conn, col_name: str) -> dict:
    """Get detailed info about a specific column including values preview."""
    cur = conn.cursor()
    col_info = cur.execute(f"PRAGMA table_info(dataset)").fetchall()
    total_rows = cur.execute("SELECT COUNT(*) FROM dataset").fetchone()[0]
    master_schema = get_master_schema() or {}

    # Get all values for the column
    rows = cur.execute(f'SELECT "{col_name}" FROM dataset').fetchall()
    values = [r[0] for r in rows]

    # Get existing (non-missing) values
    existing_values = []
    missing_indices = []
    for idx, val in enumerate(values):
        if _is_missing(val):
            missing_indices.append(idx)
        else:
            existing_values.append(val)

    # Compute stats for numeric columns
    master_type = master_schema.get(col_name, 'TEXT')
    is_numeric = master_type == 'NUM'

    stats = {}
    if is_numeric:
        numeric_vals = []
        for v in existing_values:
            try:
                numeric_vals.append(float(v))
            except (ValueError, TypeError):
                pass
        if numeric_vals:
            import statistics
            stats['mean'] = round(statistics.mean(numeric_vals), 2)
            stats['median'] = round(statistics.median(numeric_vals), 2)
            try:
                mode_val = statistics.mode(numeric_vals)
                stats['mode'] = round(float(mode_val), 2)
            except statistics.StatisticsError:
                stats['mode'] = None
    else:
        # Mode for categorical
        from collections import Counter
        counter = Counter(existing_values)
        if counter:
            stats['mode'] = str(counter.most_common(1)[0][0])

    # Build preview of values (up to 100)
    preview_values = []
    for val in values[:100]:
        if _is_missing(val):
            preview_values.append({"value": None, "is_missing": True})
        else:
            preview_values.append({"value": str(val), "is_missing": False})

    # Determine display type
    if master_type == 'NUM':
        display_type = 'Numeric'
    elif master_type == 'DATE':
        display_type = 'Date'
    else:
        display_type = 'Categorical'

    return {
        "column_name": col_name,
        "data_type": display_type,
        "total_rows": total_rows,
        "missing_count": len(missing_indices),
        "missing_indices": missing_indices,  # Row indices of missing values
        "preview_values": preview_values,
        "stats": stats,
    }


@api.route("/missing-values", methods=["GET"])
def get_missing_values():
    """Return all columns with missing values and total counts."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    conn = get_active_connection()
    try:
        stats = _compute_missing_stats(conn)
        return jsonify({
            "success": True,
            "missing_columns": stats["missing_columns"],
            "total_missing": stats["total_missing"],
            "total_rows": stats["total_rows"],
        })
    except Exception as e:
        logger.exception("Failed to compute missing values: %s", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@api.route("/missing-values/<column>", methods=["GET"])
def get_missing_column_detail(column):
    """Return detailed info about a specific column's missing values."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    conn = get_active_connection()
    try:
        detail = _get_column_detail(conn, column)
        return jsonify({
            "success": True,
            **detail,
        })
    except Exception as e:
        logger.exception("Failed to get column detail: %s", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@api.route("/missing-values/replace", methods=["POST"])
def replace_missing_values():
    """Replace missing values in a column and return a preview or apply changes."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    body = request.json or {}
    column = body.get("column", "")
    method = body.get("method", "custom")
    custom_value = body.get("value")
    preview_only = body.get("preview", True)

    if not column:
        return jsonify({"error": "Column name is required."}), 400

    conn = get_active_connection()
    try:
        cur = conn.cursor()
        detail = _get_column_detail(conn, column)
        missing_indices = detail["missing_indices"]

        if not missing_indices:
            return jsonify({"success": True, "message": "No missing values found in this column.", "affected_rows": 0})

        # Determine replacement value
        replacement = None
        if method == "null":
            replacement = None
        elif method in ("mean", "median", "mode"):
            stats = detail["stats"]
            replacement = stats.get(method)
            if replacement is None:
                return jsonify({"error": f"Cannot compute {method} for this column."}), 400
        else:  # custom
            if custom_value is None or (isinstance(custom_value, str) and custom_value.strip() == ''):
                return jsonify({"error": "Replacement value cannot be empty."}), 400
            replacement = custom_value

        # Get old values for preview
        all_rows = cur.execute(f'SELECT "{column}" FROM dataset').fetchall()
        old_values = [all_rows[i][0] for i in missing_indices]
        preview_data = [
            {"old": str(v) if v is not None else '[EMPTY]', "new": str(replacement) if replacement is not None else 'NULL'}
            for v in old_values
        ]

        if preview_only:
            return jsonify({
                "success": True,
                "preview": True,
                "column": column,
                "method": method,
                "replacement": str(replacement) if replacement is not None else None,
                "affected_rows": len(missing_indices),
                "preview_data": preview_data[:50],  # Limit preview to 50 rows
            })

        # Apply changes
        # Save a backup of the column for undo
        backup_key = f"rm_backup_{column}"
        if backup_key not in session:
            session[backup_key] = old_values
            session.modified = True
            session["rm_can_undo"] = True
            session.modified = True

        if replacement is None:
            cur.execute(f'UPDATE dataset SET "{column}" = NULL WHERE rowid IN ({",".join(str(i+1) for i in missing_indices)})')
        else:
            cur.execute(f'UPDATE dataset SET "{column}" = ? WHERE rowid IN ({",".join(str(i+1) for i in missing_indices)})', (replacement,))

        conn.commit()
        logger.info("Replaced %d missing values in column '%s' with method=%s value=%s",
                     len(missing_indices), column, method, replacement)

        # Recompute missing stats after replacement
        updated_stats = _compute_missing_stats(conn)

        return jsonify({
            "success": True,
            "preview": False,
            "column": column,
            "method": method,
            "replacement": str(replacement) if replacement is not None else None,
            "affected_rows": len(missing_indices),
            "message": f"{len(missing_indices)} missing values in {column} were successfully replaced.",
            "updated_missing": updated_stats,
        })

    except Exception as e:
        logger.exception("Failed to replace missing values: %s", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@api.route("/missing-values/undo", methods=["POST"])
def undo_replace_missing_values():
    """Undo the last replacement operation."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    body = request.json or {}
    column = body.get("column", "")
    backup_key = f"rm_backup_{column}"

    if backup_key not in session:
        return jsonify({"error": "No backup found for this column. Cannot undo."}), 400

    backup_values = session[backup_key]
    # Delete the backup key
    del session[backup_key]
    session.modified = True

    conn = get_active_connection()
    try:
        cur = conn.cursor()

        # Get the row IDs of where the missing values were
        all_rows = cur.execute(f'SELECT rowid, "{column}" FROM dataset').fetchall()
        missing_indices = []
        for i, val in enumerate(all_rows):
            v = val[1]
            if v is None or (isinstance(v, float) and str(v) == 'nan') or (isinstance(v, str) and v.strip() == ''):
                continue
            # Check if this was a previously replaced value by comparing against current values
            # We use the backup length as the indicator
            pass

        # Restore backup: update the rows that were previously modified
        # We identify them by finding rows where the current value matches the replacement
        # and restoring them one by one. A simpler approach: use the row IDs stored.
        # For simplicity, restore by finding rows with the replacement value that were in missing positions.
        # Better: use a transaction-based approach with a tracking table.

        # Simple approach: restore from backup indices stored in session
        indices_key = f"rm_backup_indices_{column}"
        if indices_key in session:
            indices = session[indices_key]
            for idx, val in zip(indices, backup_values):
                rowid = idx + 1
                if val is None:
                    cur.execute(f'UPDATE dataset SET "{column}" = NULL WHERE rowid = ?', (rowid,))
                else:
                    cur.execute(f'UPDATE dataset SET "{column}" = ? WHERE rowid = ?', (val, rowid))
            del session[indices_key]
        else:
            # Fallback: restore all values
            for idx, val in enumerate(backup_values):
                if val is None:
                    cur.execute(f'UPDATE dataset SET "{column}" = NULL WHERE rowid = ?', (idx + 1,))
                else:
                    cur.execute(f'UPDATE dataset SET "{column}" = ? WHERE rowid = ?', (val, idx + 1))

        conn.commit()

        # Update undo state
        remaining_backups = [k for k in session.keys() if k.startswith("rm_backup_")]
        if not remaining_backups:
            session["rm_can_undo"] = False
        session.modified = True

        # Recompute stats
        updated_stats = _compute_missing_stats(conn)

        return jsonify({
            "success": True,
            "message": f"Undo successful. Restored {len(backup_values)} values in {column}.",
            "updated_missing": updated_stats,
        })

    except Exception as e:
        logger.exception("Failed to undo: %s", str(e))
        return jsonify({"error": str(e)}), 500
    finally:
        conn.close()


@api.route("/export-cleaned-dataset/<fmt>", methods=["GET"])
def export_cleaned_dataset(fmt):
    """Export the cleaned dataset after replacing missing values."""
    if not active_dataset_exists():
        return jsonify({"error": "No active dataset."}), 400

    if fmt not in ('xlsx', 'csv', 'pdf', 'docx', 'json'):
        return jsonify({"error": f"Unsupported format '{fmt}'. Choose: xlsx, csv, pdf, docx, json."}), 400

    try:
        from backend.services.export_service import to_excel, to_pdf, to_word
        import pandas as pd

        conn = get_active_connection()
        try:
            df = pd.read_sql("SELECT * FROM dataset", conn)
        finally:
            conn.close()

        if fmt == 'csv':
            buffer = io.BytesIO()
            df.to_csv(buffer, index=False)
            buffer.seek(0)
            mimetype = 'text/csv'
            ext = 'csv'
        elif fmt == 'json':
            buffer = io.BytesIO()
            df.to_json(buffer, orient='records', date_format='iso')
            buffer.seek(0)
            mimetype = 'application/json'
            ext = 'json'
        elif fmt == 'xlsx':
            buffer = to_excel(df)
            mimetype = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'
            ext = 'xlsx'
        elif fmt == 'pdf':
            buffer = to_pdf(df, title="Cleaned Dataset")
            mimetype = 'application/pdf'
            ext = 'pdf'
        elif fmt == 'docx':
            buffer = to_word(df, title="Cleaned Dataset")
            mimetype = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document'
            ext = 'docx'

        download_name = f"cleaned_dataset.{ext}"
        return send_file(buffer, as_attachment=True, download_name=download_name, mimetype=mimetype)

    except Exception as e:
        logger.exception("Export cleaned dataset failed: %s", str(e))
        return jsonify({"error": f"Export failed: {str(e)}"}), 500