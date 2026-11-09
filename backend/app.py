# backend/app.py
from __future__ import annotations

import logging
import os
import time

from flask import Flask, g, request
from flask_cors import CORS
from werkzeug.middleware.proxy_fix import ProxyFix

from config import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s: %(message)s",
)
log = logging.getLogger("spotty")


def create_app(testing: bool = False) -> Flask:
    app = Flask(__name__)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    app.config["SECRET_KEY"] = settings.secret_key
    app.config["MAX_CONTENT_LENGTH"] = settings.max_upload_mb * 1024 * 1024
    app.config["TESTING"] = testing
    app.config["JSON_SORT_KEYS"] = False

    CORS(
        app,
        resources={r"/api/*": {"origins": settings.cors_origins}, r"/login": {"origins": settings.cors_origins}},
        supports_credentials=False,
        expose_headers=["X-RateLimit-Limit", "X-RateLimit-Remaining", "Retry-After"],
    )

    from extensions import limiter

    limiter.init_app(app)
    if testing:
        limiter.enabled = False

    if settings.tesseract_cmd:
        try:
            import pytesseract

            pytesseract.pytesseract.tesseract_cmd = settings.tesseract_cmd
        except Exception as e:  # pragma: no cover
            log.warning("pytesseract not available: %s", e)

    from db import init_db

    init_db()

    from routes.auth import auth_bp
    from routes.generate import generate_bp
    from routes.scan import scan_bp
    from routes.spotify import spotify_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(spotify_bp)
    app.register_blueprint(scan_bp)
    app.register_blueprint(generate_bp)

    # --- request logging + security headers --------------------------------

    @app.before_request
    def _start_timer():
        g._t0 = time.perf_counter()

    @app.after_request
    def _finish(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "strict-origin-when-cross-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        t0 = getattr(g, "_t0", None)
        if t0 is not None and request.path.startswith("/api") and not request.path.startswith("/api/audio"):
            ms = (time.perf_counter() - t0) * 1000
            if ms > 500 or resp.status_code >= 400:
                log.info("%s %s -> %s (%.0f ms)", request.method, request.path, resp.status_code, ms)
        return resp

    # --- health -----------------------------------------------------------

    @app.get("/")
    def root():
        return {"ok": True, "service": "trill-backend", "version": "2.0.0"}

    @app.get("/api/health/live")
    def live():
        return {"ok": True}

    @app.get("/api/health/ready")
    def ready():
        from sqlalchemy import text as sa_text

        from db import SessionLocal
        from services import llm
        from services.acestep_client import acestep

        db_ok = True
        try:
            db = SessionLocal()
            db.execute(sa_text("SELECT 1"))
            db.close()
        except Exception as e:
            db_ok = False
            log.warning("DB not ready: %s", e)
        body = {"ok": db_ok, "db": db_ok, "acestep": acestep.health_check(), "llm": llm.status()}
        return body, (200 if db_ok else 500)

    # --- errors -------------------------------------------------------------

    @app.errorhandler(413)
    def too_big(e):
        return {"error": "payload_too_large", "limit_mb": settings.max_upload_mb}, 413

    @app.errorhandler(404)
    def not_found(e):
        return {"error": "not_found"}, 404

    @app.errorhandler(405)
    def not_allowed(e):
        return {"error": "method_not_allowed"}, 405

    @app.errorhandler(429)
    def rate_limited(e):
        return {"error": "rate_limited", "message": "Slow down a little.", "detail": str(getattr(e, "description", ""))}, 429

    @app.errorhandler(Exception)
    def internal(e):
        log.exception("Unhandled error")
        return {"error": "server_error"}, 500

    # --- background worker --------------------------------------------------

    if settings.worker_enabled and not testing and os.getenv("WERKZEUG_RUN_MAIN", "true") == "true":
        from services import worker

        worker.start()

    return app


app = create_app()

if __name__ == "__main__":
    # use_reloader=False so the completion worker thread isn't started twice
    app.run(host=settings.app_host, port=settings.app_port, debug=not settings.is_production, use_reloader=False)
