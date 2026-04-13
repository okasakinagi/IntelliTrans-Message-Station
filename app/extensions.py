import redis
from flask_login import LoginManager
from flask_socketio import SocketIO

socketio = SocketIO()
login_manager = LoginManager()

# Module-level Redis client; initialised in create_app via init_redis().
redis_client: redis.Redis | None = None


def init_redis(app) -> redis.Redis:
    """Create and store the Redis client on *app* and in this module."""
    global redis_client
    redis_client = redis.Redis(
        host=app.config["REDIS_HOST"],
        port=app.config["REDIS_PORT"],
        db=app.config["REDIS_DB"],
        password=app.config["REDIS_PASSWORD"],
        decode_responses=True,
    )
    app.extensions["redis"] = redis_client
    return redis_client
