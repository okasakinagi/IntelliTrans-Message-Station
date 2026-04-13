from flask import Blueprint, jsonify, request
from flask_login import current_user, login_required
from flask_socketio import emit, join_room, leave_room

from app.extensions import socketio
from app.services.redis_service import get_history, publish_message

bp = Blueprint("messages", __name__, url_prefix="/messages")


# ---------------------------------------------------------------------------
# REST endpoints
# ---------------------------------------------------------------------------


@bp.route("/history")
@login_required
def history():
    """Return the persisted message history for a room (default: *general*)."""
    room = request.args.get("room", "general")
    messages = get_history(room=room)
    return jsonify(messages)


# ---------------------------------------------------------------------------
# Socket.IO event handlers
# ---------------------------------------------------------------------------


@socketio.on("join")
def on_join(data):
    room = data.get("room", "general")
    join_room(room)
    history = get_history(room=room)
    emit("history", history)
    emit(
        "status",
        {"msg": f"{current_user.username} has entered the room."},
        to=room,
    )


@socketio.on("leave")
def on_leave(data):
    room = data.get("room", "general")
    leave_room(room)
    emit(
        "status",
        {"msg": f"{current_user.username} has left the room."},
        to=room,
    )


@socketio.on("send_message")
def on_send_message(data):
    room = data.get("room", "general")
    text = (data.get("text") or "").strip()
    if not text:
        return
    message = publish_message(
        username=current_user.username,
        text=text,
        room=room,
    )
    emit("new_message", message, to=room)
