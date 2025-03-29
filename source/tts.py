import configparser

from google.oauth2 import service_account
from google.cloud import texttospeech

with open('config.ini', 'r') as f:
    config = configparser.ConfigParser()
    config.read_file(f)


class TTS():
    def __init__(self) -> None:
        _credentials = service_account.Credentials.from_service_account_file(
            filename=config['GOOGLE']['credentials_path']
        )
        self._client = texttospeech.TextToSpeechClient(
            credentials=_credentials
        )
        self._voice = texttospeech.VoiceSelectionParams(
            language_code="ko-KR",
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3
        )

    def request(self, text):
        synthesis_input = texttospeech.SynthesisInput(text=text)
        response = self._client.synthesize_speech(
            input=synthesis_input,
            voice=self._voice,
            audio_config=self.audio_config
        )

        return response


if __name__ == "__main__":
    text = "안녕하세요. TTS test 입니다."

    tts = TTS()
    response = tts.request(text)

    with open("output.mp3", "wb") as out:
        out.write(response.audio_content)
