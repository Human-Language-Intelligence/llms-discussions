from dataclasses import dataclass, asdict, field

from . import utils


@dataclass
class MessageContent:
    name: str
    role: str
    message: str
    audio_base64: str = ""
    timestamp: str = field(default_factory=utils.get_utc_timestamp)
    is_typing: bool = False
    is_playing: bool = False

    def to_dict(self) -> dict:
        return asdict(self)
