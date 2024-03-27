from flask import Flask, render_template, request, session, redirect, url_for, request
from flask_socketio import join_room, leave_room, send, SocketIO
import random
from string import ascii_uppercase
from datetime import datetime 
import time 
import random
from openai import OpenAI
from fuzzywuzzy import fuzz
import queue
import threading 
from collections import deque

app = Flask(__name__)
app.config["SECRET_KEY"] = "hjhjsdahhds"
socketio = SocketIO(app)

import pathlib 
from helper import to_markdown
import google.generativeai as genai

client = OpenAI(
    api_key="" # anonymoize for submission 
)
GOOGLE_API_KEY = "" # anonymoize for submission

genai.configure(api_key=GOOGLE_API_KEY)

gemini_safety_settings = [
  {
    "category": "HARM_CATEGORY_HARASSMENT",
    "threshold": "BLOCK_NONE"
  },
  {
    "category": "HARM_CATEGORY_HATE_SPEECH",
    "threshold": "BLOCK_NONE"
  },
  {
    "category": "HARM_CATEGORY_SEXUALLY_EXPLICIT",
    "threshold": "BLOCK_NONE"
  },
  {
    "category": "HARM_CATEGORY_DANGEROUS_CONTENT",
    "threshold": "BLOCK_NONE"
  },
]
gemini_client = genai.GenerativeModel(model_name="gemini-pro",
                              safety_settings=gemini_safety_settings)

rooms = {}

work_queue = queue.Queue()
gemini_work_queue = queue.Queue()
gpt_lock = threading.Lock()

auto_stop = 0

def worker():
    global auto_stop
    while auto_stop < 10:
        chatgpt_response, room = work_queue.get()
        if chatgpt_response is None:
            break
        content = send_gpt_response(chatgpt_response, room)
        work_queue.task_done()
        Geminimessage(content, room)

worker_thread = threading.Thread(target=worker, daemon=True)
worker_thread.start()

def gemini_worker():
    global auto_stop
    while auto_stop < 10:
        gemini_response, room = gemini_work_queue.get()
        if gemini_response is None:
            break
        content = send_gemini_response(gemini_response, room)
        gemini_work_queue.task_done()
        GPTmessage(content, room)

gemini_worker_thread = threading.Thread(target=gemini_worker, daemon=True)
gemini_worker_thread.start()


def generate_unique_code(length):
    while True:
        code = ""
        for _ in range(length):
            code += random.choice(ascii_uppercase)
        
        if code not in rooms:
            break
    
    return code

@app.route("/", methods=["POST", "GET"])
def home():
    session.clear()
    if request.method == "POST":
        topic = request.form.get("topic")
        if not topic:
            return render_template("home.html", error="Please enter a topic.")

        room = generate_unique_code(2)
        rooms[room] = {"members": 0, "messages": []}
        
        session["room"] = room
        session["topic"] = topic
        return redirect(url_for("room"))

    return render_template("home.html")

@app.route("/room")
def room():
    room = session.get("room")
    topic = session.get("topic")
    
    if room is None or topic is None or room not in rooms:
        return redirect(url_for("home"))
    
    return render_template("room.html", code=room, topic=topic, messages=rooms[room]["messages"])

conversation = [{"role": "system", "content":"You will take a position in favor of the given topic and proceed with the debate in Korean. Your response should not exceed 5 lines."}]# "You are a debater with opposing views."}]
gemini_conversation = [{
        "role": "user",
        "parts": [{ "text": "System prompt: You will take a position against the given topic and proceed with the debate in Korean. Your response should not exceed 5 lines."}],
      },
      {
        "role": "model",
        "parts": [{ "text": "Understood."}],
      },]#[{"role": "system", "parts":["You are a debater with opposing views."]}]
gemini_chat = gemini_client.start_chat(history=gemini_conversation)

def get_chatgpt_response():
    chat_completion = client.chat.completions.create(
        messages=conversation, 
        model="gpt-3.5-turbo",
    )
    return chat_completion.choices[0].message.content

def get_gemini_response(user_input):
    chat_completion = gemini_chat.send_message(user_input)
    return chat_completion.text

@socketio.on("message")
def message(data):
    room = session.get("room")
    if room not in rooms:
        return 
    
    content = {
        "name": "User",#session.get("name"),
        "message": data["data"],
        "timestamp": datetime.utcnow().isoformat(),  # 현재 시간을 UTC로 저장
        "is_typing": False  
    }

    if content["message"].strip() == "":
        return

    if data["data"].strip() != "":
        content["is_typing"] = False
        rooms[room]["messages"].append(content)

    socketio.emit("message", content, room=room)
    # 키스트로크를 로그에 기록
    log_event("Send", "User", content["message"])#session.get("name")
    GPTmessage(content, room)

# gpt 응답 생성 여부 추적 
gpt_response_in_progress = {}
gemini_response_in_progress = {}
#user_prompt_point = {}

def send_gpt_response(chatgpt_response, room):
    content = {
        "name": "ChatGPT",
        "timestamp": datetime.utcnow().isoformat(),
        "is_typing": True,
    }

    for i, partial_response in enumerate(chatgpt_response):
        if gpt_response_in_progress.get(room) == False: # 지피티가 만들고 있던 응답을 여기서 삭제 
            conversation.insert(-1, {"role": "assistant","content": chatgpt_response[:i+1]}) #FIX 
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

        socketio.emit("gpt-message", content, room=room)
        
        time.sleep(get_random_time())
        if content["is_typing"] == False: 
            conversation.append({"role": "assistant","content": chatgpt_response[:i+1]})
            log_event("Send", "ChatGPT", content["message"])
        elif content["is_typing"] == True:
            log_event("Keystroke", "ChatGPT", content["message"])
     
        #Interrupt   
        #if len(content['message']) > 100: ############# 쌍방채팅 여기서 조정 
        #    if random.random() < 0.01:#if random.randint(0, 1) == 1:
        #        Geminimessage(content, room)

    return content
    

def send_gemini_response(gemini_response, room):
    content = {
        "name": "Gemini",
        "timestamp": datetime.utcnow().isoformat(),
        "is_typing": True,
    }

    for i, partial_response in enumerate(gemini_response):
        if gemini_response_in_progress.get(room) == False: # 지피티가 만들고 있던 응답을 여기서 삭제 
            gemini_conversation.insert(-1, {"role": "assistant","content": gemini_response[:i+1]}) #FIX 
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

        socketio.emit("gemini-message", content, room=room)
        time.sleep(get_random_time())
        if content["is_typing"] == False: 
            gemini_conversation.append({"role": "assistant","content": gemini_response[:i+1]})
            log_event("Send", "Gemini", content["message"])
        elif content["is_typing"] == True:
            log_event("Keystroke", "Gemini", content["message"])
            
        #Interrupt
        #if len(content['message']) > 100: ############# 쌍방채팅 여기서 조정 
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
            conversation.append({"role": "user", "content": recent_user_typing})

        if data["is_typing"] == True:
            if gpt_response_in_progress.get(room, False): # room이라는 키가 존재하면 value값 반환, 없으면 False 반환 
                if gemini_response_in_progress.get(room, False): # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
                    if fuzz.ratio(gemini_response_in_progress[room], recent_user_typing) < 60: # 유저가 타이핑 중에 20퍼센트 이상 다른 문장을 치면 다른 문장으로 응답 생성  
                        gpt_response_in_progress[room] = False
                        chatgpt_response = get_chatgpt_response()#recent_user_typing)
                        gpt_response_in_progress[room] = chatgpt_response###True
                        work_queue.put((chatgpt_response, room))
                        gemini_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
                return 

            chatgpt_response = get_chatgpt_response()#recent_user_typing)
            gpt_response_in_progress[room] = chatgpt_response###True
            gemini_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
            work_queue.put((chatgpt_response, room))

        if data["is_typing"] == False:
            if gpt_response_in_progress.get(room, False): # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!  
                if gemini_response_in_progress.get(room, False): # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!  
                    if fuzz.ratio(gemini_response_in_progress[room], recent_user_typing) > 60: 
                        return 
                    gpt_response_in_progress[room] = False
                    chatgpt_response = get_chatgpt_response()#recent_user_typing)
                    gpt_response_in_progress[room] = chatgpt_response###True
                    gemini_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
                    work_queue.put((chatgpt_response, room)) # 문제: 원래 치던 문장에서 send를 누르면 그걸 기반으로 다시 응답을 생성함. 

            #else: # gpt 응답이 생성중이 아니라면 생성  
            chatgpt_response = get_chatgpt_response()#recent_user_typing)
            gpt_response_in_progress[room] = chatgpt_response###True
            gemini_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
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
            if gemini_response_in_progress.get(room, False): # room이라는 키가 존재하면 value값 반환, 없으면 False 반환 
                if gpt_response_in_progress.get(room, False): # room이라는 키가 존재하면 value값 반환, 없으면 False 반환
                    if fuzz.ratio(gpt_response_in_progress[room], recent_user_typing) < 60: # 유저가 타이핑 중에 20퍼센트 이상 다른 문장을 치면 다른 문장으로 응답 생성  
                        gemini_response_in_progress[room] = False
                        gemini_response = get_gemini_response(recent_user_typing)
                        gemini_response_in_progress[room] = gemini_response###True
                        gemini_work_queue.put((gemini_response, room))
                        gpt_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
                return 

            gemini_response = get_gemini_response(recent_user_typing)
            gemini_response_in_progress[room] = gemini_response###True
            gpt_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
            gemini_work_queue.put((gemini_response, room))

        if data["is_typing"] == False:
            if gemini_response_in_progress.get(room, False): # gpt 응답이 생성중이면 삭제하고 다시 생성해야함!
                if gpt_response_in_progress.get(room, False):
                    if fuzz.ratio(gpt_response_in_progress[room], recent_user_typing) > 60: 
                        return 
                    gemini_response_in_progress[room] = False
                    gemini_response = get_gemini_response(recent_user_typing)
                    gemini_response_in_progress[room] = gemini_response###True
                    gpt_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
                    gemini_work_queue.put((gemini_response, room)) # 문제: 원래 치던 문장에서 send를 누르면 그걸 기반으로 다시 응답을 생성함. 
            #else: # gpt 응답이 생성중이 아니라면 생성      
            gemini_response = get_gemini_response(recent_user_typing)
            gemini_response_in_progress[room] = gemini_response###True
            gpt_response_in_progress[room] = recent_user_typing # 사용자가 보낸 메시지 저장
            gemini_work_queue.put((gemini_response, room))

def get_random_time():
    # 베타 분포에서 랜덤한 값을 얻음
    value = random.betavariate(1, 3)
    # 값을 0.01과 0.7 사이의 범위로 스케일링
    return 0.01 + value * (0.35 - 0.01)

@socketio.on("typing")
def handle_typing(data):
    room = session.get("room")
    if room not in rooms:
        return

    content = {
        "name": "User",#session.get("name"),
        "message": data["message"],
        "is_typing": True
    }

    socketio.emit("message", content, room=room)

    # 키스트로크를 로그에 기록
    if data["message"].strip() != "":
        log_event("Keystroke", "User", data["message"])#session.get("name")
    
    if len(content['message']) > 70: ############# 쌍방채팅 여기서 조정 
        if random.randint(0, 1) == 1:
            GPTmessage(content)        

@socketio.on("live-toggle")
def handle_live_toggle(data):
    room = session.get("room")
    if room not in rooms:
        return
    
    name = "User"#session.get("name")

    content = {
        "name": "User",#session.get("name"),
        "message": f"{name} has gone {data['status']}",
        "timestamp": datetime.utcnow().isoformat(),
    }

    socketio.emit("notification", content, room=room)

    log_event("toggle", "User", data["status"]) #session.get("name"),

@socketio.on("connect")
def connect(auth):
    room = session.get("room")
    topic = session.get("topic")
    if not room or not topic:
        return
    if room not in rooms:
        leave_room(room)
        return
    
    join_room(room)
    name = "User"#session.get("name")
    content = {
        "name": name,
        "message": f"{name} has entered the room",
        "timestamp": datetime.utcnow().isoformat(),
    }
    socketio.emit("notification", content, room=room)
    rooms[room]["members"] += 1
    print(f"{name} joined room {room}")
    
@socketio.on('sendTopic')
def sendTopic(json):
    topic = json.get('topic')
    if topic != "":
        room = session.get("room")
        if room not in rooms:
            return 
        
        content = {
            "name": "User",
            "message": "토론 주제는 "+topic+" 입니다.",
            "timestamp": datetime.utcnow().isoformat(),  # 현재 시간을 UTC로 저장
            "is_typing": False  
        }

        if content["message"].strip() == "":
            return

        if topic.strip() != "":
            content["is_typing"] = False
            rooms[room]["messages"].append(content)

        log_event("Send", "User", content["message"])#session.get("name")
        GPTmessage(content, room)
        
@socketio.on("disconnect")
def disconnect():
    room = session.get("room")
    name = "User"##session.get("name")
    leave_room(room)

    if room in rooms:
        rooms[room]["members"] -= 1
        if rooms[room]["members"] <= 0:
            del rooms[room]

    send({"name": name, "message": "has left the room"}, to=room)
    print(f"{name} has left the room {room}")

def log_event(event_type, username, additional_info=""):
    # 이벤트를 로그에 기록
    with open('events.log', 'a') as log_file:
        log_file.write(f"{datetime.utcnow().isoformat()} - {username} - {event_type}: {additional_info}\n")

if __name__ == "__main__":
    socketio.run(app, host="0.0.0.0", port=80, debug=True)
