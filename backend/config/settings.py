"""
Application configuration — all settings loaded from environment variables.
"""

import os
from dotenv import load_dotenv

load_dotenv()

# ── Server ────────────────────────────────────────────────────
HOST = os.environ.get("HOST", "127.0.0.1")
PORT = int(os.environ.get("PORT", 8080))
DEBUG = os.environ.get("DEBUG", "true").lower() == "true"

# ── Security ──────────────────────────────────────────────────
SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key")

# ── Groq ──────────────────────────────────────────────────────
GROQ_API_KEY = os.environ["GROQ_API_KEY"]
GROQ_MODEL   = os.environ.get("GROQ_MODEL", "llama-3.1-8b-instant")

# ── Paths ─────────────────────────────────────────────────────
BACKEND_DIR  = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # backend/
DATA_DIR     = os.path.join(BACKEND_DIR, "data")
UPLOADS_DIR  = os.path.join(DATA_DIR, "uploads")
EXPORTS_DIR  = os.path.join(DATA_DIR, "exports")
LOGS_DIR     = os.path.join(DATA_DIR, "logs")
SESSIONS_DIR = os.path.join(DATA_DIR, "sessions")

# ── Upload ────────────────────────────────────────────────────
ALLOWED_EXTENSIONS = {"csv"}
MAX_ROWS_IN_SESSION = 50_000
