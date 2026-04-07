from openai import OpenAI


class OpenRouter:
    def __init__(self, model="openai/gpt-oss-120b:free", key=None):
        self.client = OpenAI(
            base_url="https://openrouter.ai/api/v1",
            api_key=key,
        )
        self.model = model

    def get_response(self, text="", messages=[]):
        message = [{"role": "user", "content": text}] if text else messages
        completion = self.client.chat.completions.create(
            # extra_headers={
            #     "HTTP-Referer": "<YOUR_SITE_URL>",  # Optional. Site URL for rankings on openrouter.ai.
            #     "X-OpenRouter-Title": "<YOUR_SITE_NAME>",  # Optional. Site title for rankings on openrouter.ai.
            # },
            model=self.model,
            messages=message,
            extra_body={
                "provider": {
                    "sort": {
                        "by": "price",
                        "partition": "none",
                    },
                    "order": ["sambanova"],
                }
            },
        )

        return completion.choices[0].message.content
