from openai import OpenAI

from .config import CONFIG as _CONFIG


class ChatGPT():
    def __init__(self, system_prompt: str = "") -> None:
        self.model_name = _CONFIG["openai"]["GPT.MODEL_NAME"]
        self.client = None
        self.conversations = []

        if system_prompt:
            self.append_history(
                role="system",
                text=system_prompt
            )
        self.connect_session()

    def connect_session(self) -> None:
        self.client = OpenAI(
            api_key=_CONFIG["openai"]["GPT.API_KEY"]
        )

    def get_response(self, text: str = "") -> str:
        if not text:
            return ""

        self.append_history(role="user", text=text)
        response = self.client.responses.create(
            model=self.model_name,
            reasoning={
                "effort": "minimal"
            },
            input=self.conversations
        )
        output = response.output_text
        self.append_history("assistant", output)

        return output

    def append_history(self, role: str, text: str) -> None:
        history = {
            "role": role,
            "content": text
        }
        self.conversations.append(history)
