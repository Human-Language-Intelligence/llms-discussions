from google.oauth2 import service_account
from google import genai

from .config import CONFIG as _CONFIG


class Gemini():
    def __init__(self, system_prompt: str = "") -> None:
        self.model_name = _CONFIG["google"]["GEMINI.MODEL_NAME"]
        self.client = None
        self.conversations = []

        if system_prompt:
            self.append_history(
                role="user",
                text=system_prompt
            )
        self.connect_session()

    def connect_session(self) -> None:
        self.client = genai.Client(
            vertexai=True,
            credentials=service_account.Credentials.from_service_account_file(
                _CONFIG["google"]["CREDENTIALS"],
                scopes=[
                    "https://www.googleapis.com/auth/cloud-platform"
                ]
            ),
            project=_CONFIG["google"]["GCP.PROJECT_ID"],
            location=_CONFIG["google"]["GCP.LOCATION"],
            http_options=genai.types.HttpOptions(
                api_version="v1"
            )
        )

    def get_response(self, text: str) -> str:
        if text:
            self.append_history("user", text)
        response = self.client.models.generate_content(
            model=self.model_name,
            contents=self.conversations,
            config=genai.types.GenerateContentConfig(
                safety_settings=[
                    genai.types.SafetySetting(
                        category=genai.types.HarmCategory.HARM_CATEGORY_UNSPECIFIED,
                        threshold=genai.types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    genai.types.SafetySetting(
                        category=genai.types.HarmCategory.HARM_CATEGORY_HATE_SPEECH,
                        threshold=genai.types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    genai.types.SafetySetting(
                        category=genai.types.HarmCategory.HARM_CATEGORY_HARASSMENT,
                        threshold=genai.types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    genai.types.SafetySetting(
                        category=genai.types.HarmCategory.HARM_CATEGORY_DANGEROUS_CONTENT,
                        threshold=genai.types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    genai.types.SafetySetting(
                        category=genai.types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                        threshold=genai.types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                    genai.types.SafetySetting(
                        category=genai.types.HarmCategory.HARM_CATEGORY_CIVIC_INTEGRITY,
                        threshold=genai.types.HarmBlockThreshold.BLOCK_NONE,
                    ),
                ]
            )
        )

        return response.text

    def convert_content(self, content: dict) -> genai.types.Content:
        content = genai.types.Content(
            role=content.get("role"),
            parts=[
                genai.types.Part.from_text(text=part.get("text")) for part in content.get("parts")
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
    history = "System prompt: You will take a position against the given topic. Counter the opposing viewpoint and assert your own opinion in Korean. Your response should not exceed 3 lines."

    gemini = Gemini(history)
    gemini.append_history("assistant", "학교는 연구를 위한 곳입니다.")
    response = gemini.get_response("위 내용에 대해서 답변해줘.")

    print(response)
