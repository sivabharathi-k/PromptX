# PromptX — AI-Powered Conversational Data Analysis Platform

> **Transform raw datasets into actionable insights using natural language — no SQL, no coding, no complexity.**

PromptX is a production-grade, enterprise-ready web application that redefines how non-technical users interact with tabular data. Upload a CSV or Excel file, converse with your dataset in plain English, and instantly receive query results, AI-generated visualizations, data quality reports, and exportable documents — all powered by a sophisticated LLM-driven backend.

---

## 📋 Table of Contents

1. [Project Overview](#-project-overview)
2. [Problem Statement](#-problem-statement)
3. [Key Features](#-key-features)
4. [Technology Stack](#-technology-stack)
5. [Tools and Frameworks Used](#-tools-and-frameworks-used)
6. [System Architecture](#-system-architecture)
7. [Feature-wise Technical Breakdown](#-feature-wise-technical-breakdown)
8. [Database Design](#-database-design)
9. [API Integrations](#-api-integrations)
10. [Installation Guide](#-installation-guide)
11. [Usage Instructions](#-usage-instructions)
12. [Project Workflow](#-project-workflow)
13. [Folder Structure Explanation](#-folder-structure-explanation)
14. [Future Enhancements](#-future-enhancements)
15. [Conclusion](#-conclusion)

---

## 🚀 Project Overview

**PromptX** (formerly "Text to Excel") is a full-stack conversational data analysis platform that bridges the gap between natural language and structured querying. Built with Python (Flask) on the backend and vanilla JavaScript (with Chart.js) on the frontend, it leverages the **Groq API** — specifically fine-tuned LLama-based models — to perform real-time natural language to SQL translation, intent classification, query relevance validation, and automated chart recommendation.

The platform supports the complete data analysis lifecycle:
- **Ingestion** → Drag-and-drop CSV/Excel upload with automatic schema detection
- **Exploration** → Conversational querying with paginated results
- **Transformation** → Natural language data editing (insert, update, delete, clean)
- **Visualization** → Auto-recommended charts + full custom chart builder
- **Analysis** → Comprehensive 12-section statistical insights engine
- **Export** → Download results as Excel, PDF, Word, PNG, or JPG

---

## 🎯 Problem Statement

**Who it's for:** Business analysts, data enthusiasts, students, interns, and non-technical stakeholders who need to extract insights from tabular data but lack SQL proficiency or coding skills.

**The Problem:**
- Traditional data analysis requires SQL knowledge or complex spreadsheet formulas
- Existing BI tools (Tableau, Power BI) have steep learning curves and licensing costs
- Query builders and drag-and-drop UIs are cumbersome for ad-hoc analysis
- Converting insights into shareable reports requires multiple tools and manual effort

**How PromptX Solves It:**
- Users upload a dataset and ask questions in plain English
- An LLM converts natural language to SQL automatically with self-correction
- Intent classification routes queries to the appropriate engine (query, edit, visualize, schema)
- Results are instantly rendered as tables, charts, or schema descriptions
- One-click export to multiple formats (Excel, PDF, Word, PNG, JPG)
- Comprehensive data quality reports and health scoring for every dataset

---

## ✨ Key Features

### 1. 📤 Smart File Upload
- Drag-and-drop + click-to-browse upload interface
- Supports CSV, XLSX, and XLS file formats
- Automatic schema detection (NUM, TEXT, DATE classification)
- 50-row instant preview for visualization readiness
- Session-isolated dataset storage

### 2. 💬 Natural Language Querying
- Ask questions in plain English (e.g., "Show top 10 customers by revenue")
- LLM-powered text-to-SQL generation via Groq API
- Self-correcting SQL engine with automatic error recovery
- Fast rule-based fallback when LLM fails (pandas fallback)
- Paginated results display (20 rows per page)

### 3. 🧠 AI-Powered Intent Classification
- Hybrid classification: fast rule-based + LLM fallback
- 4 intent types: `query`, `edit`, `visualization`, `schema`
- 7 edit operation types: `insert`, `update`, `delete`, `schema_add`, `schema_rename`, `schema_remove`, `clean`, `transform`, `undo`, `save_subset`
- Destructive operation confirmation safety net
- Context-aware follow-up handling

### 4. ✏️ Conversational Data Editing
- Insert rows: "Add a new employee with name John and salary 50000"
- Update rows: "Change all salaries in department A to 60000"
- Delete rows: "Remove rows where age is less than 18" (confirmation required)
- Add columns: "Add a column called bonus"
- Rename columns: "Rename 'emp_name' to 'employee_name'"
- Remove columns: "Drop the 'temp' column" (confirmation required)
- Clean data: "Remove duplicates", "Fill missing values with 0", "Trim spaces"
- Transform data: Custom transformations via natural language
- Snapshot-based undo for all destructive operations

### 5. 📊 Comprehensive Visualization Suite
- **Auto-Visualization**: AI analyzes the dataset and recommends the Top 10 best charts with confidence scores
- **Custom Chart Builder**: Full Power BI-style interface with:
  - 7 chart types: Bar, Line, Area, Pie, Donut, Scatter, Histogram
  - Axis selection with intelligent defaults
  - 6 aggregation options: Sum, Avg, Count, Max, Min, Median
  - Sort Order: Ascending / Descending
  - Top-N filtering (5, 10, 20, 50, 100)
  - Smart chart validation with auto-suggestions
  - Professional insights panel with statistical analysis
- **In-chart type switching**: Switch between chart types without losing context
- **Chat inline charts**: Visualize results directly in conversation

### 6. 📈 AI Insights Engine (12-Section Analysis)
- Dataset Overview & Summary
- Data Quality Assessment (missing values, duplicates, consistency)
- Statistical Summary (mean, median, mode, std, IQR, skewness)
- Outlier Analysis (IQR-based with severity classification)
- Correlation Insights (Pearson matrix with strong/weak relationships)
- Trend Analysis (MoM changes, seasonality detection, slope calculation)
- Category Analysis (concentration, top/bottom performers)
- Performance Analysis (gap analysis, segment comparison)
- Anomaly Detection (z-score, spikes, excessive zeros)
- Key Business Insights (concentration risk, growth opportunities)
- Recommendations (actionable data-driven suggestions)
- Executive Summary with Health Score (0–100)

### 7. 📂 Dataset Overview Dashboard
- Total Records, Columns, File Size
- Column Type Distribution (Numeric, Categorical, Date, Boolean)
- Schema Summary with sample values
- Data Quality Summary (missing, duplicates, consistency)
- Key Field Detection (primary ID, date column, measures)
- Health Score with visual progress bar
- 6-section professional report exportable to Excel, PDF, Word, PNG, JPG

### 8. 📤 Multi-Format Export
- **Query Results**: Excel (.xlsx), PDF (.pdf), Word (.docx), Image (.png, .jpg)
- **Chart Exports**: PNG (client-side), PDF, Excel, Word (server-side with embedded image + data + insights)
- **Overview Reports**: Full dataset overview in all formats

### 9. 🛡️ Relevance Validation Pipeline
- Production-grade 8-step query understanding:
  1. Text Normalization (word-number, synonym expansion)
  2. Intent Detection (SHOW_DATA, AGGREGATION, VISUALIZATION, METADATA)
  3. Synonym Expansion
  4. Fast Pattern ALLOW
  5. Fast Pattern REJECT
  6. Hybrid Scoring (intent 40% + semantic 30% + schema 20% + entity 10%)
  7. LLM Fallback (uncertain zone 0.40–0.60)
  8. Intelligent Suggestions for off-topic queries

### 10. 🌓 Enterprise UI/UX
- Dark/Light theme with persisted preference
- Responsive sidebar navigation
- Dataset health indicator
- Toast notifications system
- Keyboard shortcuts (Enter to send, Shift+Enter for new line, Esc to close)
- Professional Chart.js rendering with theme-aware colors
- Animated transitions and micro-interactions

---

## 🛠 Technology Stack

### Backend

| Technology | Purpose | Version |
|------------|---------|---------|
| **Python** | Primary programming language | 3.9+ |
| **Flask** | Web framework (WSGI) | 3.0+ |
| **Flask-Session** | Server-side filesystem sessions | 0.8+ |
| **SQLite** | Embedded database engine | Built-in |
| **Pandas** | Data manipulation & analysis | 2.0+ |
| **NumPy** | Numerical computing | 1.24+ |
| **Groq API** | LLM inference (text-to-SQL, classification) | 0.9+ |
| **Matplotlib** | Chart rendering for exports | 3.7+ |
| **ReportLab** | PDF document generation | 4.0+ |
| **python-docx** | Word document generation | 1.1+ |
| **OpenPyXL** | Excel file generation | 3.1+ |
| **XLRD** | Legacy Excel reading | 2.0+ |
| **Pillow (PIL)** | Image processing | 10.0+ |
| **Werkzeug** | WSGI utilities | 3.0+ |
| **python-dotenv** | Environment variable loading | 1.0+ |

### Frontend

| Technology | Purpose |
|------------|---------|
| **HTML5** | Document structure |
| **CSS3** | Styling with custom properties (theming) |
| **JavaScript (Vanilla ES6+)** | Client-side logic (no frameworks) |
| **Chart.js** | Interactive chart rendering |
| **Chart.js DataLabels Plugin** | Value annotation on charts |
| **Google Fonts (Inter)** | Typography |
| **Tabler Icons** | Iconography |

### Infrastructure & Tools

| Tool | Purpose |
|------|---------|
| **Git** | Version control |
| **Docker** | Containerization support |
| **Kubectl** | Kubernetes deployment support |
| **Visual Studio Code** | Development IDE |
| **pip** | Python package management |
| **npm** | Node package management (if needed) |
| **curl** | API testing |

---

## 🧩 Tools and Frameworks Used

### Backend Frameworks & Libraries

| Library | Usage in Codebase |
|---------|-------------------|
| **Flask** | Application factory pattern, Blueprint-based routing |
| **Flask-Session** | Filesystem-based session storage for large datasets |
| **Groq** | All LLM interactions (SQL generation, intent classification, relevance validation) |
| **Pandas** | Core data structure (DataFrame), SQL I/O, statistical computations |
| **SQLite3** | Per-session persistent dataset storage, PRAGMA-based schema inspection |
| **Matplotlib** | Server-side chart rendering for PDF/Word/Excel export |
| **ReportLab** | Professional PDF report generation with tables and images |
| **python-docx** | Word document generation with formatted tables and embedded images |
| **OpenPyXL** | Excel workbook generation with charts, formatting, and styling |
| **Pillow** | Image format conversion and processing for export |
| **NumPy** | Statistical computations (variance, correlation, quantiles) |
| **python-dotenv** | Secure API key and configuration management |
| **Werkzeug** | Secure filename handling |

### Frontend Libraries

| Library | Usage in Codebase |
|---------|-------------------|
| **Chart.js 4.4** | All chart rendering (bar, line, area, pie, doughnut, scatter) |
| **Chart.js DataLabels 2.2** | Value labels on bar charts |
| **Tabler Icons** | UI icons throughout the interface |

---

## 🏗 System Architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         CLIENT (Browser)                            │
│                                                                     │
│  ┌─────────────┐  ┌──────────────┐  ┌─────────────────────────┐   │
│  │ Upload UI    │  │ Chat         │  │ Visualization Suite     │   │
│  │ (Drag/drop)  │  │ Interface    │  │ (Chart.js renderer)     │   │
│  └──────┬───────┘  └──────┬───────┘  └───────────┬─────────────┘   │
│         │                 │                      │                  │
│         └─────────────────┴──────────────────────┘                  │
│                              │ HTTP (Fetch API)                     │
└──────────────────────────────┼──────────────────────────────────────┘
                               │
┌──────────────────────────────┼──────────────────────────────────────┐
│                    FLASK APPLICATION (WSGI)                         │
│                              │                                      │
│  ┌───────────────────────────┴──────────────────────────────┐      │
│  │                    API Blueprint (routes.py)              │      │
│  │                                                          │      │
│  │  /upload → /query → /schema → /dataset-overview          │      │
│  │  /visualize/* → /download/* → /download-excel            │      │
│  └──────────┬──────────────────────────┬────────────────────┘      │
│             │                          │                            │
│  ┌──────────▼──────────┐   ┌──────────▼──────────────────┐         │
│  │   Intent Classifier  │   │   Relevance Validator       │         │
│  │   (Fast + LLM)       │   │   (8-step pipeline)        │         │
│  └──────────┬───────────┘   └──────────┬──────────────────┘         │
│             │                          │                            │
│  ┌──────────▼──────────────────────────────────────────────────┐   │
│  │                    SERVICE LAYER                             │   │
│  │                                                              │   │
│  │  ┌────────────┐ ┌───────────┐ ┌──────────────┐              │   │
│  │  │ Query      │ │ Export    │ │ Visualization │              │   │
│  │  │ Service    │ │ Service   │ │ Services (×5) │              │   │
│  │  └─────┬──────┘ └─────┬─────┘ └──────┬───────┘              │   │
│  │        │              │              │                       │   │
│  │  ┌─────▼──────┐ ┌─────▼─────┐ ┌──────▼───────┐              │   │
│  │  │ Cleaning   │ │ Schema    │ │ Insights     │              │   │
│  │  │ Service    │ │ Service   │ │ Engine       │              │   │
│  │  └─────┬──────┘ └─────┬─────┘ └──────┬───────┘              │   │
│  │        │              │              │                       │   │
│  │  ┌─────▼──────┐ ┌─────▼─────┐ ┌──────▼───────┐              │   │
│  │  │ Transform  │ │ Audit     │ │ Insert/Update │              │   │
│  │  │ Service    │ │ Service   │ │ Delete Service│              │   │
│  │  └────────────┘ └───────────┘ └──────────────┘              │   │
│  └──────────────────────────────────────────────────────────────┘   │
│                               │                                     │
│  ┌────────────────────────────▼──────────────────────────────┐     │
│  │                    DATA LAYER                               │     │
│  │                                                             │     │
│  │  ┌──────────────────┐  ┌──────────────────────────┐        │     │
│  │  │ Per-Session      │  │ Schema Detector          │        │     │
│  │  │ SQLite Database  │  │ (NUM/TEXT/DATE)          │        │     │
│  │  └──────────────────┘  └──────────────────────────┘        │     │
│  │                                                             │     │
│  │  ┌──────────────────┐  ┌──────────────────────────┐        │     │
│  │  │ File Store       │  │ Dataset Cache            │        │     │
│  │  │ (uploads/exports)│  │ (DataFrame + Profile)    │        │     │
│  │  └──────────────────┘  └──────────────────────────┘        │     │
│  └─────────────────────────────────────────────────────────────┘     │
└──────────────────────────────────────────────────────────────────────┘
                               │
                    ┌──────────▼──────────┐
                    │    GROQ API (LLM)    │
                    │  (cloud inference)   │
                    └─────────────────────┘
```

---

## 📖 Feature-wise Technical Breakdown

### Feature 1: File Upload & Schema Detection

| Aspect | Details |
|--------|---------|
| **Purpose** | Allow users to upload CSV/Excel files and automatically detect column types |
| **Technologies** | Flask, Pandas, OpenPyXL, XLRD, Werkzeug |
| **Backend Workflow** | 1. Validate file extension → 2. Read file into DataFrame → 3. Clear previous session data → 4. Load DataFrame into per-session SQLite DB → 5. Detect master schema (NUM/TEXT/DATE) → 6. Store preview rows → 7. Return columns + schema + preview |
| **Frontend Workflow** | 1. Drag & drop or click to select file → 2. Validate extension client-side → 3. POST multipart form to `/upload` → 4. Display success animation → 5. Transition to chat screen → 6. Populate sidebar with metadata |
| **Database Operations** | `CREATE TABLE dataset (...)`, `INSERT INTO dataset VALUES (...)`, `PRAGMA table_info(dataset)` |
| **APIs Used** | `POST /upload` endpoint |
| **Data Flow** | File → Pandas DataFrame → SQLite table → Schema dict (session) → Frontend render |
| **Input** | CSV/XLSX file blob |
| **Output** | JSON with: total rows, column list, master schema, preview rows (first 50) |

### Feature 2: Natural Language Querying (Text-to-SQL)

| Aspect | Details |
|--------|---------|
| **Purpose** | Convert natural language questions into SQL queries and return results |
| **Technologies** | Groq API, Pandas, SQLite3, Flask |
| **Backend Workflow** | 1. Receive question → 2. Route through intent classifier → 3. Generate SQL via Groq → 4. Validate SQL (safety + syntax) → 5. Execute on SQLite → 6. On failure: self-correct via LLM → 7. On LLM failure: pandas fallback → 8. Store result in session → 9. Return JSON |
| **Frontend Workflow** | 1. User types question → 2. POST `/query` → 3. Show loading animation → 4. Render results as paginated table + action toolbar → 5. Enable visualize & export buttons |
| **Database Operations** | `SELECT ... FROM dataset WHERE ... GROUP BY ... ORDER BY ... LIMIT ...` |
| **APIs Used** | Groq Chat Completions API (`llama-3.1-8b-instant`), `POST /query` |
| **Data Flow** | Question → Intent Classifier → Groq SQL Generation → SQLite Execution → Optional Self-Correction → Optional Pandas Fallback → Session Storage → Frontend Table |
| **Input** | `{ "question": "Show top 5 customers by revenue" }` |
| **Output** | `{ columns, rows, total, type: "query" }` |

### Feature 3: AI-Powered Visualization

| Aspect | Details |
|--------|---------|
| **Purpose** | Automatically generate and render charts based on user questions and data profiles |
| **Technologies** | Chart.js, Pandas, NumPy, Groq (for recommendations) |
| **Backend Workflow** | 1. Extract column profile → 2. Classify user intent/chart type → 3. Use ChartRecommender to pick best chart → 4. Render spec via VisualizationPreparationService → 5. Generate insights → 6. Return spec + insights + all chart types |
| **Frontend Workflow** | 1. Send question → 2. Receive visualization response → 3. Render Chart.js canvas → 4. Show chart type switcher → 5. Allow in-line chart switching via `/visualize/render` |
| **Database Operations** | Read-only: `SELECT * FROM dataset` for active data |
| **APIs Used** | `POST /query` (visualization intent), `POST /visualize/render`, `POST /visualize/auto-recommendations`, `POST /visualize/custom-render` |
| **Data Flow** | Question → Intent Classification (visualization) → Column Profiling → Chart Recommendation → Spec Generation → Chart.js Rendering → Interactive Type Switching |
| **Input** | `{ "question": "Show bar chart of sales by region" }` |
| **Output** | `{ type: "visualization", spec: Chart.js config, insights, chart_type, all_types }` |

### Feature 4: Auto-Visualization (Top 10 Recommendations)

| Aspect | Details |
|--------|---------|
| **Purpose** | Generate the Top 10 best chart recommendations for the full dataset |
| **Technologies** | Pandas, NumPy, Chart.js, VisualizationProfileService, ChartRecommender |
| **Backend Workflow** | 1. Load full dataset + column profile → 2. Build candidate column-pair combinations → 3. Score each combination (95 for date+numeric line charts, 90 for cat+numeric bar, etc.) → 4. Render spec for each → 5. Generate insights → 6. Sort by confidence → 7. Return Top 10 + column profile |
| **Frontend Workflow** | 1. Click "Auto Visualization" in sidebar → 2. Fetch recommendations → 3. Render column profile badges → 4. Display 10 recommendation cards → 5. Render mini charts → 6. Expand to full Custom Chart Builder |
| **Database Operations** | Read from full dataset via `DataFrame` load |
| **APIs Used** | `POST /visualize/auto-recommendations` |
| **Data Flow** | Full Dataset → Column Classification → Candidate Generation → Scoring → Spec Rendering → Cached → Frontend Card Grid |
| **Input** | No input (uses active dataset) |
| **Output** | `{ success, recommendations: [{ chart_type, x_column, y_column, reason, confidence_score, spec, insights }], columns_profile }` |

### Feature 5: Custom Chart Builder

| Aspect | Details |
|--------|---------|
| **Purpose** | Full-featured chart creation tool with aggregation, sorting, filtering, and export |
| **Technologies** | Chart.js, Pandas, OpenPyXL, ReportLab, python-docx |
| **Backend Workflow** | 1. Receive chart params → 2. Validate column existence → 3. Aggregate (sum/avg/count/min/max/median) → 4. Sort → 5. Apply Top-N → 6. Render spec → 7. Generate professional insights → 8. Return spec + insights |
| **Frontend Workflow** | 1. Select chart type → 2. Select X/Y axes → 3. Configure aggregation, sort order, Top-N → 4. Client-side validation → 5. Fetch from `/visualize/custom-render` → 6. Fallback to local spec → 7. Render chart + insights → 8. Export via PNG/PDF/Excel/Word buttons |
| **Database Operations** | Read from full dataset |
| **APIs Used** | `POST /visualize/custom-render`, `POST /visualize/export-chart/:fmt` |
| **Data Flow** | UI Controls → Backend Pipeline (Aggregate → Sort → Top-N → Render) → Spec + Insights → Chart.js → Export |
| **Input** | `{ chart_type, xColumn, yColumn, aggregation, sortOrder, topN }` |
| **Output** | `{ spec, insights, columns, total }` |

### Feature 6: Data Editing (Insert/Update/Delete/Schema)

| Aspect | Details |
|--------|---------|
| **Purpose** | Modify dataset through natural language commands |
| **Technologies** | Groq API, SQLite3, Pandas |
| **Backend Workflow** | 1. Classify edit intent → 2. For destructive ops (delete/drop column): show confirmation → 3. Wait for "CONFIRM" → 4. Create undo snapshot → 5. Execute operation (LLM-parsed parameters) → 6. Sync database to session → 7. Return updated preview → 8. On failure: auto-undo |
| **Frontend Workflow** | 1. User types edit command → 2. Receive confirmation warning → 3. User types "CONFIRM" → 4. Operation executed → 5. Table re-renders with updated data |
| **Database Operations** | `INSERT INTO`, `UPDATE`, `DELETE`, `ALTER TABLE ADD/DROP/RENAME COLUMN`, `CREATE TABLE`, `DROP TABLE` |
| **APIs Used** | Groq Chat Completions for parameter extraction, Flask session for pending operations |
| **Data Flow** | NL Command → Intent Classification → Confirmation (if destructive) → Snapshot → SQL Execution → Sync → Preview |
| **Input** | `{ "question": "Add a column called discount with default value 0" }` |
| **Output** | `{ type: "edit", message, columns, rows, total }` |

### Feature 7: Dataset Overview & Health Score

| Aspect | Details |
|--------|---------|
| **Purpose** | Generate comprehensive 12-section statistical analysis for any dataset |
| **Technologies** | Pandas, NumPy, SciPy (via NumPy), Matplotlib |
| **Backend Workflow** | 1. Load full dataset → 2. Classify columns (NUM/TEXT/DATE/BOOL) → 3. Compute stats → 4. Detect outliers (IQR) → 5. Compute correlations (Pearson) → 6. Detect trends (slope, MoM, seasonality) → 7. Category analysis (concentration) → 8. Performance analysis (gaps) → 9. Anomaly detection (z-score) → 10. Generate business insights → 11. Compute health score → 12. Return complete payload |
| **Frontend Workflow** | 1. Click "Dataset Overview" in sidebar → 2. Fetch `/dataset-overview` → 3. Render 6-section report → 4. Export overview via format selector |
| **Database Operations** | Full table scan: `SELECT * FROM dataset` |
| **APIs Used** | `GET /dataset-overview`, `GET /dataset-overview/download/:fmt` |
| **Data Flow** | Full Dataset → Column Classification → Statistical Computation → Insight Generation → Health Score → Frontend Report → Export |
| **Input** | No input (uses active dataset) |
| **Output** | `{ success, total_records, column_types, data_quality, key_fields, health_score, schema_details }` |

### Feature 8: Multi-Format Export Engine

| Aspect | Details |
|--------|---------|
| **Purpose** | Export query results and charts in multiple professional formats |
| **Technologies** | ReportLab, python-docx, OpenPyXL, Matplotlib, Pillow |
| **Backend Workflow** | 1. Receive format + data → 2. For Excel: create workbook with styled tables → 3. For PDF: use ReportLab with tables + embedded images → 4. For Word: create docx with formatted tables → 5. For Images: render DataFrame as matplotlib figure → 6. Return binary stream as attachment |
| **Frontend Workflow** | 1. Click Export → 2. Select format from dropdown → 3. Download via browser redirect (data export) → 4. Or POST chart data + base64 image for chart export |
| **Database Operations** | Read from session (last result) |
| **APIs Used** | `GET /download/:fmt`, `GET /download-excel`, `POST /visualize/export-chart/:fmt` |
| **Data Flow** | Session Data → Format-specific Document Builder (Excel/PDF/Word/Image) → Binary Buffer → HTTP Response → Browser Download |
| **Input** | Format string and optionally chart data + base64 image |
| **Output** | File download (xlsx/pdf/docx/png/jpg) |

---

## 🗄 Database Design

The application uses **SQLite3** as its primary database engine, with per-session isolation via filesystem-based databases.

### Active Dataset Table

```sql
-- Core table: stores uploaded dataset rows
CREATE TABLE dataset (
    [column1] TYPE,
    [column2] TYPE,
    ...
);
```

**Design Characteristics:**
- Table name is always `"dataset"` (double-quoted in queries)
- Column names are dynamically determined from uploaded file headers
- All columns use TEXT storage with SQLite's flexible typing
- Schema is detected via `PRAGMA table_info(dataset)`

### Session Storage

- **Flask-Session** with filesystem backend
- Session files stored at `backend/data/sessions/`
- Key session variables:
  - `master_schema`: `Dict[str, "NUM"|"TEXT"|"DATE"]`
  - `last_result`: JSON string (pandas split orientation)
  - `last_query_sql`: Last executed SQL
  - `file_name`: Uploaded filename
  - `pending_operation`: Pending destructive operation context
  - `active_dataset_session_id`: UUID for per-session SQLite isolation

### Per-Session SQLite Database

- Location: `backend/data/sessions/active_datasets/active_{hash}.sqlite3`
- Hash derived from session UUID (SHA-256, first 16 chars)
- Created on first upload, replaced on subsequent upload
- Destroyed on session clear or new upload

### Master Schema (Single Source of Truth)

| Type | Description | Example Detection |
|------|-------------|-------------------|
| `NUM` | Numeric column | All non-null values are numeric (int or float) |
| `TEXT` | Categorical/text column | Fallback type |
| `DATE` | Date/time column | >90% of values parseable as datetime |

---

## 🔌 API Integrations

### Groq API (Primary External API)

**Provider:** Groq Inc.  
**Endpoint:** `https://api.groq.com/openai/v1/chat/completions`  
**Model:** `llama-3.1-8b-instant` (configurable)  
**Authentication:** API Key via `GROQ_API_KEY` environment variable

**Integration Points:**

| Integration | Purpose | Temperature | Max Tokens |
|-------------|---------|-------------|------------|
| **Text-to-SQL** | Convert natural language to SQLite SELECT queries | 0.0 | 300 |
| **SQL Self-Correction** | Fix invalid SQL with error feedback | 0.0 | 300 |
| **Intent Classification** | Route user questions to query/edit/visualize/schema | 0.0 | 150 |
| **Relevance Validation** | Determine if question is dataset-related | 0.0 | 80 |
| **Schema Operations** | Parse insert/update/delete/schema edit parameters | 0.0 | 200 |
| **Cleaning Operations** | Parse data cleaning instructions | 0.0 | 200 |

**Rate Limits:** Standard Groq API rate limits apply (free tier: 30 req/min)

### Google Fonts API

- **Purpose:** Load Inter font family
- **CDN:** `fonts.googleapis.com`

### CDN Libraries (Frontend)

- Chart.js 4.4.0: `cdn.jsdelivr.net/npm/chart.js@4.4.0`
- Chart.js DataLabels 2.2.0: `cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.2.0`
- Tabler Icons: `cdn.jsdelivr.net/npm/@tabler/icons-webfont`

---

## 📥 Installation Guide

### Prerequisites

- **Python 3.9+** installed
- **Git** installed (optional, for cloning)
- **Groq API Key** (free at [console.groq.com](https://console.groq.com))

### Step-by-Step Installation

```bash
# 1. Clone the repository
git clone https://github.com/your-username/promptx.git
cd promptx

# Or if starting from extraction:
cd Internship_project

# 2. (Recommended) Create a virtual environment
python -m venv venv
# On Windows:
venv\Scripts\activate
# On macOS/Linux:
# source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Create .env file with your Groq API key
echo GROQ_API_KEY=gsk_your_api_key_here > .env

# 5. (Optional) Configure additional settings
# Edit .env to add:
# GROQ_MODEL=llama-3.1-8b-instant
# HOST=127.0.0.1
# PORT=8080
# DEBUG=true
# SECRET_KEY=your-secret-key

# 6. Run the application
python -m backend.main
```

### Docker Installation

```bash
# Build the Docker image
docker build -t promptx .

# Run the container
docker run -p 8080:8080 -e GROQ_API_KEY=gsk_your_api_key_here promptx
```

### Verification

Once running, open your browser and navigate to:
```
http://127.0.0.1:8080
```

You should see the PromptX upload screen with the logo and "Talk with your CSV files using plain English" tagline.

---

## 📖 Usage Instructions

### 1. Upload a Dataset

1. Open the application in your browser
2. Drag & drop a CSV or Excel file onto the upload zone, OR click to browse
3. Wait for the upload animation to complete
4. The interface transitions to the enterprise chat workspace
5. View dataset stats in the left sidebar (rows, columns, types, health score)

### 2. Ask Questions (Query Mode)

Type natural language questions in the chat input:

```
"Show top 10 rows"
"Count total records"
"Average salary by department"
"Show rows where age is greater than 30"
"Find duplicate records in customer column"
"Show missing values report"
"What is the total revenue by region sorted descending?"
```

### 3. Visualize Data

**Auto Visualization:**
1. Click "Visualization → Auto Visualization" in the sidebar
2. View the Top 10 AI-recommended charts with confidence scores
3. Click "Expand" to open any recommendation in the Custom Chart Builder

**Via Chat:**
```
"Show bar chart of sales by region"
"Plot line chart of revenue over time"
"Pie chart of customer segments"
"Visualize salary distribution"
```

### 4. Custom Chart Builder

1. Click "Visualization → Custom Chart Builder" in the sidebar
2. Select chart type (Bar, Line, Pie, Scatter, Histogram, Area)
3. Choose X-axis and Y-axis columns
4. Configure aggregation (Sum, Avg, Count, Max, Min, Median)
5. Set Sort Order and Top-N limit
6. Click "Build Chart"
7. Export as PNG, PDF, Excel, or Word

### 5. Edit Data Via Natural Language

```
"Insert a new row with name: John, age: 30, salary: 50000"
"Update salary to 60000 where department is 'Engineering'"
"Delete rows where age is less than 18" (type CONFIRM to proceed)
"Add a column called bonus"
"Rename 'emp_name' to 'employee_name'"
"Remove column 'temp_data'" (type CONFIRM to proceed)
"Remove duplicate rows"
"Fill missing values in salary with 0"
"Undo last action"
"Save subset" (saves current query result as active dataset)
```

### 6. Export Results

- Click the "Export" button below any query result
- Choose format: Excel (.xlsx), PDF (.pdf), Word (.docx), Image (.png/.jpg)
- For charts: use the export buttons in the Custom Chart Builder
- For Dataset Overview: use the export dropdown at the bottom

### 7. View Dataset Overview

1. Click "Dataset Overview" in the sidebar
2. Browse 6 sections of analysis
3. Export the full report via the export panel

---

## 🔄 Project Workflow

```
USER ACTION                    BACKEND PROCESSING                    OUTPUT
══════════════                 ═══════════════════                   ═══════════════

1. Upload CSV/Excel
   │
   ├─► POST /upload
   │     ├─ Validate file extension (.csv/.xlsx/.xls)
   │     ├─ Read file → Pandas DataFrame
   │     ├─ Clear previous session & SQLite DB
   │     ├─ Load DataFrame → per-session SQLite
   │     ├─ Detect schema (NUM/TEXT/DATE) → session['master_schema']
   │     ├─ Store preview (first 50 rows) in frontend state
   │     └─ Return JSON { rows, columns, schema, preview_rows }
   │
   └─► Frontend: Transition to Chat Screen
         ├─ Populate sidebar with dataset metadata
         ├─ Fetch /dataset-overview for enhanced stats
         └─ Show empty state with prompt suggestions

2. Ask Question
   │
   ├─► POST /query
   │     ├─ Check active dataset exists
   │     ├─ Check for destructive confirmation (delete/drop)
   │     ├─ Check for data quality keywords
   │     ├─ CLASSIFY INTENT:
   │     │   ├─ Fast path: rule-based (no LLM)
   │     │   └─ Fallback: Groq LLM classification
   │     │
   │     ├─ [VISUALIZATION intent]
   │     │   ├─ Extract last query result from session
   │     │   ├─ Profile columns (VisualizationProfileService)
   │     │   ├─ Recommend chart (ChartRecommender)
   │     │   ├─ Render spec (VisualizationPreparationService)
   │     │   └─ Return { type: "visualization", spec, insights }
   │     │
   │     ├─ [SCHEMA intent]
   │     │   ├─ Generate schema description (PRAGMA)
   │     │   └─ Return { type: "schema", markdown_report }
   │     │
   │     ├─ [EDIT intent]
   │     │   ├─ [DELETE/SCHEMA_REMOVE] → Require CONFIRM
   │     │   ├─ Create undo snapshot (snapshot_id)
   │     │   ├─ Execute: insert/update/delete/clean/transform
   │     │   ├─ Sync SQLite → session
   │     │   ├─ On failure: auto-undo via audit_service
   │     │   └─ Return { type: "edit", updated_preview }
   │     │
   │     ├─ [QUERY intent]
   │     │   ├─ Validate relevance (8-step pipeline)
   │     │   ├─ Generate SQL via Groq
   │     │   ├─ Validate SQL safety & syntax
   │     │   ├─ Execute SQL on SQLite
   │     │   ├─ [On error] LLM self-correction pass
   │     │   ├─ [On error] Pandas fallback (rule-based)
   │     │   ├─ Store result in session['last_result']
   │     │   └─ Return { type: "query", columns, rows }
   │     │
   │     └─ On IRRELEVANT → Return suggestions
   │
   └─► Frontend: Render Response
         ├─ [query]: Paginated table + export toolbar + visualize button
         ├─ [visualization]: Chart.js canvas + type switcher + data table
         ├─ [schema]: Formatted markdown report
         ├─ [edit]: Success message + updated table
         ├─ [delete_confirm]: Warning message
         └─ [irrelevant]: Helpful message + suggestion chips

3. Build Custom Chart
   │
   ├─► POST /visualize/custom-render
   │     ├─ Validate chart type + axes + aggregation
   │     ├─ Full dataset: Aggregate → Sort → Top-N → Render
   │     ├─ Generate professional insights (10 categories)
   │     └─ Return { spec, insights }
   │
   └─► Frontend: Chart.js Rendering + Insights Panel
         ├─ Render interactive Chart.js chart
         ├─ Display professional insights
         └─ Export buttons (PNG/PDF/Excel/Word)

4. Export Results
   │
   ├─► GET /download/{format}
   │     ├─ Read session['last_result'] DataFrame
   │     ├─ [xlsx]: OpenPyXL styled workbook
   │     ├─ [pdf]: ReportLab document with table
   │     ├─ [docx]: python-docx formatted document
   │     ├─ [png/jpg]: Matplotlib figure rendering
   │     └─ Return file attachment
   │
   └─► Frontend: Browser download
         └─ Save file locally

5. Dataset Overview
   │
   ├─► GET /dataset-overview
   │     ├─ Load full dataset from SQLite
   │     ├─ Classify columns (NUM/TEXT/DATE/BOOL)
   │     ├─ Compute statistics (mean, median, IQR, outliers)
   │     ├─ Detect trends (slope, MoM, seasonality)
   │     ├─ Compute correlations (Pearson matrix)
   │     ├─ Analyze categories (concentration)
   │     ├─ Detect anomalies (z-score, spikes, zeros)
   │     ├─ Generate business insights
   │     ├─ Calculate health score (0-100)
   │     └─ Return complete 12-section payload
   │
   └─► Frontend: 6-section report render
         ├─ Dataset Summary
         ├─ Column Type Distribution
         ├─ Schema Summary (table)
         ├─ Data Quality Summary
         ├─ Key Column Detection
         ├─ Health Score (visual bar)
         └─ Export panel
```

---

## 📂 Folder Structure Explanation

```
Internship_project/
│
├── backend/                          # Python Flask backend
│   ├── main.py                       # App factory, server entry point
│   ├── api/                          # API layer
│   │   ├── __init__.py               # Package marker
│   │   ├── routes.py                 # ALL HTTP endpoints (Flask Blueprint)
│   │   └── data_edit_router_note.md  # Documentation for edit routing
│   │
│   ├── config/                       # Configuration management
│   │   ├── __init__.py               # Package marker
│   │   └── settings.py              # Environment vars, paths, constants
│   │
│   ├── data/                         # Runtime data directories
│   │   ├── exports/                  # Generated export files
│   │   ├── logs/                     # Application logs (including query_engine.log)
│   │   ├── sessions/                 # Flask-Session files + per-user SQLite databases
│   │   └── uploads/                  # (Reserved) Uploaded file storage
│   │
│   ├── services/                     # Business logic layer
│   │   ├── __init__.py               # Package marker
│   │   ├── audit_service.py          # Snapshot-based undo/redo
│   │   ├── chart_recommendation_service.py  # Chart recommendation engine
│   │   ├── chart_recommender.py      # Core chart scoring & ranking
│   │   ├── cleaning_service.py       # Data cleaning operations
│   │   ├── delete_service.py         # Row deletion with preview
│   │   ├── export_service.py         # Multi-format export (Excel/PDF/Word/Image)
│   │   ├── insert_service.py         # Row insertion via NL
│   │   ├── query_service.py          # Text-to-SQL generation + execution
│   │   ├── relevance_validator.py    # 8-step query understanding pipeline
│   │   ├── schema_service.py         # Column add/rename/remove
│   │   ├── transformation_service.py # Data transformation operations
│   │   ├── update_service.py         # Row update via NL
│   │   ├── visualization_preparation_service.py  # Chart spec rendering
│   │   ├── visualization_profile_service.py       # Column profiling for viz
│   │   └── insights/                 # AI Insights Engine
│   │       └── insights_engine.py    # 12-section statistical analysis
│   │
│   └── utils/                        # Utility functions
│       ├── __init__.py               # Package marker
│       ├── active_dataset_store.py   # Per-session SQLite management
│       ├── dataset_cache.py          # DataFrame + profile caching
│       ├── db_utils.py               # Schema extraction, DB helpers
│       ├── file_utils.py             # File validation & reading
│       └── schema_detector.py        # Column type detection (NUM/TEXT/DATE)
│
├── frontend/                         # Frontend assets
│   ├── static/                       # Static files
│   │   ├── main.js                   # ALL client-side logic (2828 lines)
│   │   ├── data_agent.js             # (Auxiliary script)
│   │   ├── style.css                 # ALL styling (dark/light theme)
│   │   └── promptx-logo.svg         # Application logo
│   │
│   └── templates/                    # Jinja2 templates
│       └── index.html                # Single-page application template
│
├── .env                              # Environment variables (NOT committed)
├── .gitignore                        # Git ignore rules
├── requirements.txt                  # Python dependencies
└── README.md                         # Project documentation
```

### Directory Design Principles

- **Separation of Concerns**: API routes (routes.py) delegate to service layer (services/) which uses utilities (utils/)
- **Single Source of Truth**: Master schema is stored in `session['master_schema']` and used by ALL modules
- **Session Isolation**: Each browser session gets its own SQLite database file
- **Layered Architecture**: API → Service → Utility → Data, with clear dependency direction
- **Feature Organization**: Each major operation (query, insert, delete, clean, etc.) has its own service file

---

## 🔮 Future Enhancements

### Short-Term (MVP Enhancements)

- [ ] **Multi-file support**: Allow uploading and joining multiple datasets
- [ ] **User authentication**: Login system with saved datasets per user
- [ ] **Chat history**: Persistent conversation history across sessions
- [ ] **Advanced filtering**: Date range pickers, numeric sliders for interactive filtering
- [ ] **Export enhancements**: Add CSV export, improve chart image quality in PDF/Word
- [ ] **Real-time collaboration**: WebSocket-based multi-user sessions

### Medium-Term

- [ ] **Advanced visualizations**: Heatmaps, box plots, waterfall charts, treemaps
- [ ] **Dashboard builder**: Create multi-chart dashboards with auto-refresh
- [ ] **Python code export**: Generate Python scripts for offline analysis
- [ ] **Data pipeline automation**: Schedule recurring uploads and reports
- [ ] **Natural language dashboard**: "Create a dashboard showing sales by region, trend, and top products"
- [ ] **Multi-language support**: UI and query parsing in multiple languages
- [ ] **CSV/Excel preview**: Show data preview before upload

### Long-Term

- [ ] **ML model integration**: AutoML for predictive analytics ("Predict next quarter sales")
- [ ] **Data storytelling**: Auto-generate narrative report from dataset
- [ ] **API access**: RESTful API for external integrations
- [ ] **Database connections**: Direct connection to PostgreSQL, MySQL, BigQuery
- [ ] **Mobile app**: Companion mobile application
- [ ] **Enterprise SSO**: SAML/OAuth integration
- [ ] **Data governance**: Audit trails, access control, data lineage

---

## 🏁 Conclusion

PromptX is a comprehensive, production-ready conversational data analysis platform that successfully bridges the gap between natural language and structured data querying. Built with a clean, layered architecture using **Python/Flask** on the backend and **vanilla JavaScript + Chart.js** on the frontend, it demonstrates:

1. **Full-stack engineering excellence**: Complete separation of concerns, API design, session management, error handling
2. **AI/LLM integration mastery**: Sophisticated use of Groq API for text-to-SQL, intent classification, self-correction, and relevance validation
3. **Data engineering capability**: Robust pipeline from file upload → schema detection → SQLite storage → query execution → export
4. **Enterprise UX design**: Professional, responsive interface with dark/light theme, toast notifications, and real-time feedback
5. **Analytics sophistication**: Statistical analysis engine covering 12 dimensions of data quality and business intelligence
6. **Production readiness**: Session isolation, error recovery, undo support, input validation, and comprehensive logging

This project is ideal for **internships, hackathons, and placement portfolios** as it showcases practical, real-world skills in:
- **Python backend development** (Flask, SQLite, Pandas)
- **LLM integration** (Groq API, prompt engineering, self-correction)
- **Data analysis & visualization** (Statistics, Chart.js, chart recommendation)
- **Frontend engineering** (Vanilla JS, HTML/CSS, responsive design)
- **Software architecture** (Layered design, service pattern, session management)
- **Project organization** (Clean structure, comprehensive documentation)

---

<p align="center">
  <strong>PromptX</strong> — <em>Talk to your data. Get answers. No SQL needed.</em>
</p>