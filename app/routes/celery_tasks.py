# celery_tasks.py
import json
import datetime
import mysql.connector
from celery import Celery
#from pathlib import Path

# -----------------------------------------------------------
# Celery configuration
# -----------------------------------------------------------
celery_app = Celery(
    "monitoring_tasks",
    broker="redis://127.0.0.1:6379/0",
    backend="redis://127.0.0.1:6379/1"
)

# MySQL connection settings (same as monitoring.py)
DB_CONFIG = {
    "host": "localhost",   # IMPORTANT: avoid localhost socket issues
    "user": "admin123",
    "password": "Petro@123",
    "database": "RestrictedAreaDB",
    #"port": 3306
}


def get_db():
    return mysql.connector.connect(**DB_CONFIG)

def ensure_tables():
    conn = get_db()
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE IF NOT EXISTS FaceEvents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            camera_id VARCHAR(255),
            person_name VARCHAR(255),
            auth BOOLEAN,
            similarity FLOAT,
            timestamp DATETIME,
            raw_event JSON
        );
    """)
    cur.execute("""
        CREATE TABLE IF NOT EXISTS AnomalyEvents (
            id INT AUTO_INCREMENT PRIMARY KEY,
            camera_id VARCHAR(255),
            anomaly_type VARCHAR(255),
            confidence FLOAT,
            timestamp DATETIME,
            video_path VARCHAR(500),
            json_path VARCHAR(500),
            raw_event JSON
        );
    """)
    conn.commit()
    conn.close()

ensure_tables()

@celery_app.task(name="celery_tasks.process_face_event")
def process_face_event(event):
    try:
        cam = event.get("camera_id")
        data = event.get("data", {})
        name = data.get("name")
        auth = bool(data.get("auth"))
        sim = float(data.get("similarity", 0.0))
        ts = event.get("ts") or data.get("timestamp") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO FaceEvents (camera_id, person_name, auth, similarity, timestamp, raw_event)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (
            cam,
            name,
            auth,
            sim,
            ts,
            json.dumps(event)
        ))
        conn.commit()
        conn.close()
        return {"status": "ok", "saved": True}
    except Exception as e:
        return {"status": "error", "error": str(e)}

@celery_app.task(name="celery_tasks.process_anomaly_event")
def process_anomaly_event(event):
    print("Celery task called with event:", event)
    """
    Safely insert an anomaly event into MySQL.
    Handles multiple payload shapes and ensures type safety.
    """
    try:
        # Camera ID
        cam = event.get("camera_id") or event.get("camera") or "unknown_camera"

        # Data extraction
        data = event.get("data", {}) if isinstance(event, dict) else {}
        if not data and isinstance(event, dict) and ("video_path" in event or "json_path" in event):
            data = event

        # Anomaly type and confidence
        anomaly_type = None
        confidence = 0.0
        objects = data.get("objects", [])
        if isinstance(objects, list) and len(objects) > 0:
            anomaly_type = str(objects[0].get("label", "unknown"))
            confidence = float(objects[0].get("conf", 0.0))
        else:
            anomaly_type = str(data.get("type", "unknown"))
            try:
                confidence = float(data.get("confidence", 0.0))
            except (TypeError, ValueError):
                confidence = 0.0

        # Video and JSON paths
        video_path = str(data.get("video_path") or data.get("video") or "")
        json_path = str(data.get("json_path") or data.get("json") or "")

        # Timestamp
        ts = event.get("ts") or data.get("timestamp") or datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        if isinstance(ts, str):
            try:
                ts = datetime.datetime.strptime(ts[:19], "%Y-%m-%d %H:%M:%S")
            except:
                ts = datetime.datetime.now()
        elif not isinstance(ts, datetime.datetime):
            ts = datetime.datetime.now()

        # Debug log
        print("Inserting anomaly event:", cam, anomaly_type, confidence, video_path, json_path, ts)

        # Insert into MySQL
        conn = get_db()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO AnomalyEvents (camera_id, anomaly_type, confidence, timestamp, video_path, json_path, raw_event)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (
            cam,
            anomaly_type,
            confidence,
            ts,
            video_path,
            json_path,
            json.dumps(event)
        ))
        conn.commit()
        conn.close()
        return {"status": "ok", "saved": True}

    except Exception as e:
        print("Error inserting anomaly event:", e)
        return {"status": "error", "error": str(e)}

