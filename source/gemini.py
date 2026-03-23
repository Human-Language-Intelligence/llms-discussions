from google import genai
from google.oauth2 import service_account


class Gemini:
    def __init__(self, model, credential_file=None, project=None) -> None:
        self.model_name = model
        self.project = project
        self.credential_file = service_account.Credentials.from_service_account_file(
            filename=credential_file,
            scopes=["https://www.googleapis.com/auth/cloud-platform"],
        )
        self.client = None
        self.conversations = []
        self.system_prompt = ""

        self.connect_session()

    def connect_session(self) -> None:
        self.client = genai.Client(
            vertexai=True,
            credentials=self.credential_file,
            project=self.project,
        )
        self.create_chat()

    def create_chat(self):
        self.chat = self.client.chats.create(
            model=self.model_name,
            config=genai.types.GenerateContentConfig(
                system_instruction=self.system_prompt,
                thinking_config=genai.types.ThinkingConfig(
                    # thinking_budget=-1,
                    thinking_level="low"
                ),
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
                ],
            ),
            history=self.conversations,
        )

    def set_system_prompt(self, system_prompt: str) -> None:
        self.system_prompt = system_prompt
        self.create_chat()

    def get_response(self, text: str) -> str:
        if not text:
            return ""

        self.append_history("user", text)
        response = self.chat.send_message(text)
        output = response.text

        return output

    def convert_content(self, content: dict) -> genai.types.Content:
        chat = genai.types.Content(
            role=content.get("role"),
            parts=[
                genai.types.Part.from_text(text=part.get("text"))
                for part in content.get("parts")
            ],
        )
        return chat

    def convert_history(self, contents: list) -> None:
        self.conversations = [self.convert_content(content) for content in contents]

    def append_history(self, role: str, text: str) -> None:
        content = {
            "role": role,
            "parts": [{"text": text}],
        }
        content = self.convert_content(content)

        self.conversations.append(content)
        self.create_chat()
