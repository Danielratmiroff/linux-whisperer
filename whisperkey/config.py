import pyaudio

# Application name
APP_NAME = "whisperkey"

# Audio configuration dictionary
AUDIO_CONFIG = {
    "FORMAT": pyaudio.paInt16,
    "CHANNELS": 1,
    "RATE": 44100,
    "CHUNK": 1024,
    "RECORD_SECONDS": 60  # Default recording time limit
}
