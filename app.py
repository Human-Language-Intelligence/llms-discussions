import base64
import string
import time
import random
import queue
import threading
import configparser
import flask
import flask_socketio

from datetime import datetime, timezone
from fuzzywuzzy import fuzz

from source.gemini import Gemini
from source.chatgpt import ChatGPT
from source.tts import TTS


CONFIG = configparser.ConfigParser()
CONFIG.read("config.ini")

app = flask.Flask(__name__)
app.secret_key = CONFIG['flask']['SECRET_KEY']
socketio = flask_socketio.SocketIO(app)

tts_M = TTS(3)
tts_F = TTS(1)

# "You are a debater with opposing views."}]
gpt_history = [
    {
        "role": "system",
        "content": "You will take a position in favor of the given topic. Counter the opposing viewpoint and assert your own opinion in Korean. Your response should not exceed 3 lines."
    }
]
gemini_history = [
    {
        "role": "user",
        "parts": [
            {"text": "System prompt: You will take a position against the given topic. Counter the opposing viewpoint and assert your own opinion in Korean. Your response should not exceed 3 lines."}
        ],
    },
    {
        "role": "model",
        "parts": [{"text": "이해했습니다."}],
    },
]

gpt = ChatGPT(gpt_history)
gemini = Gemini(gemini_history)

work_queue = queue.Queue()
gemini_work_queue = queue.Queue()
gpt_lock = threading.Lock()

# gpt 응답 생성 여부 추적
gpt_response_in_progress = {}
gemini_response_in_progress = {}
# user_prompt_point = {}
rooms = {}
auto_stop = 0


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

        if code not in rooms:
            break

    return code


def log_event(event_type, username, additional_info=""):
    # 이벤트를 로그에 기록
    with open('events.log', 'a') as log_file:
        log_file.write(
            f"{get_timestamp_utc()} - {username} - {event_type}: {additional_info}\n")


def worker():
    global auto_stop
    while auto_stop < 10:
        chatgpt_response, room = work_queue.get()
        if chatgpt_response is None:
            break
        content = send_gpt_response(chatgpt_response, room)
        work_queue.task_done()
        Geminimessage(content, room)


def gemini_worker():
    global auto_stop
    while auto_stop < 10:
        gemini_response, room = gemini_work_queue.get()
        if gemini_response is None:
            break
        content = send_gemini_response(gemini_response, room)
        gemini_work_queue.task_done()
        GPTmessage(content, room)


worker_thread = threading.Thread(target=worker, daemon=True)
worker_thread.start()

gemini_worker_thread = threading.Thread(target=gemini_worker, daemon=True)
gemini_worker_thread.start()


def send_gpt_response(chatgpt_response, room):
    content = {
        "name": "ChatGPT",
        "timestamp": get_timestamp_utc(),
        "is_typing": True,
    }

    for i, partial_response in enumerate(chatgpt_response):
        # 만들고 있던 응답을 여기서 삭제
        if gpt_response_in_progress.get(room) == False:
            gpt.append_history("assistant", chatgpt_response[:i+1])
            time.sleep(1)
            if len(sofar_message) > 120:
                content["is_typing"] = False
                content["message"] = content["message"] + "..."
                socketio.emit("gpt-message", content, room=room)
                log_event("Send", "ChatGPT", content["message"])
                return
            socketio.emit("clear-gpt-response", room=room)
            time.sleep(1)
            return

        sofar_message = chatgpt_response[:i+1]
        content["message"] = sofar_message

        if i == len(chatgpt_response) - 1:
            content["is_typing"] = False
            gpt_response_in_progress[room] = False

            try:
                tts_response = tts_F.request(content["message"])
                audio_base64 = base64.b64encode(tts_response).decode('utf-8')
                content["audio_base64"] = audio_base64
            except Exception as e:
                print("TTS error:", e)

        socketio.emit("gpt-message", content, room=room)

        time.sleep(get_random_time())
        if content["is_typing"] == False:
            gpt.append_history("assistant", chatgpt_response[:i+1])
            log_event("Send", "ChatGPT", content["message"])
        elif content["is_typing"] == True:
            log_event("Keystroke", "ChatGPT", content["message"])

        # Interrupt
        # if len(content['message']) > 100: ############# 쌍방채팅 여기서 조정
        #    if random.random() < 0.01:#if random.randint(0, 1) == 1:
        #        Geminimessage(content, room)

    return content


def send_gemini_response(gemini_response, room):
    content = {
        "name": "Gemini",
        "timestamp": get_timestamp_utc(),
        "is_typing": True,
    }

    for i, partial_response in enumerate(gemini_response):
        # 만들고 있던 응답을 여기서 삭제
        if gemini_response_in_progress.get(room) == False:
            gemini.append_history("assistant", gemini_response[:i+1])
            time.sleep(1)
            if len(sofar_message) > 120:
                content["is_typing"] = False
                content["message"] = content["message"] + "..."
                socketio.emit("gemini-message", content, room=room)
                log_event("Send", "Gemini", content["message"])
                return
            socketio.emit("clear-gemini-response", room=room)
            time.sleep(1)
            return

        sofar_message = gemini_response[:i+1]
        content["message"] = sofar_message

        if i == len(gemini_response) - 1:
            content["is_typing"] = False
            gemini_response_in_progress[room] = False

            try:
                tts_response = tts_M.request(content["message"])
                audio_base64 = base64.b64encode(tts_response).decode('utf-8')
                content["audio_base64"] = audio_base64
            except Exception as e:
                print("TTS error:", e)

        socketio.emit("gemini-message", content, room=room)
        time.sleep(get_random_time())
        if content["is_typing"] == False:
            gemini.append_history("assistant", gemini_response[:i+1])
            log_event("Send", "Gemini", content["message"])
        elif content["is_typing"] == True:
            log_event("Keystroke", "Gemini", content["message"])

        # Interrupt
        # if len(content['message']) > 100: ############# 쌍방채팅 여기서 조정
        #    if random.random() < 0.01:#if random.randint(0, 1) == 1:
        #        GPTmessage(content, room)
    return content


@socketio.on("gpt-message")
def GPTmessage(data, room):
    if data == None:
        return
    if data["name"] == "admin":
        return
    global auto_stop
    auto_stop += 1
    recent_user_typing = data["message"]

    with gpt_lock:
        if data["is_typing"] == False:
            gpt.append_history("user", recent_user_typing)
        if data["is_typing"] == True:
            # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
            if gpt_response_in_progress.get(room, False):
                # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
                if gemini_response_in_progress.get(room, False):
                    # 유저가 타이핑 중에 20퍼센트 이상 다른 문장을 치면 다른 문장으로 응답 생성
                    if fuzz.ratio(gemini_response_in_progress[room], recent_user_typing) < 60:
                        gpt_response_in_progress[room] = False
                        chatgpt_response = gpt.get_response()  # recent_user_typing)
                        # True
                        gpt_response_in_progress[room] = chatgpt_response
                        work_queue.put((chatgpt_response, room))
                        # 사용자가 보낸 메시지 저장
                        gemini_response_in_progress[room] = recent_user_typing
                return

            chatgpt_response = gpt.get_response()  # recent_user_typing)
            gpt_response_in_progress[room] = chatgpt_response  # True
            # 사용자가 보낸 메시지 저장
            gemini_response_in_progress[room] = recent_user_typing
            work_queue.put((chatgpt_response, room))

        if data["is_typing"] == False:
            # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!
            if gpt_response_in_progress.get(room, False):
                # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!
                if gemini_response_in_progress.get(room, False):
                    if fuzz.ratio(gemini_response_in_progress[room], recent_user_typing) > 60:
                        return
                    gpt_response_in_progress[room] = False
                    chatgpt_response = gpt.get_response()  # recent_user_typing)
                    gpt_response_in_progress[room] = chatgpt_response  # True
                    # 사용자가 보낸 메시지 저장
                    gemini_response_in_progress[room] = recent_user_typing
                    # 문제: 원래 치던 문장에서 send를 누르면 그걸 기반으로 다시 응답을 생성함.
                    work_queue.put((chatgpt_response, room))

            # else: # gpt 응답이 생성중이 아니라면 생성
            chatgpt_response = gpt.get_response()  # recent_user_typing)
            gpt_response_in_progress[room] = chatgpt_response  # True
            # 사용자가 보낸 메시지 저장
            gemini_response_in_progress[room] = recent_user_typing
            work_queue.put((chatgpt_response, room))


@socketio.on("gemini-message")
def Geminimessage(data, room):
    if data == None:
        return
    if data["name"] == "admin":
        return
    global auto_stop
    auto_stop += 1
    recent_user_typing = data["message"]

    with gpt_lock:
        if data["is_typing"] == True:
            # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
            if gemini_response_in_progress.get(room, False):
                # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
                if gpt_response_in_progress.get(room, False):
                    # 유저가 타이핑 중에 20퍼센트 이상 다른 문장을 치면 다른 문장으로 응답 생성
                    if fuzz.ratio(gpt_response_in_progress[room], recent_user_typing) < 60:
                        gemini_response_in_progress[room] = False
                        gemini_response = gemini.get_response(
                            recent_user_typing)
                        # True
                        gemini_response_in_progress[room] = gemini_response
                        gemini_work_queue.put((gemini_response, room))
                        # 사용자가 보낸 메시지 저장
                        gpt_response_in_progress[room] = recent_user_typing
                return

            gemini_response = gemini.get_response(recent_user_typing)
            gemini_response_in_progress[room] = gemini_response  # True
            # 사용자가 보낸 메시지 저장
            gpt_response_in_progress[room] = recent_user_typing
            gemini_work_queue.put((gemini_response, room))

        if data["is_typing"] == False:
            # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!
            if gemini_response_in_progress.get(room, False):
                if gpt_response_in_progress.get(room, False):
                    if fuzz.ratio(gpt_response_in_progress[room], recent_user_typing) > 60:
                        return
                    gemini_response_in_progress[room] = False
                    gemini_response = gemini.get_response(recent_user_typing)
                    gemini_response_in_progress[room] = gemini_response  # True
                    # 사용자가 보낸 메시지 저장
                    gpt_response_in_progress[room] = recent_user_typing
                    # 문제: 원래 치던 문장에서 send를 누르면 그걸 기반으로 다시 응답을 생성함.
                    gemini_work_queue.put((gemini_response, room))
            # else: # gpt 응답이 생성중이 아니라면 생성
            gemini_response = gemini.get_response(recent_user_typing)
            gemini_response_in_progress[room] = gemini_response  # True
            # 사용자가 보낸 메시지 저장
            gpt_response_in_progress[room] = recent_user_typing
            gemini_work_queue.put((gemini_response, room))


@socketio.on("message")
def message(data):
    room = flask.session.get("room")
    if room not in rooms:
        return

    content = {
        "name": "User",  # session.get("name"),
        "message": data["data"],
        "timestamp": get_timestamp_utc(),  # 현재 시간을 UTC로 저장
        "is_typing": False
    }

    if data["data"].strip():
        content["is_typing"] = False
        rooms[room]["messages"].append(content)
    else:
        return

    socketio.emit("message", content, room=room)
    # 키스트로크를 로그에 기록
    log_event("Send", "User", content["message"])  # session.get("name")
    GPTmessage(content, room)


@socketio.on("typing")
def handle_typing(data):
    room = flask.session.get("room")
    if room not in rooms:
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
    if len(content['message']) > 70:  # 쌍방채팅 여기서 조정
        if random.randint(0, 1) == 1:
            GPTmessage(content)


@socketio.on("live-toggle")
def handle_live_toggle(data):
    room = flask.session.get("room")
    if room not in rooms:
        return

    name = "User"  # session.get("name")
    content = {
        "name": "User",  # session.get("name"),
        "message": f"{name} has gone {data['status']}",
        "timestamp": get_timestamp_utc(),
    }

    socketio.emit("notification", content, room=room)
    log_event("toggle", "User", data["status"])  # session.get("name"),


@socketio.on('sendTopic')
def sendTopic(data):
    topic = data.get('topic')
    if topic:
        room = flask.session.get("room")
        if room not in rooms:
            return

        content = {
            "name": "User",
            "message": '토론 주제는 "'+topic+'" 입니다.',
            "timestamp": get_timestamp_utc(),  # 현재 시간을 UTC로 저장
            "is_typing": False
        }

        if topic.strip() != "":
            content["is_typing"] = False
            rooms[room]["messages"].append(content)

        log_event("Send", "User", content["message"])  # session.get("name")
        GPTmessage(content, room)


@socketio.on("connect")
def connect(auth):
    room = flask.session.get("room")
    topic = flask.session.get("topic")
    if not room or not topic:
        return
    if room not in rooms:
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
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")


@socketio.on("disconnect")
def disconnect():
    room = flask.session.get("room")
    name = "User"  # session.get("name")

    flask_socketio.leave_room(room)
    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]

    flask_socketio.send(
        {"name": name, "message": "has left the room"}, to=room
    )
    print(f"{name} has left the room {room}")


@app.route("/", methods=["POST", "GET"])
def home():
    flask.session.clear()
    if flask.request.method == "POST":
        topic = flask.request.form.get("topic")
        if not topic:
            return flask.render_template("home.html", error="Please enter a topic.")

        room = generate_unique_code(2)
        rooms[room] = {"members": 0, "messages": []}

        flask.session["room"] = room
        flask.session["topic"] = topic

        return flask.redirect(flask.url_for("room"))

    return flask.render_template("home.html")


@app.route("/room")
def room():
    room = flask.session.get("room")
    topic = flask.session.get("topic")
    if room is None or topic is None or room not in rooms:
        return flask.redirect(flask.url_for("home"))

    return flask.render_template(
        "room.html",
        code=room,
        topic=topic,
        messages=rooms[room]["messages"]
    )


if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
