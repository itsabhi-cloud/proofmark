"""Proofmark: evidence-backed brand governance before publication."""
import os
import secrets

from flask import Flask, send_from_directory

from .db import close_db, connect, init_schema


def create_app(test_config=None):
    app = Flask(__name__, static_folder="static", static_url_path="/static")
    app.config.update(
        SECRET_KEY=os.environ.get("SECRET_KEY") or secrets.token_hex(32),
        DB_PATH=os.environ.get("DB_PATH", os.path.join(app.instance_path, "proofmark.db")),
        MAX_CONTENT_LENGTH=3 * 1024 * 1024,
        SESSION_COOKIE_HTTPONLY=True,
        SESSION_COOKIE_SAMESITE="Lax",
        SESSION_COOKIE_SECURE=os.environ.get("SECURE_COOKIES", "") == "1",
        JSON_SORT_KEYS=False,
    )
    if test_config:
        app.config.update(test_config)

    with app.app_context():
        conn = connect(app.config["DB_PATH"])
        init_schema(conn)
        if conn.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
            from .seed import seed
            seed(conn)
        conn.close()

    from .api import bp
    app.register_blueprint(bp)
    app.teardown_appcontext(close_db)

    @app.get("/healthz")
    def health():
        return {"ok": True}

    @app.get("/")
    @app.get("/<path:path>")
    def spa(path=""):
        if path.startswith("api/"):
            return {"error": "Not found"}, 404
        return send_from_directory(app.static_folder, "index.html")

    @app.after_request
    def headers(resp):
        resp.headers.setdefault("X-Content-Type-Options", "nosniff")
        resp.headers.setdefault("Referrer-Policy", "same-origin")
        resp.headers.setdefault("X-Frame-Options", "DENY")
        return resp

    return app
