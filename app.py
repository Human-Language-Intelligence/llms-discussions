import random
import json

import flask
import flask_socketio

from source import config, manager, utils


TOPIC_POOL = json.loads(config.CONFIG["default"]["TOPIC"])

app = flask.Flask(__name__)
app.secret_key = config.CONFIG["flask"]["SECRET_KEY"]
socketio = flask_socketio.SocketIO(app)
room_manager = manager.RoomManager()

room_manager.event_bus.subscribe(
    "gpt-response",
    lambda data: socketio.emit(
        "gpt-message",
        data["content"],
        room=data["room"]
    )
)
room_manager.event_bus.subscribe(
    "gemini-response",
    lambda data: socketio.emit(
        "gemini-message",
        data["content"],
        room=data["room"]
    )
)


@socketio.on("tts-finished")
def handle_tts(data):
    code = data.get("room")
    side = data.get("side")
    if not (code and side):
        return

    room = room_manager.get_room(code)
    room.set_event(side)


@socketio.on("gpt-message")
def handle_model(data, code):
    if not data or data.get("name") == "admin":
        return

    room = room_manager.get_room(code)
    room.threads["gpt"].enqueue_input(
        data.get("message", "").strip()
    )


@socketio.on("message")
def handle_message(data):
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    message_text = data.get("data", "").strip()
    content = {
        "name": name,
        "message": message_text,
        "timestamp": utils.get_utc_timestamp(),
        "is_typing": False,
        "is_playing": True
    }

    if not (code and message_text) or code not in room_manager.list_rooms():
        return

    # 메시지 저장 및 브로드캐스트
    room = room_manager.get_room(code)
    room.append_message(content)

    # 로그 기록 및 GPT 응답 호출
    socketio.emit("message", content, room=code)
    handle_model(content, code)

    utils.log_event("Send", name, message_text)


@socketio.on("typing")
def handle_typing(data):
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    message_text = data.get("data", "").strip()
    content = {
        "name": name,
        "message": message_text,
        "is_typing": True,
    }

    if not code or code not in room_manager.list_rooms():
        return

    # 실시간 타이핑 메시지 전송
    socketio.emit("message", content, room=code)

    # 일정 길이 이상 메시지면 GPT 반응 확률적으로 호출
    if len(message_text) > 70 and random.randint(0, 1) == 1:
        handle_model(content, code)

    utils.log_event("Keystroke", name, message_text)


@socketio.on("live-toggle")
def handle_live_toggle(data):
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    status = data.get("status", "offline")
    content = {
        "name": name,
        "message": f"{name} has gone {status}",
        "timestamp": utils.get_utc_timestamp(),
    }

    if not code or code not in room_manager.list_rooms():
        return

    socketio.emit("notification", content, room=code)

    utils.log_event("Toggle", name, status)


@socketio.on("send-topic")
def handle_send_topic(data):
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    topic = data.get("topic", "").strip()
    content = {
        "name": name,
        "message": f"토론 주제는 '{topic}' 입니다.",
        "timestamp": utils.get_utc_timestamp(),
        "is_typing": False,
        "is_playing": True
    }

    if not (code and topic) or code not in room_manager.list_rooms():
        return

    # 메시지 저장
    room = room_manager.get_room(code)
    room.append_message(content)
    # GPT 처리 함수 호출
    handle_model(content, code)

    utils.log_event("Send", name, content["message"])


@socketio.on("connect")
def handle_connect(auth):
    code = flask.session.get("room")
    topic = flask.session.get("topic")
    name = flask.session.get("name", "user")
    content = {
        "name": name,
        "message": f"{name} has entered the room",
        "timestamp": utils.get_utc_timestamp(),
    }

    # 세션이나 유효한 방이 없으면 연결 중단
    if not (code and topic) or code not in room_manager.list_rooms():
        flask_socketio.leave_room(code)
        return

    flask_socketio.join_room(code)
    socketio.emit("notification", content, room=code)
    room = room_manager.get_room(code)
    room.add_member()

    utils.log_event("Connect", name, content["message"])


@socketio.on("disconnect")
def handle_disconnect():
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    content = {
        "name": name,
        "message": "has left the room"
    }

    if not code:
        return

    flask_socketio.leave_room(code)
    # 퇴장 메시지 전송
    flask_socketio.send(
        content,
        to=code
    )
    if code in room_manager.list_rooms():
        room = room_manager.get_room(code)
        condition = room.remove_member()
        if not condition:
            room_manager.remove_room(code)

    utils.log_event("Disconnect", name, content["message"])


@app.route("/room")
def room():
    code = flask.session.get("room")
    topic = flask.session.get("topic")

    if not (code and topic) or code not in room_manager.list_rooms():
        return flask.redirect(flask.url_for("home"))

    room = room_manager.get_room(code)
    return flask.render_template(
        "room.html",
        code=code,
        topic=topic,
        messages=room.messages
    )


@app.route("/", methods=["GET", "POST"])
def home():
    flask.session.clear()
    random_topics = random.sample(TOPIC_POOL, 3)

    if flask.request.method == "POST":
        name = "user"  # 기본 이름
        topic = flask.request.form.get("topic", "").strip()
        model_pro = flask.request.form.get("model_pro")
        model_con = flask.request.form.get("model_con")

        if not topic:
            return flask.render_template(
                "home.html",
                error="Please enter a topic.",
                random_topics=random_topics
            )

        code = room_manager.create_room()

        flask.session["room"] = code
        flask.session["topic"] = topic
        flask.session["name"] = name
        flask.session["model_pro"] = model_pro
        flask.session["model_con"] = model_con

        return flask.redirect(flask.url_for("room"))

    return flask.render_template(
        "home.html",
        random_topics=random_topics
    )


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
