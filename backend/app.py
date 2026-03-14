# backend/app.py
from __future__ import annotations

import logging

import pytesseract
from flask import Flask
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from config import settings

log = logging.getLogger("spotty")
logging.basicConfig(level=logging.INFO)


def create_app() -> Flask:
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app)
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024

    CORS(
        app,
        resources={r"/api/*": {"origins": settings.cors_origins}},
        supports_credentials=False,
    )

    if settings.tesseract_cmd:
        pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd

    # Create tables
    from db import init_db
    init_db()

    # Register blueprints
    from routes.auth import auth_bp
    from routes.spotify import spotify_bp
    from routes.scan import scan_bp
    from routes.generate import generate_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(spotify_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(generate_bp)

    # Health checks
    @app.get("/")
    def root():
        return {"ok": True, "service": "spotty-backend"}

    @app.get("/api/health/live")
    def live():
        return {"ok": True}

    @app.get("/api/health/ready")
    def ready():
        from db import SessionLocal
        from sqlalchemy import text as sa_text
        try:
            db = SessionLocal()
            db.execute(sa_text("SELECT 1"))
            db.close()
            return {"ok": True}
        except Exception as e:
            return {"ok": False, "error": str(e)}, 500

    # Error handlers
    @app.errorhandler(413)
    def too_big(e):
        return {"error": "payload_too_large", "limit_mb": settings.max_upload_mb}, 413

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "not_found"}, 404

    @app.errorhandler(Exception)
    def internal(e):
        log.exception("Unhandled error")
        return {"error": "server_error"}, 500

    return app


app = create_app()

if __name__ == "__main__":
    app.run(host=settings.app_host, port=settings.app_port, debug=True)
