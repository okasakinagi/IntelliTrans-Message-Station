import json
import logging
import time

from flask import current_app

from app.extensions import redis_client

logger = logging.getLogger(__name__)


def publish_message(username: str, text: str, room: str = "general") -> dict:
    """Publish a chat message to the Redis pub/sub channel and append it to
    the history list.

    Returns the serialised message dict that was published.
    """
    message = {
        "username": username,
        "text": text,
        "room": room,
        "timestamp": time.time(),
    }
    payload = json.dumps(message, ensure_ascii=False)

    channel: str = current_app.config["MESSAGE_CHANNEL"]
    history_key: str = current_app.config["MESSAGE_HISTORY_KEY"]
    max_history: int = current_app.config["MESSAGE_HISTORY_MAX"]

    redis_client.publish(channel, payload)
    redis_client.rpush(history_key, payload)
    redis_client.ltrim(history_key, -max_history, -1)

    return message


def get_history(room: str | None = None) -> list[dict]:
    """Return persisted message history (newest last).

    If *room* is provided only messages for that room are returned.
    """
    history_key: str = current_app.config["MESSAGE_HISTORY_KEY"]
    raw_messages: list[str] = redis_client.lrange(history_key, 0, -1)

    messages = []
    for raw in raw_messages:
        try:
            msg = json.loads(raw)
        except json.JSONDecodeError:
            logger.warning("Skipping malformed JSON entry in Redis history: %r", raw)
            continue
        if room is None or msg.get("room") == room:
            messages.append(msg)
    return messages
