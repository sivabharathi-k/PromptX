"""
Application entry point — creates the Flask app and starts the server.
Enterprise-grade hardening with global error handlers and zero-failure architecture.
"""
from __future__ import annotations

import logging
import os
import traceback

from flask import Flask, jsonify, render_template
from flask_session import Session

from backend.api.routes import api
from backend.config.settings import (
    DEBUG, HOST, PORT, SECRET_KEY,
    UPLOADS_DIR, EXPORTS_DIR, LOGS_DIR, SESSIONS_DIR,
)
from backend.error_handler import safe_route

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

    # ── Enterprise Global Error Handlers ──────────────────────
    @app.errorhandler(400)
    def bad_request(e):
        logger.warning("400 Bad Request: %s", str(e))
        return jsonify({"error": "Bad request. Please check your input.", "success": False}), 400

    @app.errorhandler(404)
    def not_found(e):
        logger.warning("404 Not Found: %s", str(e))
        return jsonify({"error": "The requested resource was not found.", "success": False}), 404

    @app.errorhandler(405)
    def method_not_allowed(e):
        logger.warning("405 Method Not Allowed: %s", str(e))
        return jsonify({"error": "Method not allowed.", "success": False}), 405

    @app.errorhandler(413)
    def payload_too_large(e):
        logger.warning("413 Payload Too Large: %s", str(e))
        return jsonify({"error": "File too large. Please upload a smaller file.", "success": False}), 413

    @app.errorhandler(422)
    def unprocessable_entity(e):
        logger.warning("422 Unprocessable Entity: %s", str(e))
        return jsonify({"error": "Unprocessable request.", "success": False}), 422

    @app.errorhandler(429)
    def too_many_requests(e):
        logger.warning("429 Too Many Requests")
        return jsonify({"error": "Too many requests. Please wait a moment.", "success": False}), 429

    @app.errorhandler(500)
    def internal_error(e):
        tb = traceback.format_exc()
        logger.critical("500 Internal Server Error: %s\n%s", str(e), tb)
        return jsonify({
            "error": "An internal server error occurred. Please try again.",
            "success": False,
        }), 500

    # ── Catch-all for any unhandled exception ──
    @app.errorhandler(Exception)
    def unhandled_exception(e):
        tb = traceback.format_exc()
        logger.critical("UNHANDLED EXCEPTION: %s\n%s", str(e), tb)
        return jsonify({
            "error": "An unexpected error occurred. Please try again.",
            "success": False,
        }), 500

    # ── Register Blueprints ──
    app.register_blueprint(api)

    @app.route("/")
    @safe_route
    def index():
        return render_template("index.html")

    logger.info("Server-side filesystem sessions configured at: %s", SESSIONS_DIR)
    logger.info("Enterprise error handlers active.")
    return app


if __name__ == "__main__":
    app = create_app()
    print("\n" + "=" * 60)
    print(f"  App running at http://{HOST}:{PORT}")
    print("=" * 60)
    app.run(host=HOST, port=PORT, debug=DEBUG, use_reloader=False)