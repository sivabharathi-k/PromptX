# PromptX — Conversational Data Analysis Platform

> **Transform raw datasets into actionable insights using natural language — no SQL, no coding, no complexity.**

PromptX is a production-grade, enterprise-ready web application that redefines how non-technical users interact with tabular data. Upload a CSV or Excel file, converse with your dataset in plain English, and instantly receive query results, data quality reports, and exportable documents — all powered by a sophisticated LLM-driven backend.

The platform is strictly **read-only**: you can query, analyze, and export your data, but you cannot modify the underlying dataset.

---

## ✨ Key Features

### 📤 Smart File Upload
- Drag-and-drop + click-to-browse upload interface
- Supports CSV, XLSX, and XLS file formats
- Automatic schema detection (NUM, TEXT, DATE classification)
- 50-row instant preview for visualization readiness
- Session-isolated dataset storage

### 💬 Natural Language Querying
- Ask questions in plain English (e.g., "Show top 10 customers by revenue")
- LLM-powered text-to-SQL generation via Groq API
- Self-correcting SQL engine with automatic error recovery
- Fast rule-based fallback when LLM fails (pandas fallback)
- Paginated results display (20 rows per page)

### 🧠 AI-Powered Intent Classification
- Hybrid classification: fast rule-based + LLM fallback
- 3 intent types: `query`, `visualization`, `schema`
- Context-aware follow-up handling



### 📈 AI Insights Engine
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

### 📂 Dataset Overview Dashboard
- Total Records, Columns, File Size
- Column Type Distribution (Numeric, Categorical, Date, Boolean)
- Schema Summary with sample values
- Data Quality Summary (missing, duplicates, consistency)
- Key Field Detection (primary ID, date column, measures)
- Health Score with visual progress bar
- 6-section professional report exportable to Excel, PDF, Word, PNG, JPG

### 📤 Multi-Format Export
- **Query Results**: Excel (.xlsx), PDF (.pdf), Word (.docx), Image (.png, .jpg)
- **Overview Reports**: Full dataset overview in all formats

### 🛡️ Relevance Validation Pipeline
- Production-grade 8-step query understanding:
  1. Text Normalization (word-number, synonym expansion)
  2. Intent Detection (SHOW_DATA, AGGREGATION, VISUALIZATION, METADATA)
  3. Synonym Expansion
  4. Fast Pattern ALLOW
  5. Fast Pattern REJECT
  6. Hybrid Scoring (intent 40% + semantic 30% + schema 20% + entity 10%)
  7. LLM Fallback (uncertain zone 0.40–0.60)
  8. Intelligent Suggestions for off-topic queries

### 🌓 Enterprise UI/UX
- Dark/Light theme with persisted preference
- Responsive sidebar navigation
- Dataset health indicator
- Toast notifications system
- Keyboard shortcuts (Enter to send, Shift+Enter for new line)
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
| **Pillow (PIL)** | Image processing | 10.0+ |

### Frontend
| Technology | Purpose |
|------------|---------|
| **HTML5** | Document structure |
| **CSS3** | Styling with custom properties (theming) |
| **JavaScript (Vanilla ES6+)** | Client-side logic (no frameworks) |
| **Google Fonts (Inter)** | Typography |
| **Tabler Icons** | Iconography |

---

## 🏗 Project Structure

```
promptx/
│
├── backend/                          # Python Flask backend
│   ├── main.py                       # App factory, server entry point
│   ├── api/                          # API layer
│   │   ├── __init__.py               # Package marker
│   │   └── routes.py                 # ALL HTTP endpoints (Flask Blueprint)
│   │
│   ├── config/                       # Configuration management
│   │   ├── __init__.py               # Package marker
│   │   └── settings.py              # Environment vars, paths, constants
│   │
│   ├── data/                         # Runtime data directories
│   │   ├── exports/                  # Generated export files
│   │   ├── logs/                     # Application logs
│   │   └── uploads/                  # Uploaded file storage
│   │
│   ├── services/                     # Business logic layer
│   │   ├── __init__.py               # Package marker
│   │   ├── export_service.py         # Multi-format export (Excel/PDF/Word/Image)
│   │   ├── query_service.py          # Text-to-SQL generation + execution
│   │   ├── relevance_validator.py    # 8-step query understanding pipeline
│   │   └── insights/                 # AI Insights Engine
│   │       ├── __init__.py
│   │       ├── insights_engine.py    # 12-section statistical analysis
│   │       └── README.md
│   │
│   ├── tests/                        # Unit tests
│   │
│   └── utils/                        # Utility functions
│       ├── __init__.py
│       ├── active_dataset_store.py   # Per-session SQLite management
│       ├── dataset_cache.py          # DataFrame caching
│       ├── db_utils.py               # Schema extraction, DB helpers
│       ├── file_utils.py             # File validation & reading
│       └── schema_detector.py        # Column type detection (NUM/TEXT/DATE)
│
├── frontend/                         # Frontend assets
│   ├── static/                       # Static files
│   │   ├── main.js                   # ALL client-side logic
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

### 3. Export Results
- Click the "Export" button below any query result
- Choose format: Excel (.xlsx), PDF (.pdf), Word (.docx), Image (.png/.jpg)
- For Dataset Overview: use the export dropdown at the bottom

---

## 🔌 API Endpoints

| Method | Endpoint | Description |
|--------|----------|-------------|
| `POST` | `/upload` | Upload CSV/Excel file |
| `POST` | `/query` | Natural language query |
| `GET` | `/schema` | Get dataset schema |
| `GET` | `/dataset-overview` | Get comprehensive dataset analysis |
| `GET` | `/dataset-overview/download/<fmt>` | Export overview report |
| `GET` | `/download/<fmt>` | Download query results |

---

## 🔮 Future Enhancements

### Short-Term
- [ ] Multi-file support: Allow uploading and joining multiple datasets
- [ ] User authentication: Login system with saved datasets per user
- [ ] Chat history: Persistent conversation history across sessions
- [ ] Advanced filtering: Date range pickers, numeric sliders for interactive filtering
- [ ] Real-time collaboration: WebSocket-based multi-user sessions

### Medium-Term
- [ ] Advanced visualizations: Heatmaps, box plots, waterfall charts, treemaps
- [ ] Dashboard builder: Create multi-chart dashboards with auto-refresh
- [ ] Python code export: Generate Python scripts for offline analysis
- [ ] Data pipeline automation: Schedule recurring uploads and reports
- [ ] Multi-language support: UI and query parsing in multiple languages

### Long-Term
- [ ] ML model integration: AutoML for predictive analytics
- [ ] Data storytelling: Auto-generate narrative report from dataset
- [ ] API access: RESTful API for external integrations
- [ ] Database connections: Direct connection to PostgreSQL, MySQL, BigQuery
- [ ] Enterprise SSO: SAML/OAuth integration
- [ ] Data governance: Audit trails, access control, data lineage

---

## 🤝 Contributing

Contributions are welcome! Please feel free to submit a Pull Request.

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/amazing-feature`)
3. Commit your changes (`git commit -m 'Add some amazing feature'`)
4. Push to the branch (`git push origin feature/amazing-feature`)
5. Open a Pull Request

---

## 📄 License

This project is licensed under the MIT License - see the LICENSE file for details.

---

## 🙏 Acknowledgments

- **Groq Inc.** for providing the LLM inference API
- **Chart.js** team for the excellent charting library
- All open-source libraries that made this project possible

---

<p align="center">
  <strong>PromptX</strong> — <em>Talk to your data. Get answers. No SQL needed.</em>
</p>