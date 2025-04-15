import threading
import queue
import base64

from . import utils


class ModelWorker:
    def __init__(self, name, model, tts, room=None):
        self.name = name
        self.model = model
        self.tts = tts
        self.room = room

        self.thread = threading.Thread(target=self.run, daemon=True)
        self.event = threading.Event()
        self.input_queue = queue.Queue()
        self.output_queue = None
        self.running = True

    def run(self):
        while self.running:
            try:
                user_input = self.input_queue.get()
            except queue.Empty:
                continue

            response = self.model.get_response(user_input)
            content = self.process_content(response)
            if self.room.event_bus:
                self.room.event_bus.publish(f"{self.name}-response", {
                    "room": self.room.room_id,
                    "content": content
                })
            self.room.append_message(content)
            self.wait_event()

            self.output_queue.put(response)
            self.input_queue.task_done()

    def process_content(self, message):
        content = {
            "name": self.name,
            "message": message,
            "audio_base64": "",
            "timestamp": utils.get_utc_timestamp(),
            "is_typing": False,
            "is_playing": False
        }
        try:
            audio = self.tts.request(message)
            audio_base64 = base64.b64encode(audio).decode("utf-8")
            content["audio_base64"] = audio_base64
            print(f"[{self.name}] 🎧 TTS 완료")
        except Exception as e:
            print(f"[{self.name}] TTS 오류:", e)

        return content

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
