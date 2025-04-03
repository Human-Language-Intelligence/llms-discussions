import configparser

from google.oauth2 import service_account
from google.cloud import texttospeech

with open('config.ini', 'r') as f:
    _CONFIG = configparser.ConfigParser()
    _CONFIG.read_file(f)


class TTS():
    def __init__(self, voice=1) -> None:
        voices = {
            1: 'ko-KR-Standard-A',
            2: 'ko-KR-Standard-B',
            3: 'ko-KR-Standard-C',
            4: 'ko-KR-Standard-D',
            5: 'ko-KR-Chirp3-HD-Aoede',
            6: 'ko-KR-Chirp3-HD-Orus',

        }
        self.config = {
            "language": "ko-KR",
            "voice": voices[voice] if voice in voices.keys() else None,
            "format": texttospeech.AudioEncoding.OGG_OPUS
        }

        self._client = texttospeech.TextToSpeechClient(
            credentials=service_account.Credentials.from_service_account_file(
                filename=_CONFIG['google']['CREDENTIALS']
            )
        )
        self.voice = texttospeech.VoiceSelectionParams(
            language_code=self.config['language'],
            name=self.config['voice'],
            # ssml_gender=
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

    tts = TTS(0)
    tts.config['format'] = texttospeech.AudioEncoding.MP3
    response = tts.request(text)

    with open("output.mp3", "wb") as out:
        out.write(response)
