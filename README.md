# llms-discussions

## Install requirements

``` shell
uv venv .venv
source .venv/bin/activate
```

```shell
uv sync
```

## Config

```ini
[default]
TOPIC = [
        "AI가 인간을 대체할 수 있는가?",
        "화성 이주는 현실적인가?",
        "온라인 교육이 오프라인 교육을 대체할 수 있을까?",
        "기후 변화는 개인의 책임인가?",
        "NFT는 예술의 미래인가?",
        "프라이버시 vs 보안: 무엇이 더 중요한가?",
        "자율주행차의 윤리적 책임은 누구에게 있는가?"
    ]
HISTORY.POSITIVE = You are a skilled debater arguing FOR the given topic. Respond in Korean, using 3~5 sentences of plain text. Focus on one strong, persuasive argument supported by a brief metaphor, simple but credible statistics, or a quick real-world example. Directly address and refute the opponent’s main point in 1–2 sentences before presenting your counterargument. Maintain a confident yet respectful tone throughout.
HISTORY.NEGATIVE = You are a skilled debater arguing AGAINST the given topic. Respond in Korean, using 3~5 sentences of plain text. Focus on one strong, persuasive argument supported by a brief metaphor, simple but credible statistics, or a quick real-world example. Directly address and refute the opponent’s main point in 1–2 sentences before presenting your counterargument. Maintain a confident yet respectful tone throughout.

[flask]
SECRET_KEY = @@@

[openai]
GPT.API_KEY = @@@
GPT.MODEL_NAME = gpt-5-nano

[google]
CREDENTIALS = @@@.json
GCP.PROJECT_ID = @@@
GCP.LOCATION = us-west1
GEMINI.MODEL_NAME = gemini-2.5-flash-lite
```

You need to generate "config.ini" file, and replace the `@@@` placeholder in the "config.ini" file with the appropriate value. Before that, you must create credential keys for both GCP and OpenAI.
- [GCP Service Accouunt credentials](https://cloud.google.com/iam/docs/keys-create-delete)
- [OpenAI API key](https://platform.openai.com/settings/organization/api-keys)

## Run flask app

```shell
flask run --debug
```
