from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from flask_socketio import emit, join_room, leave_room

from app.extensions import socketio
from app.services.redis_service import get_history, publish_message

# 消息蓝图：提供 REST 历史接口和 Socket.IO 实时事件处理
bp = Blueprint("messages", __name__, url_prefix="/messages")


# ---------------------------------------------------------------------------
# REST 接口
# ---------------------------------------------------------------------------


@bp.route("/history")
@login_required
def history():
    """返回指定房间的历史消息（默认房间：general）。"""
    room = request.args.get("room", "general")
    messages = get_history(room=room)
    return jsonify(messages)


# ---------------------------------------------------------------------------
# Socket.IO 事件处理器
# ---------------------------------------------------------------------------


@socketio.on("join")
def on_join(data):
    """处理客户端加入房间事件：加入 Socket.IO 房间并推送历史记录。"""
    room = data.get("room", "general")
    join_room(room)
    # 向当前连接推送该房间的历史消息
    history = get_history(room=room)
    emit("history", history)
    # 向房间内所有成员广播进入通知
    emit(
        "status",
        {"msg": f"{current_user.username} 进入了房间。"},
        to=room,
    )


@socketio.on("leave")
def on_leave(data):
    """处理客户端离开房间事件：退出 Socket.IO 房间并广播通知。"""
    room = data.get("room", "general")
    leave_room(room)
    emit(
        "status",
        {"msg": f"{current_user.username} 离开了房间。"},
        to=room,
    )


@socketio.on("send_message")
def on_send_message(data):
    """处理客户端发送消息事件：发布到 Redis 并广播给房间内所有成员。"""
    room = data.get("room", "general")
    text = (data.get("text") or "").strip()
    # 忽略空消息
    if not text:
        return
    # 将消息发布到 Redis Pub/Sub 频道，同时持久化到历史记录
    message = publish_message(
        username=current_user.username,
        text=text,
        room=room,
    )
    # 将完整消息对象广播给房间内所有在线用户
    emit("new_message", message, to=room)
