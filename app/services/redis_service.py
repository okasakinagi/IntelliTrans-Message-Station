import json
import logging
import time

from flask import current_app

from app.extensions import redis_client

# 使用模块名创建日志记录器，便于追踪来源
logger = logging.getLogger(__name__)


def publish_message(username: str, text: str, room: str = "general") -> dict:
    """将聊天消息发布到 Redis Pub/Sub 频道，并追加到历史记录列表。

    返回已发布的消息字典。
    """
    # 构造消息体
    message = {
        "username": username,
        "text": text,
        "room": room,
        "timestamp": time.time(),  # Unix 时间戳（秒）
    }
    # 序列化为 JSON 字符串，ensure_ascii=False 保留中文字符
    payload = json.dumps(message, ensure_ascii=False)

    channel: str = current_app.config["MESSAGE_CHANNEL"]
    history_key: str = current_app.config["MESSAGE_HISTORY_KEY"]
    max_history: int = current_app.config["MESSAGE_HISTORY_MAX"]

    # 发布消息到 Pub/Sub 频道，所有订阅者（在线用户）将实时收到
    redis_client.publish(channel, payload)
    # 将消息追加到历史记录列表的右端
    redis_client.rpush(history_key, payload)
    # 裁剪列表，仅保留最新的 max_history 条记录，防止无限增长
    redis_client.ltrim(history_key, -max_history, -1)

    return message


def get_history(room: str | None = None) -> list[dict]:
    """从 Redis 获取历史消息（按时间从旧到新排列）。

    若指定了 room，则只返回该房间的消息；否则返回所有房间的消息。
    """
    history_key: str = current_app.config["MESSAGE_HISTORY_KEY"]
    # 取出列表中所有元素（0 到 -1 表示全部）
    raw_messages: list[str] = redis_client.lrange(history_key, 0, -1)

    messages = []
    for raw in raw_messages:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            # 记录损坏的 JSON 条目，便于运维排查数据质量问题
            logger.warning("跳过 Redis 历史记录中格式错误的 JSON 条目: %r", raw)
            continue
        # 按房间过滤
        if room is None or msg.get("room") == room:
            messages.append(msg)
    return messages
