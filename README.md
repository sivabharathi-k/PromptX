# Text to Excel

A production-ready Text-to-SQL web application that allows users to upload a CSV dataset, ask questions in plain English, and download the results as an Excel file.

## How It Works

1. User uploads a CSV file
2. The dataset is loaded into a SQLite database
3. The user's question is converted to SQL using Groq (LLM)
4. SQL is executed on the dataset
5. Results are displayed in a table and available for Excel download

## Project Structure

```
Internship_project/
├── backend/
│   ├── api/
│   │   └── routes.py          # All HTTP API endpoints (Flask Blueprint)
│   ├── config/
│   │   └── settings.py        # Centralized configuration
│   ├── data/
│   │   ├── uploads/           # Uploaded datasets and SQLite DB
│   │   ├── exports/           # Generated Excel exports
│   │   └── logs/              # Application logs
│   ├── models/                # Data models (reserved for future use)
│   ├── services/
│   │   ├── export_service.py  # Excel export logic
│   │   └── query_service.py   # SQL generation (Groq) and execution
│   ├── utils/
│   │   ├── db_utils.py        # SQLite connection and schema helpers
│   │   └── file_utils.py      # File validation and CSV reading
│   └── main.py                # App factory and server entry point
├── frontend/
│   ├── static/
│   │   ├── main.js            # Frontend interactivity
│   │   └── style.css          # All styles
│   └── templates/
│       └── index.html         # Main UI template
├── .env                       # Environment variables (not committed)
├── .gitignore
├── requirements.txt
└── README.md
```

## Setup

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Create a .env file in the project root
echo GROQ_API_KEY=your_key_here > .env

# 3. Run the application
python -m backend.main
```

## Environment Variables

| Variable      | Default              | Description                   |
|---------------|----------------------|-------------------------------|
| GROQ_API_KEY  | required             | Your Groq API key             |
| GROQ_MODEL    | llama-3.1-8b-instant | Groq model name               |
| HOST          | 127.0.0.1            | Server host                   |
| PORT          | 8080                 | Server port                   |
| DEBUG         | true                 | Enable Flask debug mode       |
| SECRET_KEY    | dev-secret-key       | Flask session secret key      |

## API Endpoints

| Method | Endpoint        | Description                        |
|--------|-----------------|------------------------------------|
| GET    | /               | Serve the main UI                  |
| POST   | /upload         | Upload and validate a CSV file     |
| POST   | /query          | Run a natural language query       |
| GET    | /download-excel | Download last result as Excel      |
