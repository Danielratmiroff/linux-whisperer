#!/usr/bin/env python3
import pyaudio
import wave
import datetime
import os
import signal
import sys
import psutil
import time
import pyperclip
import notify2
import threading
from pynput import keyboard
from openai import OpenAI
from whisperkey.keyboard_handler import KeyboardHandler
from whisperkey.utils import show_notification


class LinuxWhisperer:
    """A class that handles audio recording and transcription using OpenAI's Whisper API."""

    # Audio configuration
    FORMAT = pyaudio.paInt16
    CHANNELS = 1
    RATE = 44100
    CHUNK = 1024
    RECORD_SECONDS = 60  # Default recording time limit

    def __init__(self):
        """Initialize the WhisperKey application."""
        # Save directory setup
        self.save_dir = os.path.join(
            os.environ['HOME'], 'code/whisperkey/')
        os.makedirs(self.save_dir, exist_ok=True)

        # PID file for single instance management
        self.pid_file = os.path.join(self.save_dir, 'recorder.pid')

        # Recording state
        self.is_recording = False
        self.recording_thread = None
        self.frames = []
        self.audio = None
        self.stream = None
        self.recording_complete = False
        self.current_keys = set()

        # Initialize OpenAI client
        self.client = OpenAI()

        # Initialize notification system
        notify2.init("WhisperKey")

        # Setup signal handlers
        signal.signal(signal.SIGINT, self._signal_handler)  # Ctrl+C
        # Termination signal
        signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, sig, frame):
        """Handle shutdown signals by stopping recording and cleaning up."""
        if self.is_recording:
            self.stop_recording()

        self.recording_complete = True
        self._remove_pid_file()
        sys.exit(0)

    def _create_pid_file(self):
        """Create a PID file with the current process ID."""
        with open(self.pid_file, 'w') as f:
            f.write(str(os.getpid()))

    def _remove_pid_file(self):
        """Remove the PID file when the process exits."""
        if os.path.exists(self.pid_file):
            os.remove(self.pid_file)

    def is_process_running(self, pid):
        """Check if a process with the given PID is running."""
        try:
            process = psutil.Process(pid)
            return process.is_running() and (process.name() == os.path.basename(sys.argv[0])
                                             or 'python' in process.name())
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            return False

    def save_recording(self):
        """Save the recorded frames to a WAV file."""
        if not self.frames:
            print("No audio data to save")
            return None

        # Generate a timestamped filename with full path
        filename = os.path.join(self.save_dir,
                                datetime.datetime.now().strftime("recording_%Y%m%d_%H%M%S.wav"))

        print("Saving to", filename)
        with wave.open(filename, 'wb') as wf:
            wf.setnchannels(self.CHANNELS)
            wf.setsampwidth(self.audio.get_sample_size(self.FORMAT))
            wf.setframerate(self.RATE)
            wf.writeframes(b''.join(self.frames))

        return filename

    def transcribe_audio(self, filename):
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

            # Copy transcription to clipboard
            try:
                pyperclip.copy(transcription)
                print("Transcription copied to clipboard!")

                show_notification(
                    "Recording Completed",
                    "The transcription has been copied to your clipboard",
                    "dialog-information"
                )
            except Exception as e:
                print(f"Failed to copy to clipboard: {e}")
                show_notification(
                    "Error",
                    f"Failed to copy to clipboard: {e}",
                    "dialog-error"
                )

            # TODO: Delete the audio file after transcription

            return transcription

        except Exception as e:
            print(f"Transcription error: {e}")
            show_notification(
                "Transcription Error",
                f"Failed to transcribe audio: {e}",
                "dialog-error"
            )
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
        self.stream = self.audio.open(format=self.FORMAT,
                                      channels=self.CHANNELS,
                                      rate=self.RATE,
                                      input=True,
                                      frames_per_buffer=self.CHUNK)

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
        chunks_to_record = int(self.RATE / self.CHUNK * self.RECORD_SECONDS)

        # Record until stopped or time limit reached
        for _ in range(chunks_to_record):
            if not self.is_recording:
                break

            try:
                data = self.stream.read(self.CHUNK)
                self.frames.append(data)
            except Exception as e:
                print(f"Error recording audio: {e}")
                break

        # If we reach the time limit
        if self.is_recording:
            self.stop_recording()
            show_notification(
                "Recording Stopped",
                f"Time limit of {self.RECORD_SECONDS} seconds reached",
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

        filename = self.save_recording()

        print("Recording stopped. Processing transcription...")

        # Transcribe in a separate thread to keep the UI responsive
        if filename:
            threading.Thread(target=self.transcribe_audio,
                             args=(filename,),
                             daemon=True).start()

    def toggle_recording(self):
        """Toggle recording state."""
        if self.is_recording:
            self.stop_recording()
        else:
            self.start_recording()

    def run(self):
        """Run the WhisperKey application."""
        # Create PID file to indicate this process is running
        self._create_pid_file()

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
            self._remove_pid_file()


def main():
    """Main entry point for the application."""
    whisperer = LinuxWhisperer()
    whisperer.run()


if __name__ == "__main__":
    main()
