import configparser

from google.oauth2 import service_account
from google.cloud import aiplatform
from vertexai import generative_models

with open('config.ini', 'r') as f:
    _CONFIG = configparser.ConfigParser()
    _CONFIG.read_file(f)


class Gemini():
    def __init__(self, history):
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
        self.conversations = self.convert_history(history)

        self.connect_session()
        self.connect_chat()

    def connect_session(self):
        self.client = generative_models.GenerativeModel(
            model_name=self.model_name,
            # safety_settings=
        )

    def connect_chat(self):
        self.chat = self.client.start_chat(history=self.conversations)

    def get_response(self, text):
        response = self.chat.send_message(text)
        probability = [_.avg_logprobs for _ in response.candidates]
        result = [
            _.text for _ in response.candidates[
                probability.index(max(probability))
            ].content.parts if hasattr(_, 'text')
        ]

        return result

    def convert_history(self, contents):
        history = [
            generative_models.Content(
                role=content.get('role'),
                parts=[
                    generative_models.Part.from_text(part.get('text')) for part in content.get('parts')
                ]
            ) for content in contents
        ]
        return history


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
    text = '인사해줘.'

    gemini = Gemini(history)
    response = gemini.get_response(text)

    print(response)
