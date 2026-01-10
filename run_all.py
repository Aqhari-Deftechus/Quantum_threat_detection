#run_all.py

import subprocess
import sys
import time
import os
import socket




BASE_DIR = r'C:\Users\dus_m\OneDrive\Desktop\Quantum_threat_detection'
VENV_PYTHON = r"C:\Users\dus_m\myenv\Scripts\python.exe"
REDIS_EXE = r"C:\Program Files\Redis\redis-server.exe"

def start_process(cmd, cwd=None):
    return subprocess.Popen(
        cmd,
        cwd=cwd,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )


def redis_running():
    s = socket.socket()
    try:
        s.connect(("localhost", 6379))
        return True
    except:
        return False

if __name__ == "__main__":

    print("Starting Redis...")
    start_process([REDIS_EXE])

    time.sleep(2)  # allow Redis to start

    print("Starting Celery worker...")
    start_process([
        VENV_PYTHON, "-m", "celery",
        "-A", "celery_worker.celery_app",
        "worker",
        "-P", "eventlet",
        "--loglevel=info"
    ], cwd=os.path.join(BASE_DIR, "app", "routes"))

    time.sleep(2)

    print("Starting Flask API...")
    start_process([VENV_PYTHON, "run.py"], cwd=BASE_DIR)

    print("All services started.")
