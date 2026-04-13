import os


class BaseConfig:
    """所有环境共用的基础配置。"""

    # Flask 密钥，用于 session 加密；生产环境必须通过环境变量覆盖
    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-please-change")

    # Redis 连接配置
    REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
    REDIS_DB = int(os.environ.get("REDIS_DB", 0))
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)  # 无密码时为 None

    # 消息频道与历史记录配置
    MESSAGE_CHANNEL = os.environ.get("MESSAGE_CHANNEL", "intellitrans:messages")     # Pub/Sub 频道名
    MESSAGE_HISTORY_KEY = os.environ.get("MESSAGE_HISTORY_KEY", "intellitrans:history")  # 历史记录 List 键名
    MESSAGE_HISTORY_MAX = int(os.environ.get("MESSAGE_HISTORY_MAX", 200))            # 最多保留的历史消息条数


class DevelopmentConfig(BaseConfig):
    """开发环境配置：开启调试模式。"""

    DEBUG = True


class ProductionConfig(BaseConfig):
    """生产环境配置：关闭调试模式，强制要求安全密钥。"""

    DEBUG = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    def validate(cls) -> None:
        """校验生产环境必填项，SECRET_KEY 不得使用默认开发值。"""
        import os

        if os.environ.get("SECRET_KEY", "dev-secret-key-please-change") == "dev-secret-key-please-change":
            raise RuntimeError(
                "生产环境必须通过环境变量 SECRET_KEY 设置一个安全随机密钥，"
                "请勿使用默认开发密钥。"
            )


class TestingConfig(BaseConfig):
    """测试环境配置：开启测试模式，使用独立的 Redis 数据库。"""

    TESTING = True
    DEBUG = True
    # 测试专用 Redis 数据库，避免污染开发数据
    REDIS_DB = int(os.environ.get("REDIS_TEST_DB", 15))


# 环境名称 → 配置类的映射表
_config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(env: str | None = None) -> type[BaseConfig]:
    """根据环境名称返回对应的配置类，未识别的名称回退到开发配置。"""
    env = env or os.environ.get("FLASK_ENV", "development")
    return _config_map.get(env, DevelopmentConfig)
