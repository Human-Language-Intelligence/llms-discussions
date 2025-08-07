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
        completion = self.client.chat.completions
        if text:
            self.append_history(role="user", text=text)
        response = completion.create(
            messages=self.conversations,
            model=self.model_name
        )
        probability = [_.logprobs for _ in response.choices]
        result = " ".join([
            value for key, value in response.choices[
                probability.index(max(probability))
            ].message if key == "content"
        ])

        return result

    def append_history(self, role: str, text: str) -> None:
        history = {
            "role": role,
            "content": text
        }
        self.conversations.append(history)


if __name__ == "__main__":
    history = "You will take a position in favor of the given topic. Counter the opposing viewpoint and assert your own opinion in Korean. Your response should not exceed 3 lines."

    gpt = ChatGPT(history)
    gpt.append_history("user", "학교는 연구를 위한 공간입니다.")
    response = gpt.get_response()

    print(response)
