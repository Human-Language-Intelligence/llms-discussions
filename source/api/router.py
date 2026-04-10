from openai import OpenAI


class LLMRouter:
    def __init__(self, model="openai/gpt-oss-120b:free", base="openrouter", key=""):
        self.model = model
        self.client = None
        self.bases = {
            "openrouter": {
                "url": "https://openrouter.ai/api/v1",
                "body": {
                    "provider": {
                        "sort": {
                            "by": "latency",
                            "partition": "none",
                        },
                        "order": ["sambanova"],
                    },
                    "reasoning": {"enabled": False},
                },
            },
            "vllm": {
                "url": "http://localhost:8000/v1",
                "body": {"chat_template_kwargs": {"enable_thinking": False}},
            },
        }
        self.base = self.bases.get(base)

        self.connect_session(key)

    def connect_session(self, key) -> None:
        self.client = OpenAI(
            base_url=self.base.get("url"),
            api_key=key,
        )

    def get_response(self, text="", messages=None):
        message = messages if messages is not None else [{"role": "user", "content": text}]
        body = self.base.get("body")

        completion = self.client.chat.completions.create(
            model=self.model,
            messages=message,
            # extra_headers={
            #     "HTTP-Referer": "<YOUR_SITE_URL>",  # Optional. Site URL for rankings on openrouter.ai.
            #     "X-OpenRouter-Title": "<YOUR_SITE_NAME>",  # Optional. Site title for rankings on openrouter.ai.
            # },
            extra_body=body
        )

        return completion.choices[0].message.content
