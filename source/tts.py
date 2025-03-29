import configparser

from google.oauth2 import service_account
from google.cloud import texttospeech

with open('config.ini', 'r') as f:
    _config = configparser.ConfigParser()
    _config.read_file(f)

_credentials = service_account.Credentials.from_service_account_file(
    filename=_config['GOOGLE']['credentials_path']
)

class TTS():
    def __init__(self) -> None:
        self.config = {
            "language": "ko-KR",
            "voice": texttospeech.SsmlVoiceGender.NEUTRAL,
            "format": texttospeech.AudioEncoding.MP3
        }

        self._client = texttospeech.TextToSpeechClient(
            credentials=_credentials
        )
        self.voice = texttospeech.VoiceSelectionParams(
            language_code=self.config['language'],
            ssml_gender=self.config['voice']
        )
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=self.config['format']
        )

    def request(self, text):
        synthesis_input = texttospeech.SynthesisInput(text=text)
        response = self._client.synthesize_speech(
            input=synthesis_input,
            voice=self.voice,
            audio_config=self.audio_config
        )

        return response


if __name__ == "__main__":
    text = "안녕하세요. TTS test 입니다."

    tts = TTS()
    response = tts.request(text)

    with open("output.mp3", "wb") as out:
        out.write(response.audio_content)
