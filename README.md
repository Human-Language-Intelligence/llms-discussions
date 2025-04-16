# llms-discussions

## Install requirements

``` shell
pip install -U -r requirements.txt
```

## Config

```ini
[flask]
SECRET_KEY = @@@

[openai]
GPT.API_KEY = @@@
GPT.MODEL_NAME = gpt-4o-mini

[google]
CREDENTIALS = @@@.json
GCP.PROJECT_ID = @@@
GCP.LOCATION = us-west1
GEMINI.MODEL_NAME = gemini-2.0-flash-lite
```

Replace the '@@@' placeholder in the config.ini file with the appropriate value. Before that, you must create credential keys for both GCP and OpenAI.
- [GCP Service Accouunt credentials](https://cloud.google.com/iam/docs/keys-create-delete)
- [OpenAI API key](https://platform.openai.com/settings/organization/api-keys)

## Run flask app

```shell
flask run --debug
```


