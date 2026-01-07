# application.py

import sys
from pathlib import Path

# --------------------------------------------------
# Ensure project root is on PYTHONPATH
# --------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import time
from flask import Flask, request, jsonify, Response
from flask_cors import CORS
from flasgger import Swagger
import cv2

import scripts.monitoring as monitoring

from celery import Celery

# --------------------------------------------------
# Flask App Setup
# --------------------------------------------------
app = Flask(__name__)
CORS(app)
swagger = Swagger(app)

# --------------------------------------------------
# Celery Client (NO TASK DEFINITIONS HERE)
# --------------------------------------------------
celery_app = Celery(
    "monitoring_tasks",
    broker="redis://127.0.0.1:6379/0",
    backend="redis://127.0.0.1:6379/1"
)

# --------------------------------------------------
# Camera CRUD APIs
# --------------------------------------------------
@app.route("/api/cameras", methods=["GET"])
def list_cameras():
    """
    List all cameras
    ---
    responses:
      200:
        description: List of camera IDs
    """
    return jsonify({"cameras": monitoring.list_cameras()})


@app.route("/api/cameras", methods=["POST"])
def add_camera():
    """
    Add a new camera
    ---
    parameters:
      - name: body
        in: body
        required: true
        schema:
          type: object
          required:
            - camera_id
            - source
          properties:
            camera_id:
              type: string
            source:
              type: string
    """
    data = request.json or {}
    camera_id = data.get("camera_id")
    source = data.get("source")

    if not camera_id or not source:
        return jsonify({"error": "camera_id and source are required"}), 400

    monitoring.add_camera(camera_id, source)
    return jsonify({"status": "ok", "camera_id": camera_id})


@app.route("/api/cameras/<camera_id>/start", methods=["POST"])
def start_camera(camera_id):
    """
    Start camera processing
    ---
    parameters:
      - name: camera_id
        in: path
        required: true
    """
    monitoring.start_camera(camera_id)
    return jsonify({"status": "started", "camera_id": camera_id})


@app.route("/api/cameras/<camera_id>/stop", methods=["POST"])
def stop_camera(camera_id):
    """
    Stop camera processing
    ---
    parameters:
      - name: camera_id
        in: path
        required: true
    """
    monitoring.stop_camera(camera_id)
    return jsonify({"status": "stopped", "camera_id": camera_id})


@app.route("/api/cameras/<camera_id>", methods=["DELETE"])
def delete_camera(camera_id):
    """
    Remove camera
    ---
    parameters:
      - name: camera_id
        in: path
        required: true
    """
    monitoring.remove_camera(camera_id)
    return jsonify({"status": "deleted", "camera_id": camera_id})

# --------------------------------------------------
# Camera Connection Test
# --------------------------------------------------
@app.route("/api/cameras/test-connection", methods=["POST"])
def test_camera_connection():
    """
    Test RTSP / video source connectivity
    ---
    parameters:
      - name: source
        in: body
        required: true
        schema:
          type: object
          properties:
            source:
              type: string
    """
    data = request.json or {}
    source = data.get("source")

    if not source:
        return jsonify({"error": "source required"}), 400

    cap = cv2.VideoCapture(source)
    ok, _ = cap.read()
    cap.release()

    if not ok:
        return jsonify({"status": "failed"}), 400

    return jsonify({"status": "success"})

# --------------------------------------------------
# MJPEG Streaming
# --------------------------------------------------
def mjpeg_generator(camera_id, fps=5):
    interval = 1.0 / max(1, fps)

    while True:
        frame = monitoring.get_latest_frame(camera_id)

        if frame is None:
            time.sleep(0.1)
            continue

        ok, jpg = cv2.imencode(".jpg", frame)
        if not ok:
            continue

        yield (
            b"--frame\r\n"
            b"Content-Type: image/jpeg\r\n\r\n" +
            jpg.tobytes() +
            b"\r\n"
        )
        time.sleep(interval)


@app.route("/api/cameras/<camera_id>/stream")
def stream_camera(camera_id):
    """
    Live MJPEG stream
    ---
    parameters:
      - name: fps
        in: query
        type: number
        default: 5
    """
    fps = float(request.args.get("fps", 5))
    return Response(
        mjpeg_generator(camera_id, fps),
        mimetype="multipart/x-mixed-replace; boundary=frame"
    )

# --------------------------------------------------
# Health Check
# --------------------------------------------------
@app.route("/")
def health():
    """
    Health check
    ---
    responses:
      200:
        description: Service is running
    """
    return jsonify({
        "status": "ok",
        "service": "Flask Monitoring API"
    })

# --------------------------------------------------
# Main
# --------------------------------------------------
if __name__ == "__main__":
    print("Starting Flask Monitoring API...")
    app.run(host="0.0.0.0", port=8000, debug=True)
