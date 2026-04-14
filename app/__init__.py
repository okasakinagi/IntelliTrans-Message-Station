from pathlib import Path

from dotenv import load_dotenv
from flask import Flask, redirect, url_for
from flask_login import current_user

# 在导入 app.config 之前加载 .env，避免配置类在导入时读取到旧环境变量。
_project_root = Path(__file__).resolve().parent.parent
_dotenv_path = _project_root / ".env"
if _dotenv_path.exists():
    load_dotenv(dotenv_path=_dotenv_path, override=True)

from app.config import get_config
from app.extensions import init_redis, login_manager, socketio


def create_app(env: str | None = None) -> Flask:
    """Flask 应用工厂函数。

    参数
    ----------
    env:
        可选的环境名称（``"development"``、``"production"``、``"testing"``）。
        默认读取 ``FLASK_ENV`` 环境变量，未设置时回退到 ``"development"``。
    """
    app = Flask(__name__)
    # 根据环境名称加载对应的配置类
    app.config.from_object(get_config(env))

    if app.config.get("WORKFLOW_ENABLED") and (
        not app.config.get("WORKFLOW_API_URL") or not app.config.get("WORKFLOW_API_TOKEN")
    ):
        app.logger.warning(
            "工作流已启用但缺少 WORKFLOW_API_URL 或 WORKFLOW_API_TOKEN，"
            "消息将按降级策略处理。"
        )

    # ------------------------------------------------------------------
    # 初始化扩展
    # ------------------------------------------------------------------
    # 初始化 Redis 客户端，并挂载到 app.extensions["redis"]
    init_redis(app)
    # 初始化 Socket.IO，使用 Redis 作为消息队列以支持多进程广播
    socketio.init_app(
        app,
        message_queue=_redis_url(app),
        async_mode="eventlet",
        cors_allowed_origins="*",
    )
    # 初始化 Flask-Login，未登录时跳转到登录页
    login_manager.init_app(app)
    login_manager.login_view = "auth.login"

    # ------------------------------------------------------------------
    # 注册蓝图（路由模块）
    # ------------------------------------------------------------------
    from app.routes.main import bp as main_bp
    from app.routes.messages import bp as messages_bp
    from app.routes.auth import bp as auth_bp

    app.register_blueprint(main_bp)       # 首页路由
    app.register_blueprint(messages_bp)   # 消息相关路由（REST + Socket.IO）
    app.register_blueprint(auth_bp)       # 认证路由（登录/登出）

    # ------------------------------------------------------------------
    # 全局请求钩子：未登录用户强制跳转登录页
    # ------------------------------------------------------------------
    @app.before_request
    def require_login():
        from flask import request

        # Socket.IO 握手与轮询路径不走 Flask 普通页面鉴权分支。
        if request.path.startswith("/socket.io"):
            return None

        # 无需登录即可访问的端点
        open_endpoints = {"auth.login", "static"}
        if not current_user.is_authenticated and request.endpoint not in open_endpoints:
            return redirect(url_for("auth.login"))

    return app


def _redis_url(app: Flask) -> str:
    """根据配置拼接 Redis 连接 URL，供 Socket.IO 消息队列使用。"""
    host = app.config["REDIS_HOST"]
    port = app.config["REDIS_PORT"]
    db = app.config["REDIS_DB"]
    password = app.config["REDIS_PASSWORD"]
    if password:
        return f"redis://:{password}@{host}:{port}/{db}"
    return f"redis://{host}:{port}/{db}"
