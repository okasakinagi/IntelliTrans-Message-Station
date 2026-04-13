import os


class BaseConfig:
    """Base configuration shared by all environments."""

    SECRET_KEY = os.environ.get("SECRET_KEY", "dev-secret-key-please-change")

    # Redis
    REDIS_HOST = os.environ.get("REDIS_HOST", "127.0.0.1")
    REDIS_PORT = int(os.environ.get("REDIS_PORT", 6379))
    REDIS_DB = int(os.environ.get("REDIS_DB", 0))
    REDIS_PASSWORD = os.environ.get("REDIS_PASSWORD", None)

    # Message settings
    MESSAGE_CHANNEL = os.environ.get("MESSAGE_CHANNEL", "intellitrans:messages")
    MESSAGE_HISTORY_KEY = os.environ.get("MESSAGE_HISTORY_KEY", "intellitrans:history")
    MESSAGE_HISTORY_MAX = int(os.environ.get("MESSAGE_HISTORY_MAX", 200))


class DevelopmentConfig(BaseConfig):
    DEBUG = True


class ProductionConfig(BaseConfig):
    DEBUG = False

    def __init_subclass__(cls, **kwargs):
        super().__init_subclass__(**kwargs)

    @classmethod
    def validate(cls) -> None:
        import os

        if os.environ.get("SECRET_KEY", "dev-secret-key-please-change") == "dev-secret-key-please-change":
            raise RuntimeError(
                "SECRET_KEY must be set to a secure random value in production. "
                "Set the SECRET_KEY environment variable."
            )


class TestingConfig(BaseConfig):
    TESTING = True
    DEBUG = True
    REDIS_DB = int(os.environ.get("REDIS_TEST_DB", 15))


_config_map = {
    "development": DevelopmentConfig,
    "production": ProductionConfig,
    "testing": TestingConfig,
}


def get_config(env: str | None = None) -> type[BaseConfig]:
    """Return the configuration class for the given environment name."""
    env = env or os.environ.get("FLASK_ENV", "development")
    return _config_map.get(env, DevelopmentConfig)
