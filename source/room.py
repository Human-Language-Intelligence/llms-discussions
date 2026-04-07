import threading

from source import worker
from source.api import gemini, gpt, tts
from source.config import CONFIG as _CONFIG


class Room:
    def __init__(self, room_id, model_pros="gpt", model_cons="gemini", event_bus=None):
        self.room_id = room_id
        self.event_bus = event_bus
        self.members = 0
        self.count = 0
        self.messages = []
        self.results = {}

        self.history_max = int(_CONFIG["default"]["HISTORY.SIZE"])
        self.history_prompt = {
            "pros": _CONFIG["default"]["HISTORY.POSITIVE"],
            "cons": _CONFIG["default"]["HISTORY.NEGATIVE"]
        }
        self.models = {
            "gpt": gpt.ChatGPT(
                _CONFIG["openai"]["GPT.MODEL_NAME"],
                key=_CONFIG["openai"]["GPT.API_KEY"],
            ),
            "gemini": gemini.Gemini(
                _CONFIG["google"]["GEMINI.MODEL_NAME"],
                credential_file=_CONFIG["google"]["CREDENTIALS"],
                project=_CONFIG["google"]["GCP.PROJECT_ID"],
            ),
        }
        self.lock = threading.Lock()
        self.threads = {
            "pros": worker.ModelWorker(
                self,
                "pros",
                model=self.select_model(model_pros, "pros"),
                tts=tts.TTS(1, credential_file=_CONFIG["google"]["CREDENTIALS"]),
            ),
            "cons": worker.ModelWorker(
                self,
                "cons",
                model=self.select_model(model_cons, "cons"),
                tts=tts.TTS(3, credential_file=_CONFIG["google"]["CREDENTIALS"]),
            ),
        }

        self.threads["pros"].set_output_queue(self.threads["cons"].input_queue)
        self.threads["cons"].set_output_queue(self.threads["pros"].input_queue)

    def select_model(self, model, role):
        prompt = self.history_prompt.get(role)
        model_obj = self.models.get(model)

        model_obj.set_system_prompt(prompt)

        return model_obj

    def start_debate(self, topic: str):
        self.threads["pros"].enqueue_input(topic)

    def append_message(self, message):
        with self.lock:
            self.count += 1
            if self.count >= self.history_max:
                self.stop_threads()
            self.messages.append(message)
        if len(self.messages) > 100:
            self.messages.pop(0)

    def user_message(self, message):
        for thread in self.threads.values():
            thread.model.append_history("user", message)

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
