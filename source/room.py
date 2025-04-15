import threading

from . import worker, gemini, chatgpt, tts
from .config import CONFIG as _CONFIG


class Room:
    def __init__(self, room_id, event_bus=None):
        self.room_id = room_id
        self.event_bus = event_bus
        self.lock = threading.Lock()
        self.members = 0
        self.count = 0
        self.messages = []
        self.threads = {
            'gpt': worker.ModelWorker(
                "gpt",
                chatgpt.ChatGPT(_CONFIG["default"]["HISTORY.POSITIVE"]),
                tts.TTS(1),
                self
            ),
            'gemini': worker.ModelWorker(
                "gemini",
                gemini.Gemini(_CONFIG["default"]["HISTORY.NEGATIVE"]),
                tts.TTS(3),
                self
            )
        }

        self.threads['gpt'].set_output_queue(
            self.threads['gemini'].input_queue
        )
        self.threads['gemini'].set_output_queue(
            self.threads['gpt'].input_queue
        )

    def append_message(self, message):
        with self.lock:
            self.messages.append(message)
        if len(self.messages) > 100:
            self.messages.pop(0)

    def get_message(self):
        for i, msg in enumerate(self.messages):
            if not msg.get("is_playing"):
                self.messages[i]["is_playing"] = True
                return msg
        return None

    def add_member(self):
        self.members += 1

    def remove_member(self):
        self.members -= 1
        return self.members > 0

    def wait_event(self, side):
        self.threads[side].wait_event()

    def set_event(self, side):
        self.threads[side].set_event()

    def check_event(self, side):
        return self.threads[side].event.is_set()

    def start_threads(self):
        with self.lock:
            for worker in self.threads.values():
                worker.start()

    def stop_threads(self):
        with self.lock:
            for worker in self.threads.values():
                worker.stop()
