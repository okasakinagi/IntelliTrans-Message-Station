from collections import defaultdict
import time

from flask import Blueprint, current_app, jsonify, request
from flask_login import current_user, login_required
from flask_socketio import emit, join_room, leave_room

from app.extensions import socketio
from app.services.redis_service import (
    add_private_room_for_users,
    create_group_room,
    delete_group_room,
    delete_private_room,
    ensure_default_group_rooms,
    get_history,
    is_group_room_exists,
    list_group_rooms,
    list_private_rooms,
    publish_message,
)
from app.services.workflow_service import WorkflowServiceError, process_new_message, request_manual_translation

# 消息蓝图：提供 REST 历史接口和 Socket.IO 实时事件处理
bp = Blueprint("messages", __name__, url_prefix="/messages")

# 在线用户会话表（demo 级内存实现，单实例可用）
_online_users: dict[str, set[str]] = defaultdict(set)
_sid_to_user: dict[str, str] = {}
_http_presence: dict[str, float] = {}
_HTTP_PRESENCE_TTL_SECONDS = 40


def _is_dm_room(room: str) -> bool:
    return room.startswith("dm:")


def _build_dm_room(user_a: str, user_b: str) -> str:
    left, right = sorted([user_a, user_b])
    return f"dm:{left}|{right}"


def _dm_members(room: str) -> list[str]:
    if not _is_dm_room(room):
        return []
    members = room[3:].split("|")
    if len(members) != 2:
        return []
    return members


def _can_join_room(room: str, username: str) -> bool:
    if _is_dm_room(room):
        return username in _dm_members(room)
    return is_group_room_exists(room)


def _broadcast_online_users() -> None:
    socketio.emit("online_users", {"users": _online_usernames()})


def _mark_http_presence(username: str) -> None:
    _http_presence[username] = time.time()


def _online_usernames() -> list[str]:
    now = time.time()
    stale_users = [u for u, ts in _http_presence.items() if now - ts > _HTTP_PRESENCE_TTL_SECONDS]
    for username in stale_users:
        _http_presence.pop(username, None)

    merged = set(_online_users.keys()) | set(_http_presence.keys())
    return sorted(merged)


def _socket_username() -> str:
    """获取当前 Socket 连接用户名，兼容 Flask-Login 与 auth 回退。"""
    if current_user.is_authenticated and getattr(current_user, "username", ""):
        return str(current_user.username)
    return _sid_to_user.get(request.sid, "")


def _broadcast_group_rooms() -> None:
    rooms = list_group_rooms()
    socketio.emit("group_rooms_updated", {"rooms": rooms})


def _emit_private_rooms_for_user(username: str) -> None:
    rooms = list_private_rooms(username)
    for sid in _online_users.get(username, set()):
        socketio.emit("private_rooms_updated", {"rooms": rooms}, to=sid)


# ---------------------------------------------------------------------------
# REST 接口
# ---------------------------------------------------------------------------


@bp.route("/history")
@login_required
def history():
    """返回指定房间的历史消息（默认房间：general）。"""
    room = request.args.get("room", "general")
    limit = request.args.get("limit", type=int)
    messages = get_history(room=room, limit=limit)
    return jsonify(messages)


@bp.route("/online-users")
@login_required
def online_users():
    """返回当前在线用户名列表。"""
    _mark_http_presence(current_user.username)
    return jsonify(_online_usernames())


@bp.route("/presence", methods=["POST"])
@login_required
def heartbeat_presence():
    """HTTP 在线心跳：供无 Socket 场景维持在线列表。"""
    _mark_http_presence(current_user.username)
    return jsonify({"ok": True})


@bp.route("/send", methods=["POST"])
@login_required
def send_message_rest():
    """HTTP 发送兜底接口：用于 Socket.IO 不可用时仍可发送消息。"""
    data = request.get_json(silent=True) or {}
    room = data.get("room", "general")
    text = (data.get("text") or "").strip()
    username = current_user.username
    _mark_http_presence(username)

    if not text:
        return jsonify({"error": "消息不能为空"}), 400
    if not _can_join_room(room, username):
        return jsonify({"error": "会话不存在或无发送权限"}), 403

    history_window = current_app.config["WORKFLOW_HISTORY_WINDOW"]
    history = get_history(room=room, limit=history_window)
    try:
        workflow_result = process_new_message(
            new_message=text,
            chat_history=history,
            user_language="",
        )
    except WorkflowServiceError as exc:
        return jsonify({"error": f"工作流调用失败: {exc}"}), 502

    if not workflow_result["is_safe"]:
        return jsonify(
            {
                "error": "message_rejected",
                "reason": workflow_result.get("unsafe_reason") or "消息未通过安全检查。",
            }
        ), 422

    extras = {
        "translated_text": workflow_result.get("translated_text", ""),
        "detected_language": workflow_result.get("detected_language", ""),
        "suggested_replies": workflow_result.get("suggested_replies", []),
        "workflow_need_translate": workflow_result.get("need_translate", False),
        "workflow_trace_id": workflow_result.get("trace_id", ""),
    }
    if workflow_result.get("workflow_error"):
        extras["workflow_error"] = workflow_result["workflow_error"]

    message = publish_message(
        username=username,
        text=text,
        room=room,
        extras=extras,
    )
    socketio.emit("new_message", message, to=room)
    return jsonify({"message": message})


@bp.route("/sessions")
@login_required
def sessions_snapshot():
    """返回当前用户的群聊/私聊会话快照。"""
    _mark_http_presence(current_user.username)
    ensure_default_group_rooms()
    return jsonify(
        {
            "group_rooms": list_group_rooms(),
            "private_rooms": list_private_rooms(current_user.username),
        }
    )


# ---------------------------------------------------------------------------
# Socket.IO 事件处理器
# ---------------------------------------------------------------------------


@socketio.on("connect")
def on_connect(auth=None):
    """Socket 连接建立时登记在线用户。"""
    username = ""
    if current_user.is_authenticated and getattr(current_user, "username", ""):
        username = str(current_user.username)
    elif isinstance(auth, dict):
        username = str((auth.get("username") or "").strip())

    if not username:
        return False

    sid = request.sid
    _sid_to_user[sid] = username
    _online_users[username].add(sid)
    ensure_default_group_rooms()
    _broadcast_online_users()
    _broadcast_group_rooms()
    _emit_private_rooms_for_user(username)


@socketio.on("disconnect")
def on_disconnect():
    """Socket 断开时清理在线用户会话。"""
    sid = request.sid
    username = _sid_to_user.pop(sid, None)
    if not username:
        return

    user_sids = _online_users.get(username)
    if user_sids:
        user_sids.discard(sid)
        if not user_sids:
            _online_users.pop(username, None)
    _broadcast_online_users()


@socketio.on("fetch_sessions")
def on_fetch_sessions():
    """主动拉取会话快照（用于重连或前端首次初始化）。"""
    username = _socket_username()
    if not username:
        emit("error_message", {"msg": "会话未登录，请刷新页面重试。"})
        return

    ensure_default_group_rooms()
    emit("group_rooms_updated", {"rooms": list_group_rooms()})
    emit("private_rooms_updated", {"rooms": list_private_rooms(username)})


@socketio.on("create_group_room")
def on_create_group_room(data):
    """创建群聊会话。"""
    room_name = (data.get("room_name") or "").strip()
    if not room_name:
        emit("group_room_error", {"msg": "房间名不能为空。"})
        return

    try:
        room = create_group_room(room_name)
    except ValueError as exc:
        emit("group_room_error", {"msg": str(exc)})
        return

    join_room(room)
    _broadcast_group_rooms()
    emit("group_room_created", {"room": room})


@socketio.on("delete_group_room")
def on_delete_group_room(data):
    """删除群聊会话。"""
    room = (data.get("room") or "").strip()
    if not room:
        emit("group_room_error", {"msg": "缺少房间标识。"})
        return

    try:
        removed = delete_group_room(room)
    except ValueError as exc:
        emit("group_room_error", {"msg": str(exc)})
        return

    if not removed:
        emit("group_room_error", {"msg": "房间不存在或已删除。"})
        return

    _broadcast_group_rooms()
    socketio.emit("room_deleted", {"room": room, "room_type": "group"})


@socketio.on("open_private_chat")
def on_open_private_chat(data):
    """创建或打开 1v1 私聊房间，并返回规范房间号。"""
    peer = (data.get("peer") or "").strip()
    me = _socket_username()

    if not me:
        emit("private_chat_error", {"msg": "未识别当前登录用户。"})
        return

    if not peer:
        emit("private_chat_error", {"msg": "私聊对象不能为空。"})
        return
    if peer == me:
        emit("private_chat_error", {"msg": "不能和自己建立私聊。"})
        return
    if peer not in _online_usernames():
        emit("private_chat_error", {"msg": "对方当前不在线。"})
        return

    room = _build_dm_room(me, peer)
    add_private_room_for_users(room, me, peer)
    join_room(room)
    emit("private_chat_ready", {"room": room, "peer": peer})
    _emit_private_rooms_for_user(me)
    _emit_private_rooms_for_user(peer)

    # 通知对方有新的私聊会话可加入。
    for sid in _online_users.get(peer, set()):
        emit("private_chat_invite", {"room": room, "peer": me}, to=sid)


@socketio.on("delete_private_chat")
def on_delete_private_chat(data):
    """删除私聊会话。"""
    room = (data.get("room") or "").strip()
    if not room:
        emit("private_chat_error", {"msg": "缺少私聊房间标识。"})
        return

    operator = _socket_username()
    if not operator:
        emit("private_chat_error", {"msg": "未识别当前登录用户。"})
        return

    try:
        removed = delete_private_room(room, operator=operator)
    except ValueError as exc:
        emit("private_chat_error", {"msg": str(exc)})
        return

    if not removed:
        emit("private_chat_error", {"msg": "私聊会话不存在或已删除。"})
        return

    members = _dm_members(room)
    for username in members:
        _emit_private_rooms_for_user(username)
        for sid in _online_users.get(username, set()):
            socketio.emit("room_deleted", {"room": room, "room_type": "dm"}, to=sid)


@socketio.on("join")
def on_join(data):
    """处理客户端加入房间事件：加入 Socket.IO 房间并推送历史记录。"""
    username = _socket_username()
    if not username:
        emit("error_message", {"msg": "会话未登录，请刷新页面。"})
        return

    room = data.get("room", "general")
    if not _can_join_room(room, username):
        emit("error_message", {"msg": "会话不存在或无加入权限。"})
        return

    join_room(room)
    # 向当前连接推送该房间的历史消息
    history = get_history(room=room)
    emit("history", history)
    # 群聊广播进入通知，私聊不广播系统提示。
    if not _is_dm_room(room):
        emit(
            "status",
            {"msg": f"{username} 进入了房间。"},
            to=room,
        )


@socketio.on("leave")
def on_leave(data):
    """处理客户端离开房间事件：退出 Socket.IO 房间并广播通知。"""
    username = _socket_username()
    room = data.get("room", "general")
    leave_room(room)
    if username and not _is_dm_room(room):
        emit(
            "status",
            {"msg": f"{username} 离开了房间。"},
            to=room,
        )


@socketio.on("send_message")
def on_send_message(data):
    """处理客户端发送消息：先走工作流，再决定拦截或广播。"""
    username = _socket_username()
    if not username:
        emit("error_message", {"msg": "会话未登录，请刷新页面后重试。"})
        return

    room = data.get("room", "general")
    text = (data.get("text") or "").strip()
    # 忽略空消息
    if not text:
        return

    if not _can_join_room(room, username):
        emit("error_message", {"msg": "会话不存在或无发送权限。"})
        return

    history_window = current_app.config["WORKFLOW_HISTORY_WINDOW"]
    history = get_history(room=room, limit=history_window)
    emit("message_processing", {"msg": "正在进行安全检查与智能分析..."})
    try:
        workflow_result = process_new_message(
            new_message=text,
            chat_history=history,
            user_language="",
        )
    except WorkflowServiceError as exc:
        emit("error_message", {"msg": f"工作流调用失败: {exc}"})
        return

    if not workflow_result["is_safe"]:
        emit(
            "message_rejected",
            {
                "text": text,
                "reason": workflow_result.get("unsafe_reason") or "消息未通过安全检查。",
            },
        )
        return

    extras = {
        "translated_text": workflow_result.get("translated_text", ""),
        "detected_language": workflow_result.get("detected_language", ""),
        "suggested_replies": workflow_result.get("suggested_replies", []),
        "workflow_need_translate": workflow_result.get("need_translate", False),
        "workflow_trace_id": workflow_result.get("trace_id", ""),
    }
    if workflow_result.get("workflow_error"):
        extras["workflow_error"] = workflow_result["workflow_error"]

    # 将消息发布到 Redis Pub/Sub 频道，同时持久化到历史记录
    message = publish_message(
        username=username,
        text=text,
        room=room,
        extras=extras,
    )
    # 将完整消息对象广播给房间内所有在线用户
    emit("new_message", message, to=room)


@socketio.on("translate_message")
def on_translate_message(data):
    """手动触发某条消息翻译（可选/输入目标语言）。"""
    text = (data.get("text") or "").strip()
    target_language = (data.get("target_language") or "").strip()
    message_id = (data.get("message_id") or "").strip()

    if not text:
        emit("translation_error", {"msg": "原消息不能为空。", "message_id": message_id})
        return
    if not target_language:
        emit("translation_error", {"msg": "目标语言不能为空。", "message_id": message_id})
        return

    try:
        result = request_manual_translation(
            new_message=text,
            target_language=target_language,
            user_language="",
        )
    except WorkflowServiceError as exc:
        emit("translation_error", {"msg": str(exc), "message_id": message_id})
        return

    if not result["is_safe"]:
        emit(
            "translation_blocked",
            {
                "message_id": message_id,
                "reason": result.get("unsafe_reason") or "内容未通过安全检查。",
            },
        )
        return

    emit(
        "translation_result",
        {
            "message_id": message_id,
            "translated_text": result.get("translated_text") or text,
            "detected_language": result.get("detected_language", ""),
            "target_language": target_language,
            "need_translate": result.get("need_translate", False),
            "trace_id": result.get("trace_id", ""),
        },
    )
