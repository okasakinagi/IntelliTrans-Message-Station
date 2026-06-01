"""测试共用夹具（fixtures）。"""

import pytest

from app import create_app


@pytest.fixture
def app():
    """创建测试 Flask 应用，使用独立的 Redis DB 9，避免污染开发数据。"""
    import os

    from app.config import DevelopmentConfig

    # 直接覆写配置类属性（类属性在定义时已计算，os.environ 无效）
    DevelopmentConfig.REDIS_DB = 9
    DevelopmentConfig.WORKFLOW_ENABLED = False
    os.environ["SECRET_KEY"] = "test-secret"

    _app = create_app(env="development")
    _app.config["TESTING"] = True

    # 清空测试 DB
    redis = _app.extensions["redis"]
    redis.flushdb()

    yield _app

    # 测试结束后再次清空
    redis.flushdb()


@pytest.fixture
def redis_client(app):
    """返回测试用的 Redis 客户端。"""
    return app.extensions["redis"]


@pytest.fixture
def app_context(app):
    """推送应用上下文，让 current_app 可用。"""
    with app.app_context():
        yield
