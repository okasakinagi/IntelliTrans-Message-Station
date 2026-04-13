from flask import Flask, redirect, url_for
from flask_login import current_user

from app.config import get_config
from app.extensions import init_redis, login_manager, socketio


def create_app(env: str | None = None) -> Flask:
    """Application factory.

    Parameters
    ----------
    env:
        Optional environment name (``"development"``, ``"production"``,
        ``"testing"``).  Defaults to the ``FLASK_ENV`` environment variable.
    """
    # Load .env only in non-production environments; production deployments
    # should inject environment variables through the process environment.
    import os
    from dotenv import load_dotenv

    if os.environ.get("FLASK_ENV") != "production":
        load_dotenv()

    app = Flask(__name__)
    app.config.from_object(get_config(env))

    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    init_redis(app)
    socketio.init_app(
        app,
        message_queue=_redis_url(app),
        async_mode="eventlet",
        cors_allowed_origins="*",
    )
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # ------------------------------------------------------------------
    # Blueprints
    # ------------------------------------------------------------------
    from app.routes.main import bp as main_bp
    from app.routes.messages import bp as messages_bp
    from app.routes.auth import bp as auth_bp

    app.register_blueprint(main_bp)
    app.register_blueprint(messages_bp)
    app.register_blueprint(auth_bp)

    # ------------------------------------------------------------------
    # Root redirect for unauthenticated users
    # ------------------------------------------------------------------
    @app.before_request
    def require_login():
        from flask import request

        open_endpoints = {"auth.login", "static"}
        if not current_user.is_authenticated and request.endpoint not in open_endpoints:
            return redirect(url_for("auth.login"))

    return app


def _redis_url(app: Flask) -> str:
    host = app.config["REDIS_HOST"]
    port = app.config["REDIS_PORT"]
    db = app.config["REDIS_DB"]
    password = app.config["REDIS_PASSWORD"]
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"
