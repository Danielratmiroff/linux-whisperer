#!/usr/bin/env python3
import datetime
import pyaudio
import wave
import os
import signal
import sys
import time
import pyperclip
import notify2
import threading
from pynput import keyboard
from openai import OpenAI
from whisperkey.keyboard_handler import KeyboardHandler
from whisperkey.utils import show_notification
from whisperkey.file_handler import FileHandler
from whisperkey.config import AUDIO_CONFIG


class WhisperKey:
    """A class that handles audio recording and transcription using OpenAI's Whisper API."""

    def __init__(self):
        """Initialize the WhisperKey application."""
        self.file_handler = FileHandler()
        self.audio_config = AUDIO_CONFIG

        # Recording state
        self.is_recording = False
        self.recording_thread = None
        self.frames = []
        self.audio = None
        self.stream = None
        self.recording_complete = False

        # Initialize OpenAI client
        self.client = OpenAI()

        # Initialize notification system
        notify2.init("WhisperKey")

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)  # Ctrl+C
        # Termination signal
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, signum, frame):
        """Handle shutdown signals by stopping recording and cleaning up."""
        if self.is_recording:
            self.stop_recording()

        self.recording_complete = True
        self.file_handler.remove_pid_file()
        sys.exit(0)

    def transcribe_audio(self, filename) -> str | None:
        """Transcribe the audio file using OpenAI's Whisper API."""
        try:
            with open(filename, "rb") as audio_file:
                transcription = self.client.audio.transcriptions.create(
                    model="whisper-1",
                    file=audio_file,
                    response_format="text",
                    language="en",
                )

            print(transcription)
            return transcription

        except Exception as e:
            print(f"Transcription error: {e}")
            return None

    def start_recording(self):
        """Start recording audio in a separate thread."""
        if self.is_recording:
            print("Already recording!")
            return

        # Clear previous recording data
        self.frames = []

        # Initialize PyAudio
        self.audio = pyaudio.PyAudio()
        self.stream = self.audio.open(format=self.audio_config.FORMAT,
                                      channels=self.audio_config.CHANNELS,
                                      rate=self.audio_config.RATE,
                                      input=True,
                                      frames_per_buffer=self.audio_config.CHUNK)

        self.is_recording = True

        # Start recording in a separate thread
        self.recording_thread = threading.Thread(target=self._record_audio)
        self.recording_thread.daemon = True
        self.recording_thread.start()

        show_notification(
            "Recording Started",
            "Press Alt+G to stop recording",
            "dialog-information"
        )
        print("Recording started. Press Alt+G to stop.")

    def _record_audio(self):
        """Record audio until stopped or time limit reached."""
        # Calculate how many chunks we need to read for RECORD_SECONDS
        chunks_to_record = int(
            self.audio_config.RATE / self.audio_config.CHUNK * self.audio_config.RECORD_SECONDS)

        # Record until stopped or time limit reached
        for _ in range(chunks_to_record):
            if not self.is_recording:
                break

            try:
                data = self.stream.read(self.audio_config.CHUNK)
                self.frames.append(data)
            except Exception as e:
                print(f"Error recording audio: {e}")
                break

        # If we reach the time limit
        if self.is_recording:
            self.stop_recording()
            show_notification(
                "Recording Stopped",
                f"Time limit of {self.audio_config.RECORD_SECONDS} seconds reached",
                "dialog-information"
            )

    def stop_recording(self):
        """Stop the current recording, save the file, and transcribe it."""
        if not self.is_recording:
            print("Not currently recording!")
            return

        self.is_recording = False

        # Wait for recording thread to finish
        if self.recording_thread and self.recording_thread.is_alive():
            self.recording_thread.join(timeout=1.0)

        if self.stream:
            self.stream.stop_stream()
            self.stream.close()

        if self.audio:
            self.audio.terminate()

        # Save the recording
        filename = self.file_handler.save_recording(
            self.frames, self.audio, self.audio_config)
        if not filename:
            show_notification(
                "Error",
                "Failed to save recording",
                "dialog-error"
            )
            return

        print("Recording stopped. Processing transcription...")

        # Transcribe the recording
        transcription = self.transcribe_audio(filename)
        if not transcription:
            show_notification(
                "Error",
                "Failed to transcribe recording",
                "dialog-error"
            )
            return

        pyperclip.copy(transcription)
        print("Transcription copied to clipboard!")

        show_notification(
            "Recording Completed",
            "The transcription has been copied to your clipboard",
            "dialog-information"
        )

    def toggle_recording(self):
        """Toggle recording state."""
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def run(self):
        """Run the WhisperKey application."""

        # Create PID file to indicate this process is running
        self.file_handler.create_pid_file()

        # Set up keyboard listener
        self.keyboard_handler = KeyboardHandler(self.toggle_recording)
        keyboard_setup_success = self.keyboard_handler.setup_keyboard_listener()

        if not keyboard_setup_success:
            show_notification(
                "Error",
                "Failed to set up keyboard listener",
                "dialog-error"
            )
            return

        # Inform the user about the shortcut
        show_notification(
            "WhisperKey Active",
            "Press Alt+G to start/stop recording",
            "dialog-information"
        )

        print("WhisperKey is running in the background.")
        print("Press Alt+G to start/stop recording.")

        # Keep the main thread alive
        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self._signal_handler(signal.SIGINT, None)
        finally:
            if self.is_recording:
                self.stop_recording()
            self.file_handler.remove_pid_file()


def main():
    """Main entry point for the application."""
    whisperkey = WhisperKey()
    whisperkey.run()


if __name__ == "__main__":
    main()
