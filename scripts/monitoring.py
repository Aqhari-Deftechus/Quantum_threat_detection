# monitoring.py
import cv2
import numpy as np
import pickle
import logging
import threading
import queue
import time
import datetime
import csv
import argparse
import warnings
import os
from pathlib import Path
import torch
import torchvision.ops as tv_ops
from scipy.spatial.distance import cdist
import collections
import json
import uuid

import mediapipe as mp
from mediapipe.tasks import python
from mediapipe.tasks.python import vision
from mediapipe.tasks.python.core import base_options
from ultralytics import YOLO
from keras_facenet import FaceNet
from deep_sort_realtime.deepsort_tracker import DeepSort
import mysql.connector

def init_face_model():
    import mediapipe as mp
    #return mp.solutions.face_mesh
    return mp.tasks.face_mesh


# ----------------- Patch: Force torchvision.ops.nms to run on CPU (keeps compatibility) -----------------
_orig_nms = tv_ops.nms

def nms_cpu_fallback(boxes, scores, iou_threshold):
    return _orig_nms(boxes.cpu(), scores.cpu(), iou_threshold)

tv_ops.nms = nms_cpu_fallback

# ----------------- Configuration -----------------
FRAME_DOWNSCALE = 1
INPUT_SIZE = (160, 160)
SIMILARITY_THRESHOLD = 0.55
FALLBACK_VERIFY = True
FALLBACK_MARGIN = 0.02

AUTH_CACHE_TTL = 10
TRACK_MEMORY_TTL = 10
IDENTITY_PERSISTENCE_TTL = 5
TARGET_FPS = 10
FRAME_INTERVAL = 1 / TARGET_FPS

# --- Event video settings ---
PRE_EVENT_SECONDS  = 3
POST_EVENT_SECONDS = 3
EVENT_CLIP_SECONDS = PRE_EVENT_SECONDS + POST_EVENT_SECONDS

ANOMALY_BUFFER_SIZE = int(TARGET_FPS * EVENT_CLIP_SECONDS)

# --- Cooldown settings ---
ANOMALY_COOLDOWN_SECONDS = 10      # per camera
UNAUTHORIZED_COOLDOWN_SECONDS = 10 # per camera


DB_CONFIG = {
    "host": "localhost",   # IMPORTANT: avoid localhost socket issues
    "user": "admin123",
    "password": "Degftech@012026",
    "database": "RestrictedAreaDB",
    #"port": 3306
}


# Directory to save anomaly clips & JSON (user-specified)
ANOMALY_BASE_DIR = Path(r"C:\Users\dusai\Desktop\Quantum_Threat_Detection\Anomalies_video")



#PROJECT_ROOT = Path(__file__).resolve().parent.parent  
#ANOMALY_BASE_DIR = PROJECT_ROOT.parent / "Anomalies_video"



# --- Base paths relative to this script ---
BASE_DIR = Path(__file__).resolve().parent
ROOT_DIR = BASE_DIR.parent

MODEL_DIR = ROOT_DIR / "model"
ICON_DIR = ROOT_DIR / "icon"
SCRIPT_DIR = ROOT_DIR / "scripts"

YOLO_FACE_PATH     = str(MODEL_DIR / "yolov11n-face.pt")
YOLO_PERSON_PATH   = str(MODEL_DIR / "yolo11n.pt")
YOLO_OBJECT_PATH   = str(MODEL_DIR / "inappropriate_behaviour.pt")
ICON_VERIFIED_PATH   = str(ICON_DIR / "verified2.png")
ICON_UNVERIFIED_PATH = str(ICON_DIR / "Unverified.png")
EMBEDDINGS_FILE    = str(SCRIPT_DIR / "face_encodings.pkl")
TIMESTAMP_FILE     = str(SCRIPT_DIR / "pkltimestamp")
LOG_FILE           = "unauthorized_log.csv"

# Logging & Warnings
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
warnings.filterwarnings("ignore", category=DeprecationWarning)
cv2.setNumThreads(0)

device = torch.device('cuda' if torch.cuda.is_available() else 'cpu')

# Load Models (heavy objects reused across cameras)
face_model   = YOLO(YOLO_FACE_PATH).to(device)
embedder     = FaceNet()
person_model = YOLO(YOLO_PERSON_PATH).to(device)
object_model = YOLO(YOLO_OBJECT_PATH).to(device)
OBJECT_CONFIDENCE_THRESHOLD = 0.75

# Ensure base dir exists
try:
    ANOMALY_BASE_DIR.mkdir(parents=True, exist_ok=True)
except Exception:
    logging.warning(f"Could not create anomaly base dir: {ANOMALY_BASE_DIR}")


options = vision.FaceLandmarkerOptions(
    base_options=base_options.BaseOptions(
        model_asset_path=r"C:\Users\dusai\Desktop\Quantum_Threat_Detection\model\face_landmarker.task"
    ),
    running_mode=vision.RunningMode.IMAGE,
    num_faces=1)

# ----------------- Helper -----------------
def normalize_source(source):
    if isinstance(source, str) and source.isdigit():
        return int(source)
    return source

# ---------------------------- Embeddings loader ----------------------------
embeddings_dict = {}
centroid_names = []
centroid_matrix = None

def load_embeddings():
    global embeddings_dict, centroid_names, centroid_matrix
    try:
        with open(EMBEDDINGS_FILE, 'rb') as f:
            raw = pickle.load(f)
    except Exception as e:
        logging.error(f"[Monitor] Failed to open embeddings file {EMBEDDINGS_FILE}: {e}")
        embeddings_dict = {}
        centroid_names = []
        centroid_matrix = None
        return
    new_map = {}
    for name, v in raw.items():
        try:
            if isinstance(v, dict) and 'embeddings' in v and 'centroid' in v:
                embs = np.asarray(v['embeddings'], dtype=np.float32)
                cent = np.asarray(v['centroid'], dtype=np.float32)
            else:
                embs = np.asarray(v, dtype=np.float32)
                if embs.ndim == 1:
                    embs = np.expand_dims(embs, axis=0)
                cent = np.mean(embs, axis=0) if embs.size else None
            if embs.size:
                embs = np.array([e / (np.linalg.norm(e) + 1e-10) for e in embs], dtype=np.float32)
            if cent is not None:
                cent = cent / (np.linalg.norm(cent) + 1e-10)
            new_map[name] = {"embeddings": embs, "centroid": cent}
        except Exception as e:
            logging.warning(f"[Monitor] Skipping corrupted entry for {name}: {e}")
            continue
    embeddings_dict = new_map
    centroid_names = []
    centroids = []
    for name, info in embeddings_dict.items():
        c = info.get('centroid')
        if c is None:
            embs = info.get('embeddings')
            if embs is not None and embs.size:
                c = np.mean(embs, axis=0)
                c = c / (np.linalg.norm(c) + 1e-10)
            else:
                continue
        centroid_names.append(name)
        centroids.append(c)
    if centroids:
        centroid_matrix = np.vstack(centroids).astype(np.float32)
    else:
        centroid_matrix = None
    logging.info(f"[Monitor] Reloaded embeddings for {len(embeddings_dict)} identities (centroids: {len(centroid_names)})")

load_embeddings()

# watch pkltimestamp updates
last_ts = 0
if os.path.exists(TIMESTAMP_FILE):
    try:
        last_ts = float(open(TIMESTAMP_FILE).read())
    except:
        last_ts = 0

def watch_for_updates(interval=5):
    global last_ts
    while True:
        try:
            ts = float(open(TIMESTAMP_FILE).read())
            if ts > last_ts:
                logging.info("[Monitor] Detected updated pkltimestamp, reloading embeddings...")
                load_embeddings()
                last_ts = ts
        except FileNotFoundError:
            pass
        except Exception as e:
            logging.error(f"[Monitor] Error watching pkltimestamp: {e}")
        time.sleep(interval)

threading.Thread(target=watch_for_updates, daemon=True).start()

# Load icons
verified_icon = cv2.imread(ICON_VERIFIED_PATH, cv2.IMREAD_UNCHANGED)
unverified_icon = cv2.imread(ICON_UNVERIFIED_PATH, cv2.IMREAD_UNCHANGED)
def ensure_alpha(icon):
    if icon is None:
        return None
    if icon.ndim == 3 and icon.shape[2] == 3:
        alpha = np.ones((icon.shape[0], icon.shape[1]), dtype=icon.dtype) * 255
        return np.dstack((icon, alpha))
    return icon
verified_icon = ensure_alpha(verified_icon)
unverified_icon = ensure_alpha(unverified_icon)

# ------------------------- Multi-camera state -------------------------
camera_registry = {}
latest_frames = {}
latest_faces = {}
latest_anomalies = {}
frame_buffers = {}  # camera_id -> collections.deque(maxlen=ANOMALY_BUFFER_SIZE)

# Cooldown tracking (camera_id -> last_saved_timestamp)
last_anomaly_save = {}
last_unauthorized_save = {}


# ------------------------- Compatibility globals -------------------------
frame_queue       = queue.Queue(maxsize=10)
recognition_queue = queue.Queue()
results_queue     = queue.Queue()
stop_threads      = False
authorization_cache = {}
cache_last_refresh  = 0
track_info          = {}
last_identity = {}

# ------------------------- Celery dispatch (lazy) -------------------------
def _dispatch_to_celery(event_type, camera_id, data):
    try:
        from celery_tasks import process_face_event, process_anomaly_event
        payload = {"camera_id": camera_id, "data": data}
        if event_type == "face":
            try:
                process_face_event.delay(payload)
            except Exception as e:
                logging.debug(f"[Monitor] Failed to dispatch face task to Celery: {e}")
        elif event_type == "anomaly":
            try:
                process_anomaly_event.delay(payload)
            except Exception as e:
                logging.debug(f"[Monitor] Failed to dispatch anomaly task to Celery: {e}")
    except Exception:
        return

def on_face_recognized(camera_id, data):
    try:
        _dispatch_to_celery("face", camera_id, data)
    except Exception:
        pass
    return

def on_anomaly(camera_id, data):
    try:
        _dispatch_to_celery("anomaly", camera_id, data)
    except Exception:
        pass
    return

# ------------------------- DB & helpers -------------------------
def connect_to_db():
    return mysql.connector.connect(**DB_CONFIG)

def check_authorization(name):
    global cache_last_refresh
    now = time.time()
    if now - cache_last_refresh > AUTH_CACHE_TTL:
        authorization_cache.clear()
        cache_last_refresh = now
    if name in authorization_cache:
        return authorization_cache[name]
    try:
        conn = connect_to_db()
        cur = conn.cursor()
        cur.execute(
            "SELECT Certificate1, Certificate2, Certificate3, Certificate4 FROM IdentityManagement WHERE PersonName=%s",
            (name,)
        )
        row = cur.fetchone()
        conn.close()
    except Exception as e:
        logging.error(f"DB error: {e}")
        return False
    if not row:
        authorization_cache[name] = False
        return False
    cert1, flag2, cert3, flag4 = row
    try:
        cert1 = (datetime.datetime.strptime(cert1, '%Y-%m-%d').date() if isinstance(cert1, str) else cert1)
        cert3 = (datetime.datetime.strptime(cert3, '%Y-%m-%d').date() if isinstance(cert3, str) else cert3)
    except Exception:
        authorization_cache[name] = False
        return False
    valid = (cert1 >= datetime.date.today()) and bool(flag2) and (cert3 >= datetime.date.today()) and bool(flag4)
    authorization_cache[name] = valid
    return valid

def log_unauthorized(name, timestamp, track_id):
    try:
        with open(LOG_FILE, 'a', newline='') as f:
            csv.writer(f).writerow([timestamp, name, track_id])
    except Exception:
        pass

# ------------------------- Face helpers -------------------------
def align_face(image, landmarks):
    left, right = np.array(landmarks[0]), np.array(landmarks[1])
    dY, dX = right[1]-left[1], right[0]-left[0]
    angle = np.degrees(np.arctan2(dY, dX))
    center = ((left[0]+right[0])/2, (left[1]+right[1])/2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, M, (image.shape[1], image.shape[0]), flags=cv2.INTER_LINEAR)

def preprocess_face(img):
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), INPUT_SIZE)

def extract_embeddings(faces):
    imgs = [preprocess_face(f) for f in faces]
    if not imgs:
        return np.zeros((0, 512), dtype=np.float32)
    try:
        embs = embedder.embeddings(imgs)
        embs = np.asarray(embs, dtype=np.float32)
        embs = np.array([e / (np.linalg.norm(e) + 1e-10) for e in embs], dtype=np.float32)
        return embs
    except Exception as e:
        logging.error(f"[Monitor] FaceNet embedding failed: {e}")
        return np.zeros((0, 512), dtype=np.float32)

def l2_normalize_vec(v):
    v = np.array(v, dtype=np.float32)
    n = np.linalg.norm(v)
    if n < 1e-10:
        return v
    return v / n

def recognize(emb):
    global centroid_matrix, centroid_names, embeddings_dict
    if centroid_matrix is None or len(centroid_names) == 0:
        return (None, 0.0)
    embn = l2_normalize_vec(emb)
    try:
        dists = cdist([embn], centroid_matrix, metric='cosine')[0]
    except Exception as e:
        logging.error(f"[Monitor] cdist failed: {e}")
        return (None, 0.0)
    idx = int(np.argmin(dists))
    centroid_sim = 1.0 - float(dists[idx])
    candidate_name = centroid_names[idx]
    if centroid_sim >= SIMILARITY_THRESHOLD:
        if FALLBACK_VERIFY:
            p_embs = embeddings_dict.get(candidate_name, {}).get('embeddings')
            if p_embs is not None and getattr(p_embs, 'size', 0) > 0:
                try:
                    d2 = cdist([embn], p_embs, metric='cosine')[0]
                    best_sim = 1.0 - float(np.min(d2))
                except Exception as e:
                    logging.warning(f"[Monitor] per-image verify failed for {candidate_name}: {e}")
                    best_sim = centroid_sim
                if best_sim >= max(SIMILARITY_THRESHOLD, centroid_sim - FALLBACK_MARGIN):
                    return (candidate_name, float(best_sim))
                else:
                    return (None, float(best_sim))
            else:
                return (candidate_name, float(centroid_sim))
        else:
            return (candidate_name, float(centroid_sim))
    else:
        return (None, float(centroid_sim))

def overlay_text(frame, vcnt, ucnt, fps):
    cv2.putText(frame, f"Authorized: {vcnt}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,255,0), 2)
    cv2.putText(frame, f"Unauthorized: {ucnt}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0,0,255), 2)
    cv2.putText(frame, f"FPS: {fps:.2f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 1)
    ts = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    cv2.putText(frame, ts, (10,120), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255,255,0), 1)

def detect_objects_within_box(img, box):
    x1,y1,x2,y2 = box
    roi = img[y1:y2, x1:x2]
    res = object_model(roi)[0]
    found = []
    for b in res.boxes:
        try:
            if b.conf >= OBJECT_CONFIDENCE_THRESHOLD:
                ox1,oy1,ox2,oy2 = map(int, b.xyxy[0])
                lbl = res.names[int(b.cls)]
                conf = float(b.conf.item())
                found.append({"label": lbl, "conf": conf, "xyxy": (x1+ox1, y1+oy1, x1+ox2, y1+oy2)})
        except Exception:
            continue
    return found

def run_behavior(frame):
    res = person_model(frame)[0]
    anomalies_found = []
    for box in res.boxes:
        if int(box.cls)==0:
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
            found = detect_objects_within_box(frame,(x1,y1,x2,y2))
            if found:
                # draw simple markers for found objects (non-blocking)
                for f in found:
                    xy = f.get("xyxy")
                    if xy:
                        try:
                            xA,yA,xB,yB = xy
                            cv2.rectangle(frame, (xA,yA), (xB,yB), (0,0,255), 2)
                            cv2.putText(frame, f"{f['label']} {f['conf']:.2f}", (xA, max(yA-6,0)),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0,0,255), 1)
                        except Exception:
                            pass
                anomalies_found.extend(found)
    return frame, anomalies_found

# ------------------------- Save anomaly clip + JSON (async helper) -------------------------
def _ensure_dir(p: Path):
    try:
        p.mkdir(parents=True, exist_ok=True)
    except Exception:
        pass

def save_anomaly_clip_and_json(camera_id: str, frames_list: list, anomaly_info: dict) -> tuple:
    
    if not frames_list or len(frames_list) == 0:
        logging.error("[Monitor] frames_list is EMPTY. Anomaly clip will not be saved.")
        return (None, None)

    frames_list = [f for f in frames_list if isinstance(f, np.ndarray)]
    if not frames_list:
        logging.error("[Monitor] frames_list contains no valid frames.")
        return (None, None)

    date_str = datetime.datetime.now().strftime("%Y-%m-%d")
    out_dir = ANOMALY_BASE_DIR / date_str
    _ensure_dir(out_dir)

    base_name = f"{camera_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}"
    video_path = out_dir / f"{base_name}.mp4"
    json_path = out_dir / f"{base_name}.json"

    try:
        if len(frames_list) == 0:
            logging.warning("[Monitor] No frames to save for anomaly.")
            return (None, None)
        h, w = frames_list[0].shape[:2]
        fps = TARGET_FPS
        fourcc = cv2.VideoWriter_fourcc(*'mp4v')
        writer = cv2.VideoWriter(str(video_path), fourcc, float(fps), (w, h))
        if not writer.isOpened():
            logging.error(f"[Monitor] VideoWriter failed to open: {video_path}")
            return (None, None)
        for f in frames_list:
            try:
                if f.dtype != np.uint8:
                    f = f.astype(np.uint8)
                if not f.flags['C_CONTIGUOUS']:
                    f = np.ascontiguousarray(f)
                writer.write(f)
            except Exception as e:
                logging.error(f"[Monitor] Failed writing frame: {e}")
        writer.release()
    except Exception as e:
        logging.error(f"[Monitor] Failed to write anomaly video: {e}")
        return (None, None)

    try:
        meta = {
            "camera_id": camera_id,
            "timestamp": datetime.datetime.now().isoformat(),
            "anomaly": anomaly_info,
            "video_path": str(video_path),
        }
        with open(str(json_path), 'w', encoding='utf-8') as jf:
            json.dump(meta, jf, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.error(f"[Monitor] Failed to write anomaly JSON: {e}")
        return (str(video_path), None)

    return (str(video_path), str(json_path))

def _async_save_and_dispatch(camera_id, frames_to_save, summary):
    """Run disk write and event dispatch in background thread to avoid stalling processing."""
    try:
        video_path, json_path = save_anomaly_clip_and_json(camera_id, frames_to_save, summary)
        ev = {
            "type": "anomaly",
            "camera_id": camera_id,
            "data": {
                "objects": summary.get("detected_objects", []),
                "count": summary.get("count", 0),
                "video_path": video_path,
                "json_path": json_path
            },
            "ts": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        }
        logging.info(f"[Monitor] Anomaly saved | video={video_path} | json={json_path}")

        latest_anomalies[camera_id] = ev
        try:
            on_anomaly(camera_id, ev["data"])
            _dispatch_to_celery("anomaly", camera_id, ev["data"])
        except Exception:
            pass
    except Exception as e:
        logging.error(f"[Monitor] _async_save_and_dispatch failed: {e}")

def collect_post_event_frames(camera_id, seconds):
    frames = []
    end_time = time.time() + seconds
    interval = 1.0 / TARGET_FPS

    while time.time() < end_time:
        frame = latest_frames.get(camera_id)
        if frame is not None:
            frames.append(frame.copy())
        time.sleep(interval)

    return frames

# ------------------------- Camera class (no GUI) -------------------------
class Camera:
    def __init__(self, camera_id, source, width=4096, height=2160):
        self.camera_id = camera_id
        self.source = normalize_source(source)
        self.width = width
        self.height = height

        self.frame_queue = queue.Queue(maxsize=10)
        self.recognition_queue = queue.Queue()
        self.results_queue = queue.Queue()
        self.stop_event = threading.Event()

        self.track_info = {}
        self.last_identity = {}

        latest_frames[self.camera_id] = None
        latest_faces[self.camera_id] = None
        latest_anomalies[self.camera_id] = None

        self.deep_sort = DeepSort(max_age=10)
        self.mp_face_mesh = vision.FaceLandmarker.create_from_options(options)
        # frame buffer (deque); holds latest N frames for anomaly clip
        frame_buffers[self.camera_id] = collections.deque(maxlen=ANOMALY_BUFFER_SIZE)

        self._t_capture = None
        self._t_recog = None
        self._t_process = None

    def start(self):
        logging.info(f"[Camera {self.camera_id}] Starting camera with source: {self.source}")
        self.stop_event.clear()
        self._t_recog = threading.Thread(target=self._recognition_worker, daemon=True)
        self._t_recog.start()
        self._t_capture = threading.Thread(target=self._capture_thread, daemon=True)
        self._t_capture.start()
        self._t_process = threading.Thread(target=self._process_loop, daemon=True)
        self._t_process.start()

    def stop(self, timeout=2.0):
        logging.info(f"[Camera {self.camera_id}] Stopping camera")
        self.stop_event.set()
        try:
            self.recognition_queue.put((None, None), timeout=0.5)
        except Exception:
            pass
        for t in (self._t_capture, self._t_recog, self._t_process):
            if t and t.is_alive():
                t.join(timeout)
        latest_frames.pop(self.camera_id, None)
        latest_faces.pop(self.camera_id, None)
        latest_anomalies.pop(self.camera_id, None)
        frame_buffers.pop(self.camera_id, None)

    def _capture_thread(self):
        last = 0
        try:
            cap = cv2.VideoCapture(self.source)
            try:
                cap.set(cv2.CAP_PROP_FRAME_WIDTH, self.width)
                cap.set(cv2.CAP_PROP_FRAME_HEIGHT, self.height)
            except Exception:
                pass
            if not cap.isOpened():
                logging.error(f"[Camera {self.camera_id}] Cannot open source {self.source}")
                return
        except Exception as e:
            logging.error(f"[Camera {self.camera_id}] VideoCapture error: {e}")
            return

        while not self.stop_event.is_set():
            now = time.time()
            if now - last >= FRAME_INTERVAL:
                ret, fr = cap.read()
                if ret:
                    try:
                        if not self.frame_queue.full():
                            self.frame_queue.put(fr, timeout=0.1)
                    except Exception:
                        pass
                    try:
                        buf = frame_buffers.get(self.camera_id)
                        if buf is not None:
                            buf.append(fr.copy())
                    except Exception:
                        pass
                    last = now
            else:
                time.sleep(0.001)
        try:
            cap.release()
        except Exception:
            pass

    def _recognition_worker(self):
        while True:
            try:
                tid, face_img = self.recognition_queue.get()
            except Exception:
                tid, face_img = (None, None)
            if face_img is None:
                break
            try:
                emb_arr = extract_embeddings([face_img])
                if emb_arr.shape[0] == 0:
                    self.results_queue.put((tid, "Unknown", False, 0.0, time.time()))
                    continue
                emb = emb_arr[0]
            except Exception as e:
                logging.error(f"[Camera {self.camera_id}] embedding error in recognition_worker: {e}")
                self.results_queue.put((tid, "Unknown", False, 0.0, time.time()))
                continue

            name, sim = recognize(emb)
            auth = check_authorization(name) if name else False
            self.results_queue.put((tid, name or "Unknown", auth, sim, time.time()))

    def _process_loop(self):
        prev = time.time()
        while not self.stop_event.is_set():
            try:
                if self.frame_queue.empty():
                    time.sleep(0.001)
                    continue
                frame = self.frame_queue.get()
            except Exception:
                continue

            try:
                latest_frames[self.camera_id] = frame.copy()
            except Exception:
                latest_frames[self.camera_id] = None

            try:
                processed, anomalies_in_frame = run_behavior(frame.copy())
            except Exception as e:
                logging.exception(f"[Camera {self.camera_id}] run_behavior failed: {e}")
                processed = frame
                anomalies_in_frame = []

            dets = []
            try:
                for b in face_model(processed)[0].boxes:
                    if int(b.cls) == 0:
                        x1, y1, x2, y2 = map(int, b.xyxy[0])
                        dets.append(([x1, y1, x2 - x1, y2 - y1], 1.0, 'face'))
            except Exception as e:
                logging.warning(f"[Camera {self.camera_id}] face_model call failed: {e}")

            try:
                tracks = self.deep_sort.update_tracks(dets, frame=processed)
            except Exception as e:
                logging.warning(f"[Camera {self.camera_id}] deep_sort update failed: {e}")
                tracks = []

            now = time.time()

            self.track_info = {
                tid: info
                for tid, info in self.track_info.items()
                if now - info['last_seen'] < TRACK_MEMORY_TTL
            }
            self.last_identity = {
                tid: info
                for tid, info in self.last_identity.items()
                if now - info['last_seen'] < IDENTITY_PERSISTENCE_TTL
            }

            while not self.results_queue.empty():
                try:
                    tid, name, auth, sim, tstamp = self.results_queue.get_nowait()
                except Exception:
                    break
                entry = {'name': name, 'auth': auth, 'similarity': sim, 'last_seen': tstamp}
                self.track_info[tid] = entry
                self.last_identity[tid] = entry.copy()
                try:
                    ev = {'name': name, 'auth': auth, 'similarity': sim, 'timestamp': tstamp}
                    latest_faces[self.camera_id] = ev
                    try:
                        on_face_recognized(self.camera_id, ev)
                    except Exception:
                        pass
                except Exception:
                    pass

            vcnt = ucnt = 0
            for tr in tracks:
                if not tr.is_confirmed() or tr.time_since_update > 0:
                    continue
                tid = tr.track_id
                l, t, w, h = map(int, tr.to_ltwh())
                roi = processed[t:t+h, l:l+w]
                if isinstance(roi, np.ndarray) and roi.size == 0:
                    continue

                info = self.track_info.get(tid)
                if not info:
                    last_info = self.last_identity.get(tid)
                    if last_info and (now - last_info['last_seen'] < IDENTITY_PERSISTENCE_TTL):
                        info = last_info
                        self.track_info[tid] = info
                    else:
                        try:
                            rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                            #lm_res = self.mp_face_mesh.process(rgb)
                            lm_res = self.mp_face_mesh.detect(mp.Image(image_format=mp.ImageFormat.SRGB, data=rgb))

                            if not lm_res.multi_face_landmarks:
                                continue
                            pts = lm_res.multi_face_landmarks[0].landmark
                            left = (int(pts[33].x * w), int(pts[33].y * h))
                            right = (int(pts[263].x * w), int(pts[263].y * h))
                            aligned = align_face(roi, [left, right])
                            try:
                                self.recognition_queue.put((tid, aligned), timeout=0.1)
                            except Exception:
                                pass
                        except Exception:
                            continue
                        continue

                name, auth, sim = info['name'], info['auth'], info['similarity']
                col = (0, 255, 0) if auth else (0, 0, 255)
                if auth:
                    vcnt += 1
                else:
                    ucnt += 1
                    try:
                        log_unauthorized(name, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), tid)
                    except Exception:
                        pass

                try:
                    cv2.rectangle(processed, (l, t), (l+w, t+h), col, 2)
                    text_x = l + w + 5
                    line_y = t + 15
                    cv2.putText(processed, f"Name: {name}", (text_x, line_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
                    details = fetch_worker_details(name)
                    if details:
                        for key in ("BadgeID", "Position", "Company", "AccessLevel"):
                            line_y += 20
                            cv2.putText(processed, f"{key}: {details[key]}",
                                        (text_x, line_y),
                                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
                    else:
                        line_y += 20
                        cv2.putText(processed, "(details not found)", (text_x, line_y),
                                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
                except Exception:
                    pass

            # overlay
            fps = 1.0 / max(1e-6, (time.time() - prev))
            prev = time.time()
            try:
                overlay_text(processed, vcnt, ucnt, fps)
            except Exception:
                pass

            # If anomalies detected by run_behavior (object_model inside boxes), save clip and dispatch event
#            try:
#                if anomalies_in_frame:
#                    now_ts = time.time()
#                    last_ts = last_anomaly_save.get(self.camera_id, 0)
                    
                    # --- Cooldown check ---
                    
#                    if now_ts - last_ts >= ANOMALY_COOLDOWN_SECONDS:
#                        last_anomaly_save[self.camera_id] = now_ts
                        
                        # --- Pre-event frames (buffer) ---
                        
#                        pre_frames = list(frame_buffers.get(self.camera_id, []))
                        
                        # --- Post-event frames ---
                        
#                        post_frames = collect_post_event_frames(
#                            self.camera_id,
#                            POST_EVENT_SECONDS
#                        )
                        
#                        frames_to_save = pre_frames + post_frames
                        
#                        summary = {
#                            "detected_objects": anomalies_in_frame,
#                            "count": len(anomalies_in_frame),
#                            "pre_seconds": PRE_EVENT_SECONDS,
#                            "post_seconds": POST_EVENT_SECONDS
#                        }
                        
                        # Save + dispatch in background thread
                        
#                        threading.Thread(
#                            target=_async_save_and_dispatch,
#                            args=(self.camera_id, frames_to_save, summary),
#                            daemon=True
#                        ).start()
                        
#            except Exception as e:
#                logging.error(f"[Monitor] Anomaly handling failed: {e}")
                    
                    
                

#                    buf = frame_buffers.get(self.camera_id)
#                    if buf:
#                        frames_to_save = list(buf)
#                    else:
#                        frames_to_save = [processed]
#                    summary = {"detected_objects": anomalies_in_frame, "count": len(anomalies_in_frame)}
#                    # Save + dispatch in background thread
#                    threading.Thread(target=_async_save_and_dispatch, args=(self.camera_id, frames_to_save, summary), daemon=True).start()
#            except Exception as e:
#                logging.error(f"[Monitor] Anomaly handling failed: {e}")

#        # cleanup when loop exits
#        try:
#            frame_buffers.pop(self.camera_id, None)
#        except Exception:
#            pass
        
# If anomalies detected, trigger background recording
            try:
                if anomalies_in_frame:
                    logging.info(f"[Monitor] Anomaly detected on camera {self.camera_id} | count={len(anomalies_in_frame)}")

                    now_ts = time.time()
                    last_ts = last_anomaly_save.get(self.camera_id, 0)
                    
                    if now_ts - last_ts >= ANOMALY_COOLDOWN_SECONDS:
                        last_anomaly_save[self.camera_id] = now_ts
                        
                        # Grab the PRE-EVENT frames immediately (before they are overwritten)
                        buf = frame_buffers.get(self.camera_id)
                        pre_frames = list(buf) if buf and len(buf) > 0 else [processed.copy()]

                        #pre_frames = list(frame_buffers.get(self.camera_id, []))
                        
                        summary = {
                            "detected_objects": anomalies_in_frame,
                            "count": len(anomalies_in_frame),
                            "pre_seconds": PRE_EVENT_SECONDS,
                            "post_seconds": POST_EVENT_SECONDS
                        }
                        
                        # Define a small wrapper to wait for POST-frames WITHOUT blocking this loop
                        def background_recording_task(cid, pre, summ):
                            # This part waits, but it's in its own thread so it's okay!
                            post = collect_post_event_frames(cid, POST_EVENT_SECONDS)
                            all_frames = pre + post
                            _async_save_and_dispatch(cid, all_frames, summ)

                        # Start the background task
                        threading.Thread(
                            target=background_recording_task,
                            args=(self.camera_id, pre_frames, summary),
                            daemon=True
                        ).start()
                    else:
                        logging.info(
                                   f"[Monitor] Anomaly ignored due to cooldown ({ANOMALY_COOLDOWN_SECONDS}s)"
                                )

                        
            except Exception as e:
                logging.error(f"[Monitor] Anomaly handling setup failed: {e}")        



# ------------------------- Registry helpers -------------------------
def add_camera(camera_id, source):
    if camera_id in camera_registry:
        raise ValueError(f"Camera id {camera_id} already exists")
    cam = Camera(camera_id, source)
    camera_registry[camera_id] = cam
    logging.info(f"[Registry] Added camera {camera_id} -> {source}")
    return cam

def remove_camera(camera_id):
    cam = camera_registry.get(camera_id)
    if not cam:
        raise KeyError(f"Camera id {camera_id} not found")
    try:
        cam.stop()
    except Exception:
        pass
    camera_registry.pop(camera_id, None)
    logging.info(f"[Registry] Removed camera {camera_id}")

def start_camera(camera_id):
    cam = camera_registry.get(camera_id)
    if not cam:
        raise KeyError(f"Camera id {camera_id} not found")
    cam.start()
    logging.info(f"[Registry] Started camera {camera_id}")

def stop_camera(camera_id):
    cam = camera_registry.get(camera_id)
    if not cam:
        raise KeyError(f"Camera id {camera_id} not found")
    cam.stop()
    logging.info(f"[Registry] Stopped camera {camera_id}")

def get_latest_frame(camera_id):
    return latest_frames.get(camera_id)

def get_latest_faces(camera_id):
    return latest_faces.get(camera_id)

def get_latest_anomalies(camera_id):
    return latest_anomalies.get(camera_id)

def list_cameras():
    return list(camera_registry.keys())

def fetch_worker_details(name):
    try:
        conn = connect_to_db()
        cur = conn.cursor()
        cur.execute("""
            SELECT BadgeID, Position, Company, AccessLevel
              FROM WorkerIdentity
             WHERE PersonName = %s
        """, (name,))
        row = cur.fetchone()
        conn.close()
        if row:
            return {
                "BadgeID":   row[0],
                "Position":  row[1],
                "Company":   row[2],
                "AccessLevel": row[3]
            }
    except Exception as e:
        logging.error(f"DB lookup error for {name}: {e}")
    return None


# ------------------------- Backward compatible main (for local testing) -------------------------
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', default='0', help="camera index or video file")
    parser.add_argument('--identity-persistence-ttl', type=float, default=IDENTITY_PERSISTENCE_TTL,
                        help="Seconds to keep last-known identity per track (0 to disable)")
    args = parser.parse_args()

    IDENTITY_PERSISTENCE_TTL = float(args.identity_persistence_ttl)
    src = int(args.video) if args.video.isdigit() else args.video

    tmp_id = f"local-{uuid.uuid4().hex[:8]}"
    cam = Camera(tmp_id, src)
    camera_registry[tmp_id] = cam
    try:
        cam.start()
        while not cam.stop_event.is_set():
            time.sleep(0.5)
    except KeyboardInterrupt:
        pass
    finally:
        try:
            cam.stop()
        except Exception:
            pass
        camera_registry.pop(tmp_id, None)
