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
from fuzzywuzzy import fuzz

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
        content = send_gpt_response(chatgpt_response, room)
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
        content = send_gemini_response(gemini_response, room)
        STATUS["gemini"]["queue"].task_done()

        # Gemini 응답 전송 완료 후, 자동으로 GPT 응답 생성
        with STATUS["lock"]:
            chatgpt_response = gpt.get_response(content["message"])
            STATUS["gpt"]["queue"].put((chatgpt_response, room))


def send_gpt_response(chatgpt_response, room):
    if room in STATUS["gpt"]["finished"]:
        STATUS["gpt"]["finished"][room].clear()

    full_response = "".join(chatgpt_response)
    try:
        tts_response = tts_f.request(full_response)
        audio_base64 = base64.b64encode(tts_response)
    except Exception as e:
        print("TTS error:", e)
        audio_base64 = ""

    content = {
        "name": "ChatGPT",
        "timestamp": get_timestamp_utc(),
        "message": full_response,
        "is_typing": False,
        "audio_base64": audio_base64.decode("utf-8")
    }

    # GPT 응답과 TTS 생성 완료 후 전송
    socketio.emit("gpt-message", content, room=room)

    if room in STATUS["gpt"]["finished"]:
        # 중복 클리어를 피하기 위해 다시 초기화
        STATUS["gpt"]["finished"][room].clear()
        STATUS["gpt"]["finished"][room].wait()

    return content


def send_gemini_response(gemini_response, room):
    full_response = "".join(gemini_response)

    try:
        tts_response = tts_m.request(full_response)
        audio_base64 = base64.b64encode(tts_response)
    except Exception as e:
        print("TTS error:", e)
        audio_base64 = ""

    content = {
        "name": "Gemini",
        "timestamp": get_timestamp_utc(),
        "message": full_response,
        "is_typing": False,
        "audio_base64": audio_base64.decode("utf-8")
    }

    socketio.emit("gemini-message", content, room=room)

    if room in STATUS["gemini"]["finished"]:
        STATUS["gemini"]["finished"][room].clear()
        STATUS["gemini"]["finished"][room].wait()

    return content


@socketio.on("tts_finished")
def handle_tts_finished(data):
    room = data.get("room")
    side = data.get("side")
    if room is None or side is None:
        return
    if side == "ChatGPT":
        if room in STATUS["gpt"]["finished"]:
            STATUS["gpt"]["finished"][room].set()
    elif side == "Gemini":
        if room in STATUS["gemini"]["finished"]:
            STATUS["gemini"]["finished"][room].set()


@socketio.on("gpt-message")
def GPTmessage(data, room):
    if data == None:
        return
    if data["name"] == "admin":
        return

    STATUS["count"] += 1
    recent_user_typing = data["message"]

    with STATUS["lock"]:
        if data["is_typing"] == False:
            gpt.append_history("user", recent_user_typing)
        if data["is_typing"] == True:
            # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
            if STATUS["gpt"]["progressing"].get(room, False):
                # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
                if STATUS["gemini"]["progressing"].get(room, False):
                    # 유저가 타이핑 중에 20퍼센트 이상 다른 문장을 치면 다른 문장으로 응답 생성
                    if fuzz.ratio(STATUS["gemini"]["progressing"][room], recent_user_typing) < 60:
                        STATUS["gpt"]["progressing"][room] = False
                        chatgpt_response = gpt.get_response()  # recent_user_typing)
                        # True
                        STATUS["gpt"]["progressing"][room] = chatgpt_response
                        STATUS["gpt"]["queue"].put((chatgpt_response, room))
                        # 사용자가 보낸 메시지 저장
                        STATUS["gemini"]["progressing"][room] = recent_user_typing
                return

            chatgpt_response = gpt.get_response()  # recent_user_typing)
            STATUS["gpt"]["progressing"][room] = chatgpt_response  # True
            # 사용자가 보낸 메시지 저장
            STATUS["gemini"]["progressing"][room] = recent_user_typing
            STATUS["gpt"]["queue"].put((chatgpt_response, room))

        if data["is_typing"] == False:
            # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!
            if STATUS["gpt"]["progressing"].get(room, False):
                # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!
                if STATUS["gemini"]["progressing"].get(room, False):
                    if fuzz.ratio(STATUS["gemini"]["progressing"][room], recent_user_typing) > 60:
                        return
                    STATUS["gpt"]["progressing"][room] = False
                    chatgpt_response = gpt.get_response()  # recent_user_typing)
                    STATUS["gpt"]["progressing"][room] = chatgpt_response  # True
                    # 사용자가 보낸 메시지 저장
                    STATUS["gemini"]["progressing"][room] = recent_user_typing
                    # 문제: 원래 치던 문장에서 send를 누르면 그걸 기반으로 다시 응답을 생성함.
                    STATUS["gpt"]["queue"].put((chatgpt_response, room))

            # else: # gpt 응답이 생성중이 아니라면 생성
            chatgpt_response = gpt.get_response()  # recent_user_typing)
            STATUS["gpt"]["progressing"][room] = chatgpt_response  # True
            # 사용자가 보낸 메시지 저장
            STATUS["gemini"]["progressing"][room] = recent_user_typing
            STATUS["gpt"]["queue"].put((chatgpt_response, room))


@socketio.on("gemini-message")
def Geminimessage(data, room):
    if data == None:
        return
    if data["name"] == "admin":
        return

    STATUS["count"] += 1
    recent_user_typing = data["message"]

    with STATUS["lock"]:
        if data["is_typing"] == True:
            # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
            if STATUS["gemini"]["progressing"].get(room, False):
                # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
                if STATUS["gpt"]["progressing"].get(room, False):
                    # 유저가 타이핑 중에 20퍼센트 이상 다른 문장을 치면 다른 문장으로 응답 생성
                    if fuzz.ratio(STATUS["gpt"]["progressing"][room], recent_user_typing) < 60:
                        STATUS["gemini"]["progressing"][room] = False
                        gemini_response = gemini.get_response(
                            recent_user_typing)
                        # True
                        STATUS["gemini"]["progressing"][room] = gemini_response
                        STATUS["gemini"]["queue"].put((gemini_response, room))
                        # 사용자가 보낸 메시지 저장
                        STATUS["gpt"]["progressing"][room] = recent_user_typing
                return

            gemini_response = gemini.get_response(recent_user_typing)
            STATUS["gemini"]["progressing"][room] = gemini_response  # True
            # 사용자가 보낸 메시지 저장
            STATUS["gpt"]["progressing"][room] = recent_user_typing
            STATUS["gemini"]["queue"].put((gemini_response, room))

        if data["is_typing"] == False:
            # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!
            if STATUS["gemini"]["progressing"].get(room, False):
                if STATUS["gpt"]["progressing"].get(room, False):
                    if fuzz.ratio(STATUS["gpt"]["progressing"][room], recent_user_typing) > 60:
                        return
                    STATUS["gemini"]["progressing"][room] = False
                    gemini_response = gemini.get_response(recent_user_typing)
                    STATUS["gemini"]["progressing"][room] = gemini_response  # True
                    # 사용자가 보낸 메시지 저장
                    STATUS["gpt"]["progressing"][room] = recent_user_typing
                    # 문제: 원래 치던 문장에서 send를 누르면 그걸 기반으로 다시 응답을 생성함.
                    STATUS["gemini"]["queue"].put((gemini_response, room))
            # else: # gpt 응답이 생성중이 아니라면 생성
            gemini_response = gemini.get_response(recent_user_typing)
            STATUS["gemini"]["progressing"][room] = gemini_response  # True
            # 사용자가 보낸 메시지 저장
            STATUS["gpt"]["progressing"][room] = recent_user_typing
            STATUS["gemini"]["queue"].put((gemini_response, room))


@socketio.on("message")
def message(data):
    room = flask.session.get("room")
    if room not in STATUS["rooms"]:
        return

    content = {
        "name": "User",  # session.get("name"),
        "message": data["data"],
        "timestamp": get_timestamp_utc(),  # 현재 시간을 UTC로 저장
        "is_typing": False
    }

    if data["data"].strip():
        content["is_typing"] = False
        STATUS["rooms"][room]["messages"].append(content)
    else:
        return

    socketio.emit("message", content, room=room)
    # 키스트로크를 로그에 기록
    log_event("Send", "User", content["message"])  # session.get("name")
    GPTmessage(content, room)


@socketio.on("typing")
def handle_typing(data):
    room = flask.session.get("room")
    if room not in STATUS["rooms"]:
        return

    content = {
        "name": "User",  # session.get("name"),
        "message": data["message"],
        "is_typing": True
    }

    socketio.emit("message", content, room=room)
    # 키스트로크를 로그에 기록
    if data["message"].strip():
        log_event("Keystroke", "User", data["message"])  # session.get("name")
    if len(content["message"]) > 70:  # 쌍방채팅 여기서 조정
        if random.randint(0, 1) == 1:
            GPTmessage(content)


@socketio.on("live-toggle")
def handle_live_toggle(data):
    room = flask.session.get("room")
    if room not in STATUS["rooms"]:
        return

    name = "User"  # session.get("name")
    content = {
        "name": "User",  # session.get("name"),
        "message": f"{name} has gone {data['status']}",
        "timestamp": get_timestamp_utc(),
    }

    socketio.emit("notification", content, room=room)
    log_event("toggle", "User", data["status"])  # session.get("name"),


@socketio.on("sendTopic")
def sendTopic(data):
    topic = data.get("topic")
    if topic:
        room = flask.session.get("room")
        if room not in STATUS["rooms"]:
            return

        STATUS["gpt"]["finished"][room] = threading.Event()
        STATUS["gemini"]["finished"][room] = threading.Event()

        content = {
            "name": "User",
            "message": f"토론 주제는 '{topic}' 입니다.",
            "timestamp": get_timestamp_utc(),  # 현재 시간을 UTC로 저장
            "is_typing": False
        }

        if topic.strip() != "":
            content["is_typing"] = False
            STATUS["rooms"][room]["messages"].append(content)

        log_event("Send", "User", content["message"])  # session.get("name")
        GPTmessage(content, room)


@socketio.on("connect")
def connect(auth):
    room = flask.session.get("room")
    topic = flask.session.get("topic")
    if not room or not topic:
        return
    if room not in STATUS["rooms"]:
        flask_socketio.leave_room(room)
        return

    flask_socketio.join_room(room)

    name = "User"  # session.get("name")
    content = {
        "name": name,
        "message": f"{name} has entered the room",
        "timestamp": get_timestamp_utc(),
    }

    socketio.emit("notification", content, room=room)
    STATUS["rooms"][room]["members"] += 1
    print(f"{name} joined room {room}")


@socketio.on("disconnect")
def disconnect():
    room = flask.session.get("room")
    name = "User"  # session.get("name")

    flask_socketio.leave_room(room)
    if room in STATUS["rooms"]:
        STATUS["rooms"][room]["members"] -= 1
        if STATUS["rooms"][room]["members"] <= 0:
            del STATUS["rooms"][room]

    flask_socketio.send(
        {"name": name, "message": "has left the room"}, to=room
    )
    print(f"{name} has left the room {room}")


@app.route("/room")
def room():
    room = flask.session.get("room")
    topic = flask.session.get("topic")
    if room is None or topic is None or room not in STATUS["rooms"]:
        return flask.redirect(flask.url_for("home"))

    STATUS["count"] = 0
    return flask.render_template(
        "room.html",
        code=room,
        topic=topic,
        messages=STATUS["rooms"][room]["messages"]
    )


@app.route("/", methods=["POST", "GET"])
def home():
    flask.session.clear()

    if flask.request.method == "POST":
        topic = flask.request.form.get("topic")
        if not topic:
            random_topics = random.sample(TOPIC_POOL, 3)
            return flask.render_template(
                "home.html",
                error="Please enter a topic."
            )

        room = generate_unique_code(2)
        STATUS["rooms"][room] = {"members": 0, "messages": []}

        flask.session["room"] = room
        flask.session["topic"] = topic

        return flask.redirect(flask.url_for("room"))
    # GET 요청일 때
    random_topics = random.sample(TOPIC_POOL, 3)
    return flask.render_template("home.html", random_topics=random_topics)


THREADS = {
    "gpt": threading.Thread(target=worker, daemon=True),
    "gemini": threading.Thread(target=gemini_worker, daemon=True)
}
for thread in THREADS.values():
    thread.start()

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
