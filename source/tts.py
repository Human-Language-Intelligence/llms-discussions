import configparser

from google.oauth2 import service_account
from google.cloud import texttospeech

with open('config.ini', 'r') as f:
    _CONFIG = configparser.ConfigParser()
    _CONFIG.read_file(f)


class TTS():
    def __init__(self, voice=3) -> None:
        self.config = {
            "language": "ko-KR",
            "voice": voice,
            "format": texttospeech.AudioEncoding.OGG_OPUS
        }

        self._client = texttospeech.TextToSpeechClient(
            credentials=service_account.Credentials.from_service_account_file(
                filename=_CONFIG['google']['CREDENTIALS']
            )
        )
        self.voice = texttospeech.VoiceSelectionParams(
            language_code=self.config['language'],
            ssml_gender=self.config['voice']
        )
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=self.config['format']
        )

    def request(self, text: str) -> bytes:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        response = self._client.synthesize_speech(
            input=synthesis_input,
            voice=self.voice,
            audio_config=self.audio_config
        )

        return response.audio_content


if __name__ == "__main__":
    text = "안녕하세요. TTS test 입니다."

    tts = TTS(1)
    tts.config['format'] = texttospeech.AudioEncoding.MP3
    response = tts.request(text)

    with open("output.mp3", "wb") as out:
        out.write(response)
