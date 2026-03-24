import base64

from google.cloud import texttospeech
from google.oauth2 import service_account


class TTS:
    def __init__(self, voice=1, credential_file=None) -> None:
        voices = {
            1: "ko-KR-Standard-A",
            2: "ko-KR-Standard-B",
            3: "ko-KR-Standard-C",
            4: "ko-KR-Standard-D",
            5: "ko-KR-Chirp3-HD-Aoede",
            6: "ko-KR-Chirp3-HD-Orus",
        }
        self.config = {
            "language": "ko-KR",
            "voice": voices[voice] if voice in voices.keys() else None,
        }

        self._client = texttospeech.TextToSpeechClient(
            credentials=service_account.Credentials.from_service_account_file(
                filename=credential_file
            )
        )
        self.voice = texttospeech.VoiceSelectionParams(
            language_code=self.config["language"],
            name=self.config["voice"],
            # ssml_gender=
        )
        self.audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.OGG_OPUS
        )

    def request(self, text: str) -> bytes:
        synthesis_input = texttospeech.SynthesisInput(text=text)
        response = self._client.synthesize_speech(
            input=synthesis_input, voice=self.voice, audio_config=self.audio_config
        )

        return response.audio_content

    def decode(self, audio: bytes, format="utf-8"):
        return base64.b64encode(audio).decode(format)
