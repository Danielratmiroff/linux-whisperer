import pyaudio
from pydantic import BaseModel, Field


class AudioConfig(BaseModel):
    """Audio configuration settings with validation."""
    FORMAT: int = Field(
        default=pyaudio.paInt16,
        description="Audio format"
    )
    CHANNELS: int = Field(
        default=1,
        description="Number of audio channels"
    )
    RATE: int = Field(
        default=44100,
        description="Sample rate in Hz"
    )
    CHUNK: int = Field(
        default=1024,
        description="Frames per buffer"
    )
    RECORD_SECONDS: int = Field(
        default=60,
        description="Default recording time limit in seconds"
    )


AUDIO_CONFIG = AudioConfig()

APP_NAME = "whisperkey"
