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

from openai import OpenAI
client = OpenAI()

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 10

# Define the save directory
save_dir = os.path.join(os.environ['HOME'], 'code/linux-whisperer/')

# Ensure the directory exists
os.makedirs(save_dir, exist_ok=True)

# Define a PID file to track if the script is already running
pid_file = os.path.join(save_dir, 'recorder.pid')


def is_process_running(pid):
    """Check if a process with the given PID is running"""
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.name() == os.path.basename(sys.argv[0]) or 'python' in process.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def stop_existing_process():
    """Stop an existing instance of this script if it's running"""
    if os.path.exists(pid_file):
        with open(pid_file, 'r') as f:
            try:
                pid = int(f.read().strip())
                if is_process_running(pid):
                    print(
                        f"Stopping existing recording process (PID: {pid})...")
                    os.kill(pid, signal.SIGTERM)
                    # Wait a moment to ensure the process has time to clean up
                    time.sleep(1)
                    return True
                else:
                    # PID file exists but process is not running
                    os.remove(pid_file)
            except (ValueError, ProcessLookupError):
                # Invalid PID or process doesn't exist
                os.remove(pid_file)
    return False


def create_pid_file():
    """Create a PID file with the current process ID"""
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    """Remove the PID file when the process exits"""
    if os.path.exists(pid_file):
        os.remove(pid_file)


# Global variables to access in signal handler
frames = []
audio = None
stream = None
recording_complete = False


def signal_handler(sig, frame):
    """Handle shutdown signals by stopping recording and saving the file"""
    global recording_complete, stream, audio, frames

    if not recording_complete:
        print("\nReceived shutdown signal. Stopping recording and saving file...")

        # Stop and close the stream if it's active
        if stream and stream.is_active():
            stream.stop_stream()
            stream.close()

        # Terminate PyAudio if initialized
        if audio:
            audio.terminate()

        # Save the recording if we have frames
        if frames:
            save_recording(frames)

        recording_complete = True
        remove_pid_file()

        notification = notify2.Notification(
            "Recording Stopped",
            "The recording has stopped",
            "dialog-information"  # This is a standard icon name
        )
        notification.show()

    sys.exit(0)


def save_recording(frames):
    """Save the recorded frames to a WAV file"""
    global audio, filename

    # Generate a timestamped filename with full path
    filename = os.path.join(save_dir, datetime.datetime.now().strftime(
        "recording_%Y%m%d_%H%M%S.wav"))

    print("Saving to", filename)
    wf = wave.open(filename, 'wb')
    wf.setnchannels(CHANNELS)
    wf.setsampwidth(audio.get_sample_size(FORMAT))
    wf.setframerate(RATE)
    wf.writeframes(b''.join(frames))
    wf.close()


def main():
    global audio, stream, frames, recording_complete

    notify2.init("Linux Whisperer")

    # Check if the script is already running
    if stop_existing_process():
        print("Existing recording process stopped.")
        return

    # Create PID file to indicate this process is running
    create_pid_file()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

    try:
        # Initialize PyAudio
        audio = pyaudio.PyAudio()
        stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                            input=True, frames_per_buffer=CHUNK)

        # Record for RECORD_SECONDS or until interrupted
        print(
            f"Recording for {RECORD_SECONDS} seconds... (Press Ctrl+C or send SIGTERM to stop)")

        notification = notify2.Notification(
            "Recording Started",
            "The recording has started",
            "dialog-information"  # This is a standard icon name
        )
        notification.show()

        # Calculate how many chunks we need to read for RECORD_SECONDS
        chunks_to_record = int(RATE / CHUNK * RECORD_SECONDS)

        # Record for the specified duration
        for i in range(chunks_to_record):
            data = stream.read(CHUNK)
            frames.append(data)

        # If we reach here, recording completed normally
        print("\nRecording finished (time limit reached).")
    except KeyboardInterrupt:
        # This is a fallback in case the signal handler doesn't catch it
        pass
    finally:
        # Clean up if we exit the loop normally
        if not recording_complete:
            print("\nRecording finished.")
            stream.stop_stream()
            stream.close()
            audio.terminate()
            save_recording(frames)
            remove_pid_file()

            audio_file = open(filename, "rb")
            transcription = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file
            )

            print(transcription.text)

            # Copy transcription to clipboard
            try:
                pyperclip.copy(transcription.text)
                print("Transcription copied to clipboard!")

                notification = notify2.Notification(
                    "Recording Transcribed",
                    "The transcription has been copied to your clipboard",
                    "dialog-information"  # This is a standard icon name
                )
                notification.show()
            except Exception as e:
                print(f"Failed to copy to clipboard: {e}")

                notification = notify2.Notification(
                    "Error",
                    f"Failed to copy to clipboard: {e}",
                    "dialog-error"
                )
                notification.show()


if __name__ == "__main__":
    main()
