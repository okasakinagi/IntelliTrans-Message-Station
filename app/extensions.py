import redis
from flask_login import LoginManager
from flask_socketio import SocketIO

# Socket.IO 实例：在应用工厂中通过 init_app 完成初始化
socketio = SocketIO()

# Flask-Login 管理器：处理用户认证状态
login_manager = LoginManager()

# 模块级 Redis 客户端；在 create_app 中通过 init_redis() 初始化
redis_client: redis.Redis | None = None


def init_redis(app) -> redis.Redis:
    """根据应用配置创建 Redis 客户端，并将其注册到 app.extensions 中。"""
    global redis_client
    redis_client = redis.Redis(
        host=app.config["REDIS_HOST"],
        port=app.config["REDIS_PORT"],
        db=app.config["REDIS_DB"],
        password=app.config["REDIS_PASSWORD"],
        decode_responses=True,  # 自动将字节解码为字符串
    )
    # 挂载到 Flask 扩展字典，方便其他模块通过 app.extensions["redis"] 访问
    app.extensions["redis"] = redis_client
    return redis_client
