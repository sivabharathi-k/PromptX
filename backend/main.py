"""
Application entry point — creates the Flask app and starts the server.
"""

import logging
import os

from flask import Flask, render_template
from flask_session import Session

from backend.api.routes import api
from backend.config.settings import (
    DEBUG, HOST, PORT, SECRET_KEY,
    UPLOADS_DIR, EXPORTS_DIR, LOGS_DIR, SESSIONS_DIR,
)

FRONTEND_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "frontend")

# ── Logging ───────────────────────────────────────────────────
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S",
)
logger = logging.getLogger("app")


def create_app() -> Flask:
    """Factory function — creates and configures the Flask application."""
    for d in (UPLOADS_DIR, EXPORTS_DIR, LOGS_DIR, SESSIONS_DIR):
        os.makedirs(d, exist_ok=True)

    app = Flask(
        __name__,
        template_folder=os.path.join(FRONTEND_DIR, "templates"),
        static_folder=os.path.join(FRONTEND_DIR, "static"),
    )

    app.secret_key = SECRET_KEY

    # ── Server-side filesystem sessions (no cookie size limit) ──
    app.config["SESSION_TYPE"]           = "filesystem"
    app.config["SESSION_FILE_DIR"]       = SESSIONS_DIR
    app.config["SESSION_PERMANENT"]      = False
    app.config["SESSION_USE_SIGNER"]     = True
    app.config["SESSION_FILE_THRESHOLD"] = 500          # max session files on disk
    Session(app)

    app.register_blueprint(api)

    @app.route("/")
    def index():
        return render_template("index.html")

    logger.info("Server-side filesystem sessions configured at: %s", SESSIONS_DIR)
    return app


if __name__ == "__main__":
    app = create_app()
    print("\n" + "=" * 60)
    print(f"  App running at http://{HOST}:{PORT}")
    print("=" * 60)
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)
