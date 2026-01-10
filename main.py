#main.py

import subprocess
import sys
import threading

def run_script(script):
    subprocess.run([sys.executable, script], check=True)

if __name__ == "__main__":
    print("Starting auto training (watcher)...")

    watcher_thread = threading.Thread(
        target=run_script,
        args=("scripts/auto_trainer.py",),
        daemon=True
    )
    watcher_thread.start()

    print("Running main pipeline...")
    run_script("run_all.py")

    print("Main pipeline finished. Watcher still running.")
