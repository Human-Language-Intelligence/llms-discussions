from openai import OpenAI


class ChatGPT:
    def __init__(self, model, key=None) -> None:
        self.model_name = model
        self.key = key
        self.client = None
        self.system_prompt = ""
        self.conversations = []

        self.connect_session()

    def connect_session(self) -> None:
        self.client = OpenAI(api_key=self.key)

    def set_system_prompt(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt
        self.append_history(role="system", text=system_prompt)

    def get_response(self, text: str = "") -> str:
        if not text:
            return ""

        self.append_history(role="user", text=text)
        response = self.client.responses.create(
            model=self.model_name, reasoning={"effort": "low"}, input=self.conversations
        )
        output = response.output_text
        self.append_history("assistant", output)

        return output

    def append_history(self, role: str, text: str) -> None:
        history = {"role": role, "content": text}
        self.conversations.append(history)
