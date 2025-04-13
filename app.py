import random
import queue
import threading
import configparser
import base64
import string
import json

import flask
import flask_socketio

from datetime import datetime, timezone
from thefuzz import fuzz

from source.gemini import Gemini
from source.chatgpt import ChatGPT
from source.tts import TTS


CONFIG = configparser.ConfigParser()
CONFIG.read("config.ini")


TOPIC_POOL = json.loads(CONFIG["default"]["TOPIC"])
STATUS = {
    "count": 0,
    "rooms": {},
    "lock": threading.Lock(),
    "gpt": {
        "queue": queue.Queue(),
        "progressing": {},
        "finished": {}
    },
    "gemini": {
        "queue": queue.Queue(),
        "progressing": {},
        "finished": {}
    }
}

app = flask.Flask(__name__)
app.secret_key = CONFIG["flask"]["SECRET_KEY"]
socketio = flask_socketio.SocketIO(app)

gpt = ChatGPT(CONFIG["default"]["HISTORY.POSITIVE"])
gemini = Gemini(CONFIG["default"]["HISTORY.NEGATIVE"])

tts_m = TTS(3)
tts_f = TTS(1)


def get_timestamp_utc() -> str:
    """현재 UTC 시간을 ISO 8601 형식으로 반환."""
    return datetime.now(timezone.utc).isoformat()


def get_random_time():
    # 베타 분포에서 랜덤한 값을 얻음
    value = random.betavariate(1, 3)
    # 값을 0.01과 0.7 사이의 범위로 스케일링
    return 0.01 + value * (0.35 - 0.01)


def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(string.ascii_uppercase)

        if code not in STATUS["rooms"]:
            break

    return code


def log_event(event_type, username, additional_info=""):
    # 이벤트를 로그에 기록
    with open("events.log", "a") as log_file:
        log_file.write(
            f"{get_timestamp_utc()} - {username} - {event_type}: {additional_info}\n"
        )


def worker():
    while STATUS["count"] < 10:
        chatgpt_response, room = STATUS["gpt"]["queue"].get()
        if chatgpt_response is None:
            break
        content = send_response("gpt", chatgpt_response, room)
        STATUS["gpt"]["queue"].task_done()

        # GPT 응답 전송 완료 후, 자동으로 Gemini 응답 생성
        with STATUS["lock"]:
            gemini_response = gemini.get_response(content["message"])
            STATUS["gemini"]["queue"].put((gemini_response, room))


def gemini_worker():
    while STATUS["count"] < 10:
        gemini_response, room = STATUS["gemini"]["queue"].get()
        if gemini_response is None:
            break
        content = send_response("gemini", gemini_response, room)
        STATUS["gemini"]["queue"].task_done()

        # Gemini 응답 전송 완료 후, 자동으로 GPT 응답 생성
        with STATUS["lock"]:
            chatgpt_response = gpt.get_response(content["message"])
            STATUS["gpt"]["queue"].put((chatgpt_response, room))


def handle_user_typing(side, data, room):
    """
    유저가 타이핑 중일 때 GPT와 Gemini 응답을 처리하는 함수.
    """
    if not room or not side:
        return

    recent_user_typing = data.get("message", "").strip()

    if data["is_typing"]:
        # 진행 중인 문장 유사도 비교
        other_side = "gemini" if side == "gpt" else "gpt"
        if fuzz.ratio(STATUS[other_side]["progressing"].get(room, ""), recent_user_typing) < 60:
            STATUS[side]["progressing"][room] = False
            response = generate_response(side, recent_user_typing, room)
            return response
    else:
        # 메시지 전송이 끝났을 때 처리
        if STATUS[side]["progressing"].get(room, False):
            if fuzz.ratio(STATUS[other_side]["progressing"].get(room, ""), recent_user_typing) > 60:
                return
            STATUS[side]["progressing"][room] = False
            response = generate_response(side, recent_user_typing, room)
            return response
        # 진행 중인 상태가 아니라면 새 응답을 생성
        response = generate_response(side, recent_user_typing, room)
        return response


def generate_response(side, recent_user_typing, room):
    """
    GPT 또는 Gemini 모델에 맞는 응답을 생성하고 상태를 업데이트하는 함수.
    """
    if side == "gpt":
        response = gpt.get_response(recent_user_typing)
        STATUS["gpt"]["progressing"][room] = response
        STATUS["gpt"]["queue"].put((response, room))
        STATUS["gemini"]["progressing"][room] = recent_user_typing
    elif side == "gemini":
        response = gemini.get_response(recent_user_typing)
        STATUS["gemini"]["progressing"][room] = response
        STATUS["gemini"]["queue"].put((response, room))
        STATUS["gpt"]["progressing"][room] = recent_user_typing

    return response


def send_response(side, response_data, room):
    full_response = "".join(response_data)

    if side == "gpt":
        tts_function = tts_f.request
    elif side == "gemini":
        tts_function = tts_m.request

    try:
        tts_response = tts_function(full_response)
        audio_base64 = base64.b64encode(tts_response)
    except Exception as e:
        print(f"TTS error for {side}:", e)
        audio_base64 = ""

    content = {
        "name": side,
        "timestamp": get_timestamp_utc(),
        "message": full_response,
        "is_typing": False,
        "audio_base64": audio_base64.decode("utf-8")
    }

    # 응답 전송
    socketio.emit(f"{side}-message", content, room=room)

    # 상태 업데이트
    if room in STATUS[side]["finished"]:
        STATUS[side]["finished"][room].clear()
        STATUS[side]["finished"][room].wait()

    return content


@socketio.on("tts-finished")
def handle_tts_finished(data):
    room = data.get("room")
    side = data.get("side")

    if not room or not side:
        return

    if room in STATUS[side]["finished"]:
        STATUS[side]["finished"][room].set()


@socketio.on("gpt-message")
def gpt_message(data, room):
    if data is None or data.get("name") == "admin":
        return
    print("GPT message received:", data)

    STATUS["count"] += 1
    handle_user_typing("gpt", data, room)


@socketio.on("gemini-message")
def gemini_message(data, room):
    if data is None or data.get("name") == "admin":
        return
    print("Gemini message received:", data)

    STATUS["count"] += 1
    handle_user_typing("gemini", data, room)


@socketio.on("message")
def handle_message(data):
    room = flask.session.get("room")
    if not room or room not in STATUS["rooms"]:
        return

    message_text = data.get("data", "").strip()
    if not message_text:
        return  # 빈 메시지는 무시

    name = flask.session.get("name", "User")
    content = {
        "name": name,
        "message": message_text,
        "timestamp": get_timestamp_utc(),
        "is_typing": False
    }

    # 메시지 저장 및 브로드캐스트
    STATUS["rooms"][room]["messages"].append(content)

    # 로그 기록 및 GPT 응답 호출
    socketio.emit("message", content, room=room)
    gpt_message(content, room=room)
    log_event("Send", name, message_text)


@socketio.on("typing")
def handle_typing(data):
    room = flask.session.get("room")
    if not room or room not in STATUS["rooms"]:
        return

    name = flask.session.get("name", "User")
    message_text = data.get("data", "").strip()
    content = {
        "name": name,
        "message": message_text,
        "is_typing": True,
    }

    # 실시간 타이핑 메시지 전송
    socketio.emit("message", content, room=room)

    # 일정 길이 이상 메시지면 GPT 반응 확률적으로 호출
    if len(message_text) > 70 and random.randint(0, 1) == 1:
        gpt_message(content, room=room)
    log_event("Keystroke", name, message_text)


@socketio.on("live-toggle")
def handle_live_toggle(data):
    room = flask.session.get("room")
    if not room or room not in STATUS["rooms"]:
        return

    name = flask.session.get("name", "User")
    status = data.get("status", "offline")
    content = {
        "name": name,
        "message": f"{name} has gone {status}",
        "timestamp": get_timestamp_utc(),
    }

    socketio.emit("notification", content, room=room)
    log_event("Toggle", name, status)


@socketio.on("send-topic")
def handle_send_topic(data):
    room = flask.session.get("room")
    name = flask.session.get("name", "User")
    topic = data.get("topic", "").strip()
    if not (topic and room) or room not in STATUS["rooms"]:
        return

    # GPT 및 Gemini 처리 완료 여부를 관리할 이벤트 객체 초기화
    STATUS["gpt"]["finished"][room] = threading.Event()
    STATUS["gemini"]["finished"][room] = threading.Event()

    # 메시지 구성
    content = {
        "name": name,
        "message": f"토론 주제는 '{topic}' 입니다.",
        "timestamp": get_timestamp_utc(),
        "is_typing": False,
    }
    # 메시지 저장
    STATUS["rooms"][room]["messages"].append(content)

    # GPT 처리 함수 호출
    gpt_message(content, room=room)
    log_event("Send", name, content["message"])


@socketio.on("connect")
def handle_connect(auth):
    room = flask.session.get("room")
    topic = flask.session.get("topic")
    # 세션이나 유효한 방이 없으면 연결 중단
    if not (room and topic) or room not in STATUS["rooms"]:
        flask_socketio.leave_room(room)
        return

    name = flask.session.get("name", "User")  # 이름이 있다면 세션에서 가져오고, 기본값은 'User'
    content = {
        "name": name,
        "message": f"{name} has entered the room",
        "timestamp": get_timestamp_utc(),
    }
    STATUS["rooms"][room]["members"] += 1

    flask_socketio.join_room(room)
    socketio.emit("notification", content, room=room)
    log_event("Connect", name, content["message"])


@socketio.on("disconnect")
def handle_disconnect():
    room = flask.session.get("room")
    name = flask.session.get("name", "User")  # 이름도 세션에서 가져오되 기본값 지정

    if room:
        flask_socketio.leave_room(room)

        content = {
            "name": name,
            "message": "has left the room"
        }
        # 퇴장 메시지 전송
        flask_socketio.send(
            content,
            to=room
        )

        if room in STATUS["rooms"]:
            STATUS["rooms"][room]["members"] -= 1
            if STATUS["rooms"][room]["members"] <= 0:
                del STATUS["rooms"][room]
        log_event("Disconnect", name, content["message"])


@app.route("/room")
def room():
    room = flask.session.get("room")
    topic = flask.session.get("topic")

    if not (room and topic) or room not in STATUS["rooms"]:
        return flask.redirect(flask.url_for("home"))

    STATUS["count"] = 0

    return flask.render_template(
        "room.html",
        code=room,
        topic=topic,
        messages=STATUS["rooms"][room]["messages"]
    )


@app.route("/", methods=["GET", "POST"])
def home():
    flask.session.clear()
    random_topics = random.sample(TOPIC_POOL, 3)

    if flask.request.method == "POST":
        topic = flask.request.form.get("topic", "").strip()
        model_pro = flask.request.form.get("model_pro")
        model_con = flask.request.form.get("model_con")

        if not topic:
            return flask.render_template("home.html", error="Please enter a topic.", random_topics=random_topics)

        room = generate_unique_code(2)
        STATUS["rooms"][room] = {"members": 0, "messages": []}
        flask.session["room"] = room
        flask.session["topic"] = topic

        return flask.redirect(flask.url_for("room"))
    return flask.render_template("home.html", random_topics=random_topics)


THREADS = {
    "gpt": threading.Thread(target=worker, daemon=True),
    "gemini": threading.Thread(target=gemini_worker, daemon=True)
}
for thread in THREADS.values():
    thread.start()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
