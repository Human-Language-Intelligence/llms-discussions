# llms-discussions

## Install requirements

``` shell
uv venv
source .venv/bin/activate
```

```shell
uv sync
```

## Config

```ini
[default]
TOPIC = ./static/topic.json
HISTORY.POSITIVE = "You are a DEBATER arguing FOR the given topic. Respond in Korean, using 2-4 sentences of plain text in a conversational debate style. Deepen the argument, don't repeat it, and fact-check your opponent. Back your argument with an example, a statistic, or an analogy."
HISTORY.NEGATIVE = "You are a DEBATER arguing AGAINST the given topic. Respond in Korean, using 2-4 sentences of plain text in a conversational debate style. Deepen the argument, don't repeat it, and fact-check your opponent. Back your argument with an example, a statistic, or an analogy."
HISTORY.SIZE = 10
EVAL.PERSONA = ./static/persona.jsonl
EVAL.SIZE = 10

[flask]
SECRET_KEY = @@@

[openai]
GPT.API_KEY = @@@
GPT.MODEL_NAME = gpt-5.4-nano

[google]
CREDENTIALS = @@@.json
GCP.API_KEY = @@@
GCP.PROJECT_ID = @@@
GCP.LOCATION = us-west1
GEMINI.MODEL_NAME = gemini-3.1-flash-lite-preview
```

You need to generate "config.ini" file, and replace the `@@@` placeholder in the "config.ini" file with the appropriate value. Before that, you must create credential keys for both GCP and OpenAI.
- [GCP Service Accouunt credentials](https://cloud.google.com/iam/docs/keys-create-delete)
- [OpenAI API key](https://platform.openai.com/settings/organization/api-keys)

## Run flask app

```shell
flask run
```
