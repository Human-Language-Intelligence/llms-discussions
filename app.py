import random
import json

import flask
import flask_socketio

from source import config, manager, utils, content


TOPIC_POOL = json.loads(config.CONFIG["default"]["TOPIC"])

app = flask.Flask(__name__)
app.secret_key = config.CONFIG["flask"]["SECRET_KEY"]
socketio = flask_socketio.SocketIO(app)
room_manager = manager.RoomManager()

room_manager.event_bus.subscribe(
    "pros-response",
    lambda data: socketio.emit(
        "pros-message",
        data.get("data"),
        room=data.get("room")
    )
)
room_manager.event_bus.subscribe(
    "cons-response",
    lambda data: socketio.emit(
        "cons-message",
        data.get("data"),
        room=data.get("room")
    )
)


@socketio.on("complete")
def on_tts(data):
    code = data.get("room")
    role = data.get("role")
    if not (code and role):
        return

    room = room_manager.get_room(code)
    room.set_event(role)

    utils.log_event("Complete", role)


@socketio.on("model")
def on_model(data, code):
    if not data:
        return

    room = room_manager.get_room(code)
    room.threads["pros"].enqueue_input(
        data.get("message", "").strip()
    )


@socketio.on("user")
def on_user(data):
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    message_text = data.get("data", "").strip()
    data = content.MessageContent(
        name=name,
        role="user",
        message=message_text,
        is_playing=True
    ).to_dict()

    if not (code and message_text) or code not in room_manager.list_rooms():
        return

    room = room_manager.get_room(code)
    room.user_message(message_text)
    socketio.emit("message", data, room=code)

    utils.log_event("Send", name, message_text)


@socketio.on("typing")
def on_typing(data):
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    message_text = data.get("data", "").strip()
    data = content.MessageContent(
        name=name,
        role="user",
        message=message_text,
        is_typing=True
    ).to_dict()

    if not code or code not in room_manager.list_rooms():
        return

    # 일정 길이 이상 메시지면 GPT 반응 확률적으로 호출
    if len(message_text) > 70 and random.randint(0, 1) == 1:
        on_model(data, code)

    # 실시간 타이핑 메시지 전송
    socketio.emit("message", data, room=code)

    utils.log_event("Keystroke", name, message_text)


@socketio.on("start")
def on_start(data):
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    topic = data.get("topic", "").strip()
    data = content.MessageContent(
        name=name,
        role="system",
        message=f"토론 주제는 '{topic}' 입니다.",
        is_playing=True
    ).to_dict()

    if not (code and topic) or code not in room_manager.list_rooms():
        return

    # room = room_manager.get_room(code)
    # room.append_message(data)

    on_model(data, code)

    utils.log_event("Send", name, data.get("message"))


@socketio.on("connect")
def on_connect():
    code = flask.session.get("room")
    topic = flask.session.get("topic")
    name = flask.session.get("name", "user")
    data = content.MessageContent(
        name=name,
        role="system",
        message=f"{name} has entered the room"
    ).to_dict()

    # 세션이나 유효한 방이 없으면 연결 중단
    if not (code and topic) or code not in room_manager.list_rooms():
        flask_socketio.leave_room(code)
        return

    room = room_manager.get_room(code)
    room.add_member()

    flask_socketio.join_room(code)
    # socketio.emit("notification", data, room=code)

    utils.log_event("Connect", name, data.get("message"))


@socketio.on("disconnect")
def on_disconnect():
    code = flask.session.get("room")
    name = flask.session.get("name", "user")
    data = content.MessageContent(
        name=name,
        role="system",
        message=f"{name} has left the room"
    ).to_dict()

    if not code:
        return

    if code in room_manager.list_rooms():
        room = room_manager.get_room(code)
        condition = room.remove_member()
        if not condition:
            room_manager.remove_room(code)

    flask_socketio.leave_room(code)
    # 퇴장 메시지 전송
    flask_socketio.send(
        data,
        to=code
    )

    utils.log_event("Disconnect", name, data.get("message"))


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
        model_pros = flask.request.form.get("model_pros")
        model_cons = flask.request.form.get("model_cons")

        if not topic:
            return flask.render_template(
                "home.html",
                error="Please enter a topic.",
                random_topics=random_topics
            )

        code = room_manager.create_room(model_pros, model_cons)

        flask.session["room"] = code
        flask.session["topic"] = topic
        flask.session["name"] = name

        return flask.redirect(flask.url_for("room"))

    return flask.render_template(
        "home.html",
        random_topics=random_topics
    )


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
