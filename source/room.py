import threading

from . import worker, gemini, chatgpt, tts
from .config import CONFIG as _CONFIG


class Room:
    def __init__(self, room_id, model_pros="gpt", model_cons="gemini", event_bus=None):
        self.room_id = room_id
        self.event_bus = event_bus
        self.lock = threading.Lock()
        self.members = 0
        self.count = 0
        self.messages = []
        self.threads = {
            "pros": worker.ModelWorker(
                self,
                "pros",
                self.select_model(model_pros, "pros"),
                tts.TTS(1),
            ),
            "cons": worker.ModelWorker(
                self,
                "cons",
                self.select_model(model_cons, "cons"),
                tts.TTS(3)
            )
        }

        self.threads["pros"].set_output_queue(
            self.threads["cons"].input_queue
        )
        self.threads["cons"].set_output_queue(
            self.threads["pros"].input_queue
        )

    def select_model(self, model, role):
        models = {
            "gpt": chatgpt.ChatGPT,
            "gemini": gemini.Gemini
        }
        prompt_key = "HISTORY.POSITIVE" if role == "pros" else "HISTORY.NEGATIVE"
        prompt = _CONFIG["default"][prompt_key]

        return models.get(model)(prompt)

    def append_message(self, message):
        with self.lock:
            if self.count >= 10:
                self.stop_threads()
            self.count += 1
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

    def wait_event(self, role):
        self.threads[role].wait_event()

    def set_event(self, role):
        self.threads[role].set_event()

    def check_event(self, role):
        return self.threads[role].event.is_set()

    def start_threads(self):
        with self.lock:
            for worker in self.threads.values():
                worker.start()

    def stop_threads(self):
        with self.lock:
            for worker in self.threads.values():
                worker.stop()
