import threading
import queue
import base64

from . import content


class ModelWorker:
    def __init__(self, room, role, model, tts):
        self.room = room
        self.role = role
        self.name = model.model_name.split("-")[0]
        self.model = model
        self.tts = tts

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.event = threading.Event()
        self.input_queue = queue.Queue()
        self.output_queue = None
        self.running = True

    def process_content(self, message):
        data = content.MessageContent(
            name=self.name,
            type=self.role,
            message=message,
        ).to_dict()

        try:
            audio = self.tts.request(message)
            audio_base64 = base64.b64encode(audio).decode("utf-8")
            data["audio_base64"] = audio_base64
            print(f"[{self.name}] 🎧 TTS 완료")
        except Exception as e:
            print(f"[{self.name}] TTS 오류:", e)

        if self.room.event_bus:
            self.room.event_bus.publish(f"{self.role}-response", {
                "room": self.room.room_id,
                "data": data
            })
        self.room.append_message(data)

    def run(self):
        while self.running:
            try:
                user_input = self.input_queue.get()
            except queue.Empty:
                continue

            response = self.model.get_response(user_input)
            self.process_content(response)
            self.wait_event()

            self.output_queue.put(response)
            self.input_queue.task_done()

    def enqueue_input(self, user_input):
        self.input_queue.put(user_input)
        self.set_event()

    def start(self):
        self.thread.start()

    def stop(self):
        self.running = False
        self.thread.join()

    def wait_event(self):
        self.event.clear()
        self.event.wait()

    def set_event(self):
        self.event.set()

    def set_output_queue(self, queue):
        self.output_queue = queue
