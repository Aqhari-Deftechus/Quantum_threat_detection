import json
import mimetypes
import subprocess
from pathlib import Path
from datetime import datetime
from flask import Blueprint, jsonify, request, abort, Response
import cv2

# =========================================================
# CONFIGURATION
# =========================================================

ANOMALY_BASE_DIR = Path(
    r"C:\Users\dusai\Desktop\Quantum_Threat_Detection\Anomalies_video"
)

FFMPEG_PATH = r"C:\Users\dusai\Desktop\Quantum_Threat_Detection\ffmpeg-8.0.1-essentials_build\bin\ffmpeg.exe"  # <-- CHANGE IF NEEDED
MAX_LIST_LIMIT = 1000
THUMBNAIL_SIZE = (160, 120)

bp = Blueprint("anomalies", __name__, url_prefix="/api/anomalies")

# =========================================================
# HELPERS
# =========================================================

def get_web_playable_path(input_mp4: Path) -> Path:
    """
    Ensure browser-compatible MP4 exists (H.264 + AAC).
    Converts once, then reuses.
    """
    web_mp4 = input_mp4.with_name(input_mp4.stem + "_web.mp4")

    if web_mp4.exists():
        return web_mp4

    subprocess.run(
        [
            FFMPEG_PATH,
            "-y",
            "-i", str(input_mp4),
            "-c:v", "libx264",
            "-pix_fmt", "yuv420p",
            "-movflags", "+faststart",
            "-c:a", "aac",
            str(web_mp4)
        ],
        check=True
    )

    return web_mp4


def create_thumbnail(video_path: Path):
    try:
        cap = cv2.VideoCapture(str(video_path))
        ret, frame = cap.read()
        cap.release()
        if not ret:
            return None
        frame = cv2.resize(frame, THUMBNAIL_SIZE)
        _, buffer = cv2.imencode(".jpg", frame)
        return buffer.tobytes()
    except Exception:
        return None


def load_json(file_path: Path):
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return None


def list_anomaly_files():
    anomalies = []

    for date_dir in ANOMALY_BASE_DIR.iterdir():
        if not date_dir.is_dir():
            continue

        for json_file in date_dir.glob("*.json"):
            anomaly_id = json_file.stem
            video_path = json_file.with_suffix(".mp4")

            anomalies.append({
                "anomaly_id": anomaly_id,
                "date": date_dir.name,
                "video_exists": video_path.exists()
            })

    anomalies.sort(key=lambda x: x["anomaly_id"], reverse=True)
    return anomalies[:MAX_LIST_LIMIT]

# =========================================================
# ROUTES
# =========================================================


@bp.route("", methods=["GET"])
def get_anomalies():
    """
    Get paginated list of anomaly records
    ---
    tags:
      - Anomalies
    parameters:
      - name: date_from
        in: query
        type: string
        format: date
        required: false
        description: Start date filter (YYYY-MM-DD)
      - name: date_to
        in: query
        type: string
        format: date
        required: false
        description: End date filter (YYYY-MM-DD)
      - name: camera_id
        in: query
        type: string
        required: false
        description: Filter anomalies by camera ID
      - name: page
        in: query
        type: integer
        required: false
        default: 1
        description: Page number
      - name: per_page
        in: query
        type: integer
        required: false
        default: 20
        description: Number of records per page
    responses:
      200:
        description: Paginated list of anomalies with direct video preview URLs
        schema:
          type: array
          items:
            type: object
            properties:
              anomaly_id:
                type: string
                example: CAM01_20251224_101533
              date:
                type: string
                example: 2025-12-24
              video_url:
                type: string
                example: /api/anomalies/CAM01_20251224_101533/video
    """
    ...

    result = []

    for a in list_anomaly_files():
        result.append({
            "anomaly_id": a["anomaly_id"],
            "date": a["date"],
            "video_url": f"/api/anomalies/{a['anomaly_id']}/video"
            if a["video_exists"] else None
        })

    return jsonify(result)


@bp.route("/<anomaly_id>", methods=["GET"])
def get_anomaly_details(anomaly_id):
    """
    Get anomaly metadata by anomaly ID
    ---
    tags:
      - Anomalies
    parameters:
      - name: anomaly_id
        in: path
        type: string
        required: true
        description: Unique anomaly identifier
        example: CAM01_20251224_101533
    responses:
      200:
        description: Anomaly JSON metadata
      404:
        description: Anomaly not found
    """
    ...

    for date_dir in ANOMALY_BASE_DIR.iterdir():
        if not date_dir.is_dir():
            continue

        json_path = date_dir / f"{anomaly_id}.json"
        if json_path.exists():
            data = load_json(json_path)
            if data is None:
                abort(500)
            return jsonify(data)

    abort(404)


@bp.route("/<anomaly_id>/video", methods=["GET"])
def get_anomaly_video(anomaly_id):
    """
    Stream anomaly video footage (browser playable)
    ---
    tags:
      - Anomalies
    parameters:
      - name: anomaly_id
        in: path
        type: string
        required: true
        description: Unique anomaly identifier
        example: CAM01_20251224_101533
      - name: Range
        in: header
        type: string
        required: false
        description: HTTP byte range for video streaming (handled automatically by browser)
        example: bytes=0-
    responses:
      200:
        description: Full video stream (no Range header)
        headers:
          Content-Type:
            type: string
            example: video/mp4
      206:
        description: Partial content response for video streaming
        headers:
          Content-Range:
            type: string
            example: bytes 0-102399/2048000
          Accept-Ranges:
            type: string
            example: bytes
      404:
        description: Video not found
      500:
        description: Video conversion or streaming error
    produces:
      - video/mp4
    """
    ...


    original_video = None

    for date_dir in ANOMALY_BASE_DIR.iterdir():
        if not date_dir.is_dir():
            continue

        candidate = date_dir / f"{anomaly_id}.mp4"
        if candidate.exists():
            original_video = candidate
            break

    if not original_video:
        abort(404, "Video not found")

    try:
        video_path = get_web_playable_path(original_video)
    except Exception as e:
        abort(500, f"FFmpeg error: {e}")

    file_size = video_path.stat().st_size
    range_header = request.headers.get("Range")

    # ---- No Range (initial request) ----
    if not range_header:
        def generate():
            with open(video_path, "rb") as f:
                while True:
                    chunk = f.read(8192)
                    if not chunk:
                        break
                    yield chunk

        return Response(
            generate(),
            mimetype="video/mp4",
            headers={
                "Content-Length": str(file_size),
                "Accept-Ranges": "bytes",
                "Content-Disposition": "inline"
            }
        )

    # ---- Range request ----
    try:
        _, ranges = range_header.split("=")
        start_str, end_str = ranges.split("-")
        start = int(start_str) if start_str else 0
        end = int(end_str) if end_str else file_size - 1
    except Exception:
        abort(416)

    end = min(end, file_size - 1)
    length = end - start + 1

    def generate():
        with open(video_path, "rb") as f:
            f.seek(start)
            remaining = length
            while remaining > 0:
                chunk = f.read(min(8192, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return Response(
        generate(),
        status=206,
        mimetype="video/mp4",
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Disposition": "inline"
        }
    )
