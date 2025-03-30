import configparser

from google.oauth2 import service_account
from google.cloud import aiplatform
from vertexai import generative_models

with open('config.ini', 'r') as f:
    _CONFIG = configparser.ConfigParser()
    _CONFIG.read_file(f)


class Gemini():
    def __init__(self, history: list) -> None:
        aiplatform.init(
            project=_CONFIG['google']['GCP.PROJECT_ID'],
            location=_CONFIG['google']['GCP.LOCATION'],
            credentials=service_account.Credentials.from_service_account_file(
                _CONFIG['google']['CREDENTIALS']
            )
        )

        self.model_name = _CONFIG["google"]['GEMINI.MODEL_NAME']
        self.client = None
        self.chat = None
        self.conversations = None

        self.convert_history(history)
        self.connect_session()
        self.connect_chat()

    def connect_session(self) -> None:
        self.client = generative_models.GenerativeModel(
            model_name=self.model_name,
            safety_settings={
                generative_models.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
                generative_models.HarmCategory.HARM_CATEGORY_HATE_SPEECH: generative_models.HarmBlockThreshold.BLOCK_NONE,
                generative_models.HarmCategory.HARM_CATEGORY_HARASSMENT: generative_models.HarmBlockThreshold.BLOCK_NONE,
                generative_models.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT: generative_models.HarmBlockThreshold.BLOCK_NONE
            }
        )

    def connect_chat(self) -> None:
        self.chat = self.client.start_chat(history=self.conversations)

    def get_response(self, text: str) -> str:
        response = self.chat.send_message(text)
        # probability = [_.avg_logprobs for _ in response.candidates]
        # result = [
        #     _.text for _ in response.candidates[
        #         probability.index(max(probability))
        #     ].content.parts if hasattr(_, 'text')
        # ]

        return response.text

    def convert_content(self, content: dict) -> generative_models.Content:
        content = generative_models.Content(
            role=content.get('role'),
            parts=[
                generative_models.Part.from_text(part.get('text')) for part in content.get('parts')
            ]
        )
        return content

    def convert_history(self, contents: list) -> None:
        self.conversations = [
            self.convert_content(content) for content in contents
        ]

    def append_history(self, role: str, text: str) -> None:
        content = {
            "role": role,
            "parts": [
                {"text": text}
            ],
        }
        history = self.convert_content(content)

        self.conversations.append(history)


if __name__ == "__main__":
    history = [
        {
            "role": "user",
            "parts": [
                {"text": "System prompt: You will take a position against the given topic. Counter the opposing viewpoint and assert your own opinion in Korean. Your response should not exceed 3 lines."}
            ],
        },
        {
            "role": "model",
            "parts": [
                {"text": "이해했습니다."}
            ],
        },
    ]

    gemini = Gemini(history)
    gemini.append_history('assistant', '학교는 연구를 위한 곳입니다.')
    response = gemini.get_response('위 내용에 대해서 답변해줘.')

    print(response)
