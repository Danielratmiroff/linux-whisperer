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
client = OpenAI()

# TODO:
# delete the audio file after transcription
# create desktop entry
# auto run on startup

# Audio configuration
FORMAT = pyaudio.paInt16
CHANNELS = 1
RATE = 44100
CHUNK = 1024
RECORD_SECONDS = 60  # Default recording time limit (can be stopped earlier)

# Define the save directory
save_dir = os.path.join(os.environ['HOME'], 'code/linux-whisperer/')

# Ensure the directory exists
os.makedirs(save_dir, exist_ok=True)

# Define a PID file to track if the script is already running
pid_file = os.path.join(save_dir, 'recorder.pid')

# Global state variables
is_recording = False
recording_thread = None
frames = []
audio = None
stream = None
recording_complete = False

# Keyboard shortcut configuration
START_STOP_KEYS = {keyboard.Key.alt_l,
                   keyboard.KeyCode.from_char('g')}  # Alt+G
current_keys = set()


def is_process_running(pid):
    """Check if a process with the given PID is running"""
    try:
        process = psutil.Process(pid)
        return process.is_running() and process.name() == os.path.basename(sys.argv[0]) or 'python' in process.name()
    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
        return False


def create_pid_file():
    """Create a PID file with the current process ID"""
    with open(pid_file, 'w') as f:
        f.write(str(os.getpid()))


def remove_pid_file():
    """Remove the PID file when the process exits"""
    if os.path.exists(pid_file):
        os.remove(pid_file)


def signal_handler(sig, frame):
    """Handle shutdown signals by stopping recording and saving the file"""
    global recording_complete, stream, audio, frames, is_recording

    if is_recording:
        stop_recording()

    recording_complete = True
    remove_pid_file()
    sys.exit(0)


def save_recording(frames):
    """Save the recorded frames to a WAV file"""
    global audio

    if not frames:
        print("No audio data to save")
        return None

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

    return filename


def transcribe_audio(filename):
    """Transcribe the audio file using OpenAI's Whisper API"""
    try:
        audio_file = open(filename, "rb")
        transcription = client.audio.transcriptions.create(
            model="whisper-1",
            file=audio_file,
            response_format="text",
            language="en",
            # Acronyms to help the model understand the context
            # prompt="SLACK, CURSOR"
        )

        print(transcription)

        # Copy transcription to clipboard
        try:
            pyperclip.copy(transcription)
            print("Transcription copied to clipboard!")

            notification = notify2.Notification(
                "Recording Completed",
                "The transcription has been copied to your clipboard",
                "dialog-information"
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

        return transcription
    except Exception as e:
        print(f"Transcription error: {e}")
        notification = notify2.Notification(
            "Transcription Error",
            f"Failed to transcribe audio: {e}",
            "dialog-error"
        )
        notification.show()
        return None


def start_recording():
    """Start recording audio in a separate thread"""
    global is_recording, recording_thread, frames, audio, stream

    if is_recording:
        print("Already recording!")
        return

    # Clear previous recording data
    frames = []

    # Initialize PyAudio
    audio = pyaudio.PyAudio()
    stream = audio.open(format=FORMAT, channels=CHANNELS, rate=RATE,
                        input=True, frames_per_buffer=CHUNK)

    is_recording = True

    # Start recording in a separate thread
    recording_thread = threading.Thread(target=record_audio)
    recording_thread.daemon = True
    recording_thread.start()

    notification = notify2.Notification(
        "Recording Started",
        "Press Alt+G to stop recording",
        "dialog-information"
    )
    notification.show()
    print("Recording started. Press Alt+G to stop.")


def record_audio():
    """Record audio until stopped or time limit reached"""
    global frames, stream, is_recording

    # Calculate how many chunks we need to read for RECORD_SECONDS
    chunks_to_record = int(RATE / CHUNK * RECORD_SECONDS)

    # Record until stopped or time limit reached
    for i in range(chunks_to_record):
        if not is_recording:
            break

        try:
            data = stream.read(CHUNK)
            frames.append(data)
        except Exception as e:
            print(f"Error recording audio: {e}")
            break

    # If we reach the time limit
    if is_recording:
        stop_recording()
        notification = notify2.Notification(
            "Recording Stopped",
            f"Time limit of {RECORD_SECONDS} seconds reached",
            "dialog-information"
        )
        notification.show()


def stop_recording():
    """Stop the current recording, save the file, and transcribe it"""
    global is_recording, stream, audio, frames

    if not is_recording:
        print("Not currently recording!")
        return

    is_recording = False

    # Wait for recording thread to finish
    if recording_thread and recording_thread.is_alive():
        recording_thread.join(timeout=1.0)

    # Stop and close the stream
    if stream:
        stream.stop_stream()
        stream.close()

    # Terminate PyAudio
    if audio:
        audio.terminate()

    # Save the recording
    filename = save_recording(frames)

    print("Recording stopped. Processing transcription...")

    # Transcribe in a separate thread to keep the UI responsive
    if filename:
        threading.Thread(target=transcribe_audio, args=(
            filename,), daemon=True).start()


def on_press(key):
    """Handle key press events"""
    global current_keys

    try:
        current_keys.add(key)
        # Check if our shortcut combination is pressed
        if all(k in current_keys for k in START_STOP_KEYS):
            if is_recording:
                stop_recording()
            else:
                start_recording()
    except Exception as e:
        print(f"Error in key press handler: {e}")


def on_release(key):
    """Handle key release events"""
    global current_keys

    try:
        current_keys.remove(key)
    except (KeyError, Exception) as e:
        # Just ignore if the key wasn't in the set
        pass


def toggle_recording():
    """Toggle recording state"""
    if is_recording:
        stop_recording()
    else:
        start_recording()


def main():
    global recording_complete

    notify2.init("Linux Whisperer")

    # Create PID file to indicate this process is running
    create_pid_file()

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)  # Ctrl+C
    signal.signal(signal.SIGTERM, signal_handler)  # Termination signal

    try:
        listener = keyboard.Listener(
            on_press=on_press, on_release=on_release, suppress=False)
        listener.start()
        keyboard_setup_success = True
        print("Using pynput keyboard listener")
    except Exception as e:
        print(f"Error starting keyboard listener: {e}")
        notification = notify2.Notification(
            "Warning",
            "Keyboard shortcuts may not work. Please check logs.",
            "dialog-warning"
        )
        notification.show()

    # Inform the user about the shortcut
    notification = notify2.Notification(
        "Linux Whisperer Active",
        "Press Alt+G to start/stop recording",
        "dialog-information"
    )
    notification.show()

    print("Linux Whisperer is running in the background.")
    print("Press Alt+G to start/stop recording.")

    # Keep the main thread alive
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        signal_handler(signal.SIGINT, None)
    finally:
        if is_recording:
            stop_recording()
        remove_pid_file()


if __name__ == "__main__":
    main()
