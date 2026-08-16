import os

# BẮT BỘC 100%: Phải patch_all() ở dòng ĐẦU TIÊN trước các import khác!
from gevent import monkey
monkey.patch_all()

from flask import Flask, request
from flask_cors import CORS
from flask_socketio import SocketIO, emit

app = Flask(__name__)
app.config["SECRET_KEY"] = "zchat-webrtc-secret"
CORS(app)

# Khai báo async_mode="gevent"
socketio = SocketIO(
    app,
    cors_allowed_origins="*",
    async_mode="gevent",
    logger=False,
    engineio_logger=False,
)

# username (lower) -> sid
online_users = {}
# sid -> username
sid_to_user = {}


def _norm(name):
    return (name or "").strip().lower()


@app.route("/")
def index():
    return {
        "ok": True,
        "service": "Z-Chat WebRTC Signaling",
        "online": len(online_users),
    }


@socketio.on("connect")
def on_connect():
    print(f"[connect] sid={request.sid}")


@socketio.on("disconnect")
def on_disconnect():
    sid = request.sid
    username = sid_to_user.pop(sid, None)
    if username and online_users.get(username) == sid:
        online_users.pop(username, None)
        emit(
            "user_offline",
            {"username": username},
            broadcast=True,
            include_self=False,
        )
    print(f"[disconnect] sid={sid} user={username}")


@socketio.on("register")
def on_register(data):
    username = _norm((data or {}).get("username"))
    if not username:
        emit("register_error", {"message": "username required"})
        return

    old_sid = online_users.get(username)
    if old_sid and old_sid != request.sid:
        sid_to_user.pop(old_sid, None)

    online_users[username] = request.sid
    sid_to_user[request.sid] = username
    emit("registered", {"username": username, "online": list(online_users.keys())})
    emit(
        "user_online",
        {"username": username},
        broadcast=True,
        include_self=False,
    )
    print(f"[register] {username} -> {request.sid}")


@socketio.on("call_user")
def on_call_user(data):
    data = data or {}
    to_user = _norm(data.get("to"))
    from_user = _norm(data.get("from") or sid_to_user.get(request.sid))
    offer = data.get("offer")
    call_type = data.get("callType") or "video"

    if not to_user or not from_user or not offer:
        emit("call_error", {"message": "missing to/from/offer"})
        return

    target_sid = online_users.get(to_user)
    if not target_sid:
        emit("call_error", {"message": "user_offline", "to": to_user})
        return

    emit(
        "incoming_call",
        {
            "from": from_user,
            "offer": offer,
            "callType": call_type,
        },
        to=target_sid,
    )
    print(f"[call_user] {from_user} -> {to_user}")


@socketio.on("make_answer")
def on_make_answer(data):
    data = data or {}
    to_user = _norm(data.get("to"))
    from_user = _norm(data.get("from") or sid_to_user.get(request.sid))
    answer = data.get("answer")

    if not to_user or not answer:
        emit("call_error", {"message": "missing to/answer"})
        return

    target_sid = online_users.get(to_user)
    if not target_sid:
        emit("call_error", {"message": "user_offline", "to": to_user})
        return

    emit(
        "call_answered",
        {
            "from": from_user,
            "answer": answer,
        },
        to=target_sid,
    )
    print(f"[make_answer] {from_user} -> {to_user}")


@socketio.on("ice_candidate")
def on_ice_candidate(data):
    data = data or {}
    to_user = _norm(data.get("to"))
    from_user = _norm(data.get("from") or sid_to_user.get(request.sid))
    candidate = data.get("candidate")

    if not to_user or candidate is None:
        return

    target_sid = online_users.get(to_user)
    if not target_sid:
        return

    emit(
        "ice_candidate",
        {
            "from": from_user,
            "candidate": candidate,
        },
        to=target_sid,
    )


@socketio.on("end_call")
def on_end_call(data):
    data = data or {}
    to_user = _norm(data.get("to"))
    from_user = _norm(data.get("from") or sid_to_user.get(request.sid))
    reason = data.get("reason") or "hangup"

    if not to_user:
        return

    target_sid = online_users.get(to_user)
    if target_sid:
        emit(
            "call_ended",
            {
                "from": from_user,
                "reason": reason,
            },
            to=target_sid,
        )
    print(f"[end_call] {from_user} -> {to_user} ({reason})")


@socketio.on("reject_call")
def on_reject_call(data):
    data = data or {}
    data["reason"] = "reject"
    on_end_call(data)


@socketio.on("media_state")
def on_media_state(data):
    data = data or {}
    to_user = _norm(data.get("to"))
    from_user = _norm(data.get("from") or sid_to_user.get(request.sid))
    if not to_user:
        return
    target_sid = online_users.get(to_user)
    if not target_sid:
        return
    emit(
        "media_state",
        {
            "from": from_user,
            "video": data.get("video"),
            "audio": data.get("audio"),
        },
        to=target_sid,
    )


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    print(f"Z-Chat signaling running on port {port}")
    socketio.run(app, host="0.0.0.0", port=port, debug=False)
