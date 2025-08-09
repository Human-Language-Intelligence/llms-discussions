from google.oauth2 import service_account
from google import genai

from .config import CONFIG as _CONFIG


class Gemini():
    def __init__(self, system_prompt: str = "") -> None:
        self.model_name = _CONFIG["google"]["GEMINI.MODEL_NAME"]
        self.client = None
        self.conversations = []
        self.system_prompt = system_prompt

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
                system_instruction=self.system_prompt,
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
