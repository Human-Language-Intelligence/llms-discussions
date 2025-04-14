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

app = flask.Flask(__name__)
app.secret_key = CONFIG["flask"]["SECRET_KEY"]
socketio = flask_socketio.SocketIO(app)


class Room:
    def __init__(self, room_id):
        self.room_id = room_id
        self.lock = threading.Lock()
        self.members = 0
        self.count = 0
        self.messages = []
        self.threads = {}
        self.status = {
            "gpt": {
                "queue": queue.Queue(),
                "finished": threading.Event(),
                "progressing": ''
            },
            "gemini": {
                "queue": queue.Queue(),
                "finished": threading.Event(),
                "progressing": ''
            }
        }

        # 외부 의존성 주입
        self.gpt = ChatGPT(CONFIG["default"]["HISTORY.POSITIVE"])
        self.gemini = Gemini(CONFIG["default"]["HISTORY.NEGATIVE"])
        self.tts_m = TTS(3)
        self.tts_f = TTS(1)

    def handle_user_typing(self, side, data):
        """
        유저가 타이핑 중일 때 GPT와 Gemini 응답을 처리하는 함수.
        """
        recent_user_typing = data.get("message", "").strip()
        other_side = "gemini" if side == "gpt" else "gpt"

        if data["is_typing"]:
            # 진행 중인 문장 유사도 비교
            if fuzz.ratio(
                self.status[other_side]["progressing"],
                recent_user_typing
            ) < 60:
                self.status[side]["progressing"] = ''
                response = self.generate_response(side, recent_user_typing)
                return response
        else:
            if self.status[side]["progressing"]:
                if fuzz.ratio(
                    self.status[other_side]["progressing"],
                    recent_user_typing
                ) > 60:
                    return
                self.status[side]["progressing"] = ''
                response = self.generate_response(side, recent_user_typing)
                return response
            # 진행 중인 상태가 아니라면 새 응답을 생성
            response = self.generate_response(side, recent_user_typing)
            return response

    def generate_response(self, side, data):
        """
        GPT 또는 Gemini 모델에 맞는 응답을 생성하고 상태를 업데이트하는 함수.
        """
        if side == "gpt":
            response = self.gpt.get_response(data)
            self.status["gpt"]["progressing"] = response
            self.status["gpt"]["queue"].put(response)
            self.status["gemini"]["progressing"] = data
        elif side == "gemini":
            response = self.gemini.get_response(data)
            self.status["gemini"]["progressing"] = response
            self.status["gemini"]["queue"].put(response)
            self.status["gpt"]["progressing"] = data

        return response

    def send_response(self, side, data):
        data = "".join(data)
        try:
            if side == "gpt":
                tts_response = self.tts_f.request(data)
            elif side == "gemini":
                tts_response = self.tts_m.request(data)
            audio_base64 = base64.b64encode(tts_response)
        except Exception as e:
            print(f"TTS error for {side}:", e)
            audio_base64 = ""

        content = {
            "name": side,
            "is_typing": False,
            "timestamp": get_timestamp_utc(),
            "message": data,
            "audio_base64": audio_base64.decode("utf-8")
        }

        # 응답 전송
        socketio.emit(f"{side}-message", content, room=self.room_id)

        # 상태 업데이트
        self.status[side]["finished"].clear()
        self.status[side]["finished"].wait()
        self.count += 1

        return content

    def worker(self):
        while self.count < 10:
            response = self.status["gpt"]["queue"].get()
            if not response:
                break
            content = self.send_response("gpt", response)
            self.status["gpt"]["queue"].task_done()

            with self.lock:
                gemini_response = self.gemini.get_response(content["message"])
                self.status["gemini"]["queue"].put(gemini_response)

    def gemini_worker(self):
        while self.count < 10:
            response = self.status["gemini"]["queue"].get()
            if response is None:
                break
            content = self.send_response("gemini", response)
            self.status["gemini"]["queue"].task_done()

            with self.lock:
                chatgpt_response = self.gpt.get_response(content["message"])
                self.status["gpt"]["queue"].put(chatgpt_response)

    def start_threads(self):
        self.threads = {
            "gpt": threading.Thread(target=self.worker, daemon=True),
            "gemini": threading.Thread(target=self.gemini_worker, daemon=True)
        }
        for thread in self.threads.values():
            thread.start()

    def stop_threads(self):
        for thread in self.threads.values():
            thread.join(timeout=1)
            if thread.is_alive():
                thread.join()

    def add_member(self):
        self.members += 1

    def remove_member(self):
        self.members -= 1
        if self.members <= 0:
            room_manager.remove_room(self.room_id)

    def lock_room(self):
        self.lock.acquire()

    def unlock_room(self):
        self.lock.release()


class RoomManager:
    def __init__(self):
        self.rooms = {}

    def create_room(self):
        room_id = self.generate_room_id(2)
        room = Room(
            room_id=room_id
        )
        self.rooms[room_id] = room
        room.start_threads()
        return room_id

    def get_room(self, room_id):
        return self.rooms.get(room_id)

    def remove_room(self, room_id):
        room = self.rooms.get(room_id)

        with room.lock:
            if room:
                room.stop_threads()
                del self.rooms[room_id]

    def list_rooms(self):
        return list(self.rooms.keys())

    def generate_room_id(self, length=2):
        while True:
            code = ""
            for _ in range(length):
                code += random.choice(string.ascii_uppercase)
            if code not in self.rooms:
                break
        return code


room_manager = RoomManager()


def get_timestamp_utc() -> str:
    """현재 UTC 시간을 ISO 8601 형식으로 반환."""
    return datetime.now(timezone.utc).isoformat()


def get_random_time():
    # 베타 분포에서 랜덤한 값을 얻음
    value = random.betavariate(1, 3)
    # 값을 0.01과 0.7 사이의 범위로 스케일링
    return 0.01 + value * (0.35 - 0.01)


def log_event(event_type, username, additional_info=""):
    # 이벤트를 로그에 기록
    with open("events.log", "a") as log_file:
        log_file.write(
            f"{get_timestamp_utc()} - {username} - {event_type}: {additional_info}\n"
        )


@socketio.on("tts-finished")
def handle_tts_finished(data):
    room = data.get("room")
    side = data.get("side")

    if not (room and side):
        return

    room_manager.get_room(room).status[side]["finished"].set()


@socketio.on("gpt-message")
def gpt_message(data, room):
    if not data or data.get("name") == "admin":
        return

    room_manager.get_room(room).handle_user_typing("gpt", data)


@socketio.on("gemini-message")
def gemini_message(data, room):
    if not data or data.get("name") == "admin":
        return

    room_manager.get_room(room).handle_user_typing("gemini", data)


@socketio.on("message")
def handle_message(data):
    room = flask.session.get("room")
    name = flask.session.get("name", "user")
    message_text = data.get("data", "").strip()
    content = {
        "name": name,
        "message": message_text,
        "timestamp": get_timestamp_utc(),
        "is_typing": False
    }

    if not (room and message_text) or room not in room_manager.rooms:
        return

    # 메시지 저장 및 브로드캐스트
    room_manager.get_room(room).messages.append(content)

    # 로그 기록 및 GPT 응답 호출
    socketio.emit("message", content, room=room)
    gpt_message(content, room=room)

    log_event("Send", name, message_text)


@socketio.on("typing")
def handle_typing(data):
    room = flask.session.get("room")
    name = flask.session.get("name", "user")
    message_text = data.get("data", "").strip()
    content = {
        "name": name,
        "message": message_text,
        "is_typing": True,
    }

    if not room or room not in room_manager.rooms:
        return

    # 실시간 타이핑 메시지 전송
    socketio.emit("message", content, room=room)

    # 일정 길이 이상 메시지면 GPT 반응 확률적으로 호출
    if len(message_text) > 70 and random.randint(0, 1) == 1:
        gpt_message(content, room=room)

    log_event("Keystroke", name, message_text)


@socketio.on("live-toggle")
def handle_live_toggle(data):
    room = flask.session.get("room")
    name = flask.session.get("name", "user")
    status = data.get("status", "offline")
    content = {
        "name": name,
        "message": f"{name} has gone {status}",
        "timestamp": get_timestamp_utc(),
    }

    if not room or room not in room_manager.rooms:
        return

    socketio.emit("notification", content, room=room)

    log_event("Toggle", name, status)


@socketio.on("send-topic")
def handle_send_topic(data):
    room = flask.session.get("room")
    name = flask.session.get("name", "user")
    topic = data.get("topic", "").strip()
    content = {
        "name": name,
        "message": f"토론 주제는 '{topic}' 입니다.",
        "timestamp": get_timestamp_utc(),
        "is_typing": False,
    }

    if not (topic and room) or room not in room_manager.rooms:
        return

    # 메시지 저장
    room_manager.get_room(room).messages.append(content)
    # GPT 처리 함수 호출
    gpt_message(content, room=room)

    log_event("Send", name, content["message"])


@socketio.on("connect")
def handle_connect(auth):
    room = flask.session.get("room")
    topic = flask.session.get("topic")
    name = flask.session.get("name", "user")
    content = {
        "name": name,
        "message": f"{name} has entered the room",
        "timestamp": get_timestamp_utc(),
    }

    # 세션이나 유효한 방이 없으면 연결 중단
    if not (room and topic) or room not in room_manager.rooms:
        flask_socketio.leave_room(room)
        return

    flask_socketio.join_room(room)
    socketio.emit("notification", content, room=room)
    room_manager.get_room(room).add_member()

    log_event("Connect", name, content["message"])


@socketio.on("disconnect")
def handle_disconnect():
    room = flask.session.get("room")
    name = flask.session.get("name", "user")
    content = {
        "name": name,
        "message": "has left the room"
    }

    if room:
        flask_socketio.leave_room(room)
        # 퇴장 메시지 전송
        flask_socketio.send(
            content,
            to=room
        )
        if room in room_manager.rooms:
            room_manager.get_room(room).remove_member()

        log_event("Disconnect", name, content["message"])


@app.route("/room")
def room():
    room = flask.session.get("room")
    topic = flask.session.get("topic")

    if not (room and topic) or room not in room_manager.rooms:
        return flask.redirect(flask.url_for("home"))

    return flask.render_template(
        "room.html",
        code=room,
        topic=topic,
        messages=room_manager.get_room(room).messages
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

        room = room_manager.create_room()

        flask.session["room"] = room
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
