#!/usr/bin/env python3
import pyaudio
import wave
import datetime
import os

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 5

# Define the save directory
save_dir = os.path.join(os.environ['HOME'], 'code/linux-whisperer/')

# Ensure the directory exists
os.makedirs(save_dir, exist_ok=True)

# Generate a timestamped filename with full path
filename = os.path.join(save_dir, datetime.datetime.now().strftime(
    "recording_%Y%m%d_%H%M%S.wav"))

audio = pyaudio.PyAudio()
stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                    input=True, frames_per_buffer=CHUNK)

print("Recording...")

frames = []
for _ in range(0, int(RATE / CHUNK * RECORD_SECONDS)):
    data = stream.read(CHUNK)
    frames.append(data)

print("Recording finished. Saving to", filename)

stream.stop_stream()
stream.close()
audio.terminate()

wf = wave.open(filename, 'wb')
wf.setnchannels(CHANNELS)
wf.setsampwidth(audio.get_sample_size(FORMAT))
wf.setframerate(RATE)
wf.writeframes(b''.join(frames))
wf.close()
