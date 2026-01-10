#scripts/auto_trainer.py

import time
import threading
import argparse
import subprocess
import sys
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileSystemEvent
from pathlib import Path

# Debounce settings
debounce_interval = 2.0  # seconds to wait after last event

class DebouncedHandler(FileSystemEventHandler):
    def __init__(self, face_data_dir, train_command):
        self.face_data_dir = face_data_dir
        self.train_command = train_command
        self._timer = None
        self._lock = threading.Lock()

    def _on_debounce(self):
        # Called after no new events for debounce_interval
        print("[Watcher] Changes settled, launching training...")
        # Call the training script with the same Python interpreter
        try:
            subprocess.run(self.train_command, check=True)
            print("[Watcher] Training completed successfully.")
        except subprocess.CalledProcessError as e:
            print(f"[Watcher] Training failed: {e}")

    def _schedule(self):
        with self._lock:
            if self._timer:
                self._timer.cancel()
            self._timer = threading.Timer(debounce_interval, self._on_debounce)
            self._timer.daemon = True
            self._timer.start()

    def on_any_event(self, event: FileSystemEvent):
        # Only react to changes in face_data directory
        if event.src_path.startswith(self.face_data_dir):
            print(f"[Watcher] Detected file system event: {event.event_type} -> {event.src_path}")
            self._schedule()


def main(face_data_dir, train_script_path):
    # Use the same Python interpreter that's running this script
    python_executable = sys.executable
    train_command = [python_executable, train_script_path]
    event_handler = DebouncedHandler(face_data_dir, train_command)

    observer = Observer()
    observer.schedule(event_handler, face_data_dir, recursive=True)
    observer.start()
    print(f"[Watcher] Monitoring '{face_data_dir}' for changes. Debounce interval: {debounce_interval}s")

    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        observer.stop()
    observer.join()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Watch a face_data folder and retrain embeddings on changes.")
    parser.add_argument("--face_data", help="Path to the face_data directory to monitor")
    parser.add_argument("--train_script", help="Path to train_face2.py script")
    args = parser.parse_args()

   
    BASE_DIR = Path(__file__).resolve().parent      
    DEFAULT_FACE_DATA = BASE_DIR.parent / "face_data"
    DEFAULT_TRAIN_SCRIPT = BASE_DIR / "train_face2.py"

    face_data = args.face_data or str(DEFAULT_FACE_DATA)
    train_script = args.train_script or str(DEFAULT_TRAIN_SCRIPT)

    main(face_data, train_script)
