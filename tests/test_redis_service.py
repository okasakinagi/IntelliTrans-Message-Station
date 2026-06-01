"""redis_service 模块的单元测试。

需要本地 Redis（默认 127.0.0.1:6379），测试使用 DB 9 避免污染开发数据。
"""

import time

from app.services.redis_service import (
    add_private_room_for_users,
    create_group_room,
    delete_group_room,
    delete_private_room,
    ensure_default_group_rooms,
    get_history,
    get_online_users,
    is_group_room_exists,
    is_user_online,
    list_group_rooms,
    list_private_rooms,
    mark_user_online,
    publish_message,
    remove_user_online,
)


class TestGroupRooms:
    """群聊房间管理测试。"""

    def test_ensure_default_rooms(self, app_context):
        rooms = ensure_default_group_rooms()
        assert "general" in rooms
        assert "tech" in rooms
        assert "random" in rooms
        assert rooms[0] == "general"  # general 始终排第一

    def test_create_and_delete_room(self, app_context):
        name = create_group_room("test-room")
        assert name == "test-room"
        assert is_group_room_exists("test-room")

        assert delete_group_room("test-room")
        assert not is_group_room_exists("test-room")

    def test_create_invalid_room_name(self, app_context):
        import pytest

        with pytest.raises(ValueError):
            create_group_room("")
        with pytest.raises(ValueError):
            create_group_room("a" * 33)  # too long
        with pytest.raises(ValueError):
            create_group_room("hello world!")  # invalid chars

    def test_cannot_delete_general(self, app_context):
        import pytest

        ensure_default_group_rooms()
        with pytest.raises(ValueError, match="大厅"):
            delete_group_room("general")

    def test_list_group_rooms_sorted(self, app_context):
        ensure_default_group_rooms()
        create_group_room("alpha")
        create_group_room("beta")
        rooms = list_group_rooms()
        # general 始终排第一
        assert rooms[0] == "general"


class TestPrivateRooms:
    """私聊房间管理测试。"""

    def test_add_and_list_private_rooms(self, app_context):
        add_private_room_for_users("dm:alice|bob", "alice", "bob")
        assert "dm:alice|bob" in list_private_rooms("alice")
        assert "dm:alice|bob" in list_private_rooms("bob")

    def test_delete_private_room(self, app_context):
        add_private_room_for_users("dm:alice|bob", "alice", "bob")
        assert delete_private_room("dm:alice|bob", operator="alice")
        assert "dm:alice|bob" not in list_private_rooms("alice")
        assert "dm:alice|bob" not in list_private_rooms("bob")

    def test_delete_private_room_unauthorized(self, app_context):
        import pytest

        add_private_room_for_users("dm:alice|bob", "alice", "bob")
        with pytest.raises(ValueError, match="无权"):
            delete_private_room("dm:alice|bob", operator="charlie")


class TestMessages:
    """消息发布与历史记录测试。"""

    def test_publish_and_get_history(self, app_context):
        msg1 = publish_message("alice", "Hello", room="general")
        msg2 = publish_message("bob", "Hi there", room="general")

        history = get_history(room="general")
        assert len(history) >= 2

        # 验证消息字段完整性
        last = history[-1]
        assert last["username"] == "bob"
        assert last["text"] == "Hi there"
        assert last["room"] == "general"
        assert "id" in last
        assert "timestamp" in last

    def test_history_with_limit(self, app_context):
        for i in range(10):
            publish_message("user", f"msg-{i}", room="general")

        history = get_history(room="general", limit=3)
        assert len(history) == 3
        assert history[-1]["text"] == "msg-9"

    def test_history_room_isolation(self, app_context):
        publish_message("alice", "in general", room="general")
        publish_message("alice", "in tech", room="tech")

        general_history = get_history(room="general")
        tech_history = get_history(room="tech")

        texts = [m["text"] for m in general_history]
        assert "in general" in texts
        assert "in tech" not in texts

    def test_publish_with_extras(self, app_context):
        msg = publish_message("alice", "Bonjour", room="general", extras={"translated_text": "Hello"})
        assert msg["translated_text"] == "Hello"


class TestOnlinePresence:
    """Redis 在线用户 Presence 测试。"""

    def test_mark_and_check_online(self, app_context):
        mark_user_online("alice")
        assert is_user_online("alice")
        assert "alice" in get_online_users()

    def test_remove_online(self, app_context):
        mark_user_online("alice")
        remove_user_online("alice")
        assert not is_user_online("alice")

    def test_online_users_sorted(self, app_context):
        mark_user_online("charlie")
        mark_user_online("alice")
        mark_user_online("bob")
        users = get_online_users()
        assert users == ["alice", "bob", "charlie"]

    def test_ttl_expiry(self, app, app_context):
        """验证 TTL 过期（需要等待，在 CI 中可能较慢）。"""
        app.config["ONLINE_USER_TTL"] = 1

        mark_user_online("expire-test")
        assert is_user_online("expire-test")

        time.sleep(2)
        assert not is_user_online("expire-test")
