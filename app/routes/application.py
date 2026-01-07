# application.py

import sys
from pathlib import Path
import os
import mimetypes
from flask import abort


# --------------------------------------------------
# Ensure project root is on PYTHONPATH
# --------------------------------------------------
PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

import time
from flask import Blueprint, request, jsonify, Response
from flask_cors import CORS
#from flasgger import Swagger
import cv2

import scripts.monitoring as monitoring
from celery import Celery

# --------------------------------------------------
# Blueprint Setup
# --------------------------------------------------
application_bp = Blueprint(
    "application",
    __name__,
    url_prefix="/api"
)

CORS(application_bp)
#swagger = Swagger(application_bp)

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
@application_bp.route("/cameras", methods=["GET"])
def list_cameras():
    """
    List all cameras
    ---
    tags:
      - Detection
    responses:
      200:
        description: List of camera IDs
    """
    return jsonify({"cameras": monitoring.list_cameras()})


@application_bp.route("/cameras", methods=["POST"])
def add_camera():
    """
    Add a new camera
    ---
    tags:
      - Detection
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


@application_bp.route("/cameras/<camera_id>/start", methods=["POST"])
def start_camera(camera_id):
    """
    Start camera processing
    ---
    tags:
      - Detection
    parameters:
      - name: camera_id
        in: path
        required: true
    """
    monitoring.start_camera(camera_id)
    return jsonify({"status": "started", "camera_id": camera_id})


@application_bp.route("/cameras/<camera_id>/stop", methods=["POST"])
def stop_camera(camera_id):
    """
    Stop camera processing
    ---
    tags:
      - Detection
    parameters:
      - name: camera_id
        in: path
        required: true
    """
    monitoring.stop_camera(camera_id)
    return jsonify({"status": "stopped", "camera_id": camera_id})


@application_bp.route("/cameras/<camera_id>", methods=["DELETE"])
def delete_camera(camera_id):
    """
    Remove camera
    ---
    tags:
      - Detection
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
@application_bp.route("/cameras/test-connection", methods=["POST"])
def test_camera_connection():
    """
    Test RTSP / video source connectivity
    ---
    tags:
      - Detection
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
            # Instead of just continuing, send a "Loading" or "Black" frame
            # to keep the HTTP connection alive
            time.sleep(0.2)
            continue

        ok, jpg = cv2.imencode(".jpg", frame)
        if not ok: continue

        yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpg.tobytes() + b"\r\n")
        time.sleep(interval)


@application_bp.route("/cameras/<camera_id>/stream")
def stream_camera(camera_id):
    """
    Live MJPEG stream
    ---
    tags:
      - Detection
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
# Health Check (Blueprint level)
# --------------------------------------------------
@application_bp.route("/health")
def health():
    """
    Health check
    ---
    tags:
      - Detection
    responses:
      200:
        description: Service is running
    """
    return jsonify({
        "status": "ok",
        "service": "Flask Monitoring API"
    })
