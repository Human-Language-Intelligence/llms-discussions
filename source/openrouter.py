from openai import OpenAI

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key="",
)
model = "deepseek/deepseek-r1-0528"
completion = client.chat.completions.create(
    # extra_headers={
    #     "HTTP-Referer": "<YOUR_SITE_URL>",  # Optional. Site URL for rankings on openrouter.ai.
    #     "X-OpenRouter-Title": "<YOUR_SITE_NAME>",  # Optional. Site title for rankings on openrouter.ai.
    # },
    model=model,
    messages=[{"role": "user", "content": "What is the meaning of life?"}],
    extra_body={
        "provider": {
            "sort": {
                "by": "price",
                "partition": "none",
            },
            # "order": ["sambanova/high-throughput", "sambanova"],
        }
    },
)

print(completion.choices[0].message.content)
