import json
import logging
import re
import time
import uuid

from flask import current_app

from app.extensions import redis_client

# 使用模块名创建日志记录器，便于追踪来源
logger = logging.getLogger(__name__)

_ROOM_RE = re.compile(r"^[\w\u4e00-\u9fff-]{1,32}$")


def _history_key_for_room(room: str) -> str:
    """生成房间级历史记录键，避免不同房间相互污染。"""
    base_key: str = current_app.config["MESSAGE_HISTORY_KEY"]
    return f"{base_key}:{room}"


def _user_dm_rooms_key(username: str) -> str:
    prefix: str = current_app.config["USER_DM_ROOMS_PREFIX"]
    return f"{prefix}:{username}"


def _normalize_room_name(room_name: str) -> str:
    normalized = room_name.strip().replace(" ", "-")
    return normalized if _ROOM_RE.match(normalized) else ""


def _sorted_rooms(rooms: list[str]) -> list[str]:
    return sorted(rooms, key=lambda item: (item != "general", item))


def ensure_default_group_rooms() -> list[str]:
    """初始化默认群聊房间并返回房间列表。"""
    registry_key: str = current_app.config["ROOM_REGISTRY_KEY"]
    defaults_raw: str = current_app.config["DEFAULT_GROUP_ROOMS"]

    defaults: list[str] = []
    for room in defaults_raw.split(","):
        normalized = _normalize_room_name(room)
        if normalized:
            defaults.append(normalized)
    if "general" not in defaults:
        defaults.insert(0, "general")

    if defaults:
        redis_client.sadd(registry_key, *defaults)
    return list_group_rooms()


def list_group_rooms() -> list[str]:
    """返回所有群聊会话名。"""
    registry_key: str = current_app.config["ROOM_REGISTRY_KEY"]
    rooms = [room for room in redis_client.smembers(registry_key) if isinstance(room, str)]
    if not rooms:
        return ensure_default_group_rooms()
    return _sorted_rooms(rooms)


def is_group_room_exists(room: str) -> bool:
    """判断群聊会话是否存在。"""
    registry_key: str = current_app.config["ROOM_REGISTRY_KEY"]
    return bool(redis_client.sismember(registry_key, room))


def create_group_room(room_name: str) -> str:
    """创建群聊会话，返回规范房间名。"""
    normalized = _normalize_room_name(room_name)
    if not normalized:
        raise ValueError("房间名不合法，仅支持中英文、数字、下划线和连字符，长度 1-32")

    registry_key: str = current_app.config["ROOM_REGISTRY_KEY"]
    redis_client.sadd(registry_key, normalized)
    return normalized


def delete_group_room(room: str) -> bool:
    """删除群聊会话及其历史消息。"""
    if room == "general":
        raise ValueError("大厅会话不允许删除")

    registry_key: str = current_app.config["ROOM_REGISTRY_KEY"]
    removed = redis_client.srem(registry_key, room)
    if removed:
        redis_client.delete(_history_key_for_room(room))
    return bool(removed)


def add_private_room_for_users(room: str, username_a: str, username_b: str) -> None:
    """将私聊会话写入双方会话集合。"""
    for username in {username_a, username_b}:
        redis_client.sadd(_user_dm_rooms_key(username), room)


def list_private_rooms(username: str) -> list[str]:
    """返回用户私聊会话列表。"""
    rooms = [room for room in redis_client.smembers(_user_dm_rooms_key(username)) if isinstance(room, str)]
    return sorted(rooms)


def delete_private_room(room: str, operator: str) -> bool:
    """删除私聊会话：操作人必须是会话成员，删除后双方都不可见。"""
    if not room.startswith("dm:"):
        raise ValueError("仅支持删除私聊会话")

    members = room[3:].split("|")
    if len(members) != 2 or operator not in members:
        raise ValueError("无权删除该私聊会话")

    removed_count = 0
    for username in members:
        removed_count += int(redis_client.srem(_user_dm_rooms_key(username), room))

    if removed_count:
        redis_client.delete(_history_key_for_room(room))
    return bool(removed_count)


def publish_message(
    username: str,
    text: str,
    room: str = "general",
    extras: dict | None = None,
) -> dict:
    """将聊天消息发布到 Redis Pub/Sub 频道，并追加到历史记录列表。

    返回已发布的消息字典。
    """
    # 构造消息体
    message = {
        "id": str(uuid.uuid4()),
        "username": username,
        "text": text,
        "room": room,
        "timestamp": time.time(),  # Unix 时间戳（秒）
    }
    if extras:
        message.update(extras)
    # 序列化为 JSON 字符串，ensure_ascii=False 保留中文字符
    payload = json.dumps(message, ensure_ascii=False)

    channel: str = current_app.config["MESSAGE_CHANNEL"]
    history_key = _history_key_for_room(room)
    max_history: int = current_app.config["MESSAGE_HISTORY_MAX"]

    # 发布消息到 Pub/Sub 频道，所有订阅者（在线用户）将实时收到
    redis_client.publish(channel, payload)
    # 将消息追加到历史记录列表的右端
    redis_client.rpush(history_key, payload)
    # 裁剪列表，仅保留最新的 max_history 条记录，防止无限增长
    redis_client.ltrim(history_key, -max_history, -1)

    return message


def get_history(room: str | None = None, limit: int | None = None) -> list[dict]:
    """从 Redis 获取历史消息（按时间从旧到新排列）。

    若指定了 room，则只返回该房间的消息；否则返回所有房间的消息。
    """
    if room:
        history_key = _history_key_for_room(room)
        if limit and limit > 0:
            raw_messages: list[str] = redis_client.lrange(history_key, -limit, -1)
        else:
            raw_messages = redis_client.lrange(history_key, 0, -1)
    else:
        # 保留兼容：未传 room 时从旧全局 key 读取。
        history_key: str = current_app.config["MESSAGE_HISTORY_KEY"]
        raw_messages = redis_client.lrange(history_key, 0, -1)

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
