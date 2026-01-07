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

import mediapipe as mp
from ultralytics import YOLO
from keras_facenet import FaceNet
from deep_sort_realtime.deepsort_tracker import DeepSort
import mysql.connector

# ----------------- Patch: Force torchvision.ops.nms to run on CPU -----------------
_orig_nms = tv_ops.nms

def nms_cpu_fallback(boxes, scores, iou_threshold):
    return _orig_nms(boxes.cpu(), scores.cpu(), iou_threshold)

tv_ops.nms = nms_cpu_fallback

# ----------------- Configuration -----------------
FRAME_DOWNSCALE = 1
INPUT_SIZE = (160, 160)
SIMILARITY_THRESHOLD = 0.55
# Whether to verify centroid match against per-image embeddings
FALLBACK_VERIFY = True
FALLBACK_MARGIN = 0.02

AUTH_CACHE_TTL = 10
TRACK_MEMORY_TTL = 10
IDENTITY_PERSISTENCE_TTL = 5    
TARGET_FPS = 10
FRAME_INTERVAL = 1 / TARGET_FPS

DB_CONFIG = {
    'host': 'localhost',
    'user': 'admin123',
    'password': 'Petro@123',
    'database': 'RestrictedAreaDB'
}



# --- Base paths relative to this script ---
BASE_DIR = Path(__file__).resolve().parent      # scripts/
ROOT_DIR = BASE_DIR.parent                      # inappropriate_behaviour_v3/

MODEL_DIR = ROOT_DIR / "model"
ICON_DIR  = ROOT_DIR / "icon"
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

# Load Models
face_model   = YOLO(YOLO_FACE_PATH).to(device)
embedder     = FaceNet()
deep_sort     = DeepSort(max_age=10)
person_model = YOLO(YOLO_PERSON_PATH).to(device)
object_model = YOLO(YOLO_OBJECT_PATH).to(device)
mp_face_mesh = mp.solutions.face_mesh.FaceMesh(static_image_mode=False)
OBJECT_CONFIDENCE_THRESHOLD = 0.75

# ----------------------------
# Embedding structures / loader
# ----------------------------
embeddings_dict = {}   # format: {name: {"embeddings": np.array(...), "centroid": np.array(...) } }
centroid_names = []    # list of person names corresponding to centroid_matrix rows
centroid_matrix = None # numpy array shape (N_people, dim)

def load_embeddings():
    """Load embeddings from pickle and build centroid matrix for fast search.
       Handles both new format (dict with embeddings+centroid) and older format
       where values were just numpy arrays of embeddings.
    """
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

    # Normalize and reformat into the new canonical structure
    new_map = {}
    for name, v in raw.items():
        try:
            # If v is dict with keys 'embeddings' and 'centroid', accept it
            if isinstance(v, dict) and 'embeddings' in v and 'centroid' in v:
                embs = np.asarray(v['embeddings'], dtype=np.float32)
                cent = np.asarray(v['centroid'], dtype=np.float32)
            else:
                # old format: v is array of embeddings
                embs = np.asarray(v, dtype=np.float32)
                if embs.ndim == 1:
                    # single vector -> convert to (1,D)
                    embs = np.expand_dims(embs, axis=0)
                cent = np.mean(embs, axis=0) if embs.size else None
            # L2-normalize embeddings and centroid
            if embs.size:
                embs = np.array([e / (np.linalg.norm(e) + 1e-10) for e in embs], dtype=np.float32)
            if cent is not None:
                cent = cent / (np.linalg.norm(cent) + 1e-10)
            new_map[name] = {
                "embeddings": embs,
                "centroid": cent
            }
        except Exception as e:
            logging.warning(f"[Monitor] Skipping corrupted entry for {name}: {e}")
            continue

    embeddings_dict = new_map

    # build centroid matrix
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


# Initial load
load_embeddings()

# Track last timestamp
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

# Load and ensure icons have alpha
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

# Queues & state
frame_queue       = queue.Queue(maxsize=10)
recognition_queue = queue.Queue()
results_queue     = queue.Queue()
stop_threads      = False
authorization_cache = {}
cache_last_refresh  = 0
track_info          = {}

# NEW: last known identity per track to reduce flicker
last_identity = {}  # track_id -> {'name','auth','similarity','last_seen'}

# Helper functions
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
    with open(LOG_FILE, 'a', newline='') as f:
        csv.writer(f).writerow([timestamp, name, track_id])

# Utilities
def align_face(image, landmarks):
    left, right = np.array(landmarks[0]), np.array(landmarks[1])
    dY, dX = right[1]-left[1], right[0]-left[0]
    angle = np.degrees(np.arctan2(dY, dX))
    center = ((left[0]+right[0])/2, (left[1]+right[1])/2)
    M = cv2.getRotationMatrix2D(center, angle, 1.0)
    return cv2.warpAffine(image, M, (image.shape[1], image.shape[0]), flags=cv2.INTER_LINEAR)

def preprocess_face(img):
    """Keep same preprocessing as training: BGR->RGB and resize."""
    return cv2.resize(cv2.cvtColor(img, cv2.COLOR_BGR2RGB), INPUT_SIZE)

def extract_embeddings(faces):
    """Return normalized embeddings for a list of face crops (faces: list of imgs)"""
    # Accept list of face images (BGR)
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
    """Improved recognition using centroids + optional per-image verification.
       Returns (name_or_None, similarity_score)
    """
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
        # Optional verify against per-image embeddings for the candidate
        if FALLBACK_VERIFY:
            p_embs = embeddings_dict.get(candidate_name, {}).get('embeddings')
            if p_embs is not None and getattr(p_embs, 'size', 0) > 0:
                try:
                    d2 = cdist([embn], p_embs, metric='cosine')[0]
                    best_sim = 1.0 - float(np.min(d2))
                except Exception as e:
                    logging.warning(f"[Monitor] per-image verify failed for {candidate_name}: {e}")
                    best_sim = centroid_sim
                # Accept if best_sim is reasonable (close to centroid_sim)
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
    for b in res.boxes:
        if b.conf >= OBJECT_CONFIDENCE_THRESHOLD:
            ox1,oy1,ox2,oy2 = map(int, b.xyxy[0])
            lbl = f"{res.names[int(b.cls)]} ({b.conf.item():.2f})"
            cv2.rectangle(img, (x1+ox1, y1+oy1), (x1+ox2, y1+oy2), (0,0,255), 2)
            cv2.putText(img, lbl, (x1+ox1, y1+oy1-10), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0,0,255), 2)

def run_behavior(frame):
    res = person_model(frame)[0]
    for box in res.boxes:
        if int(box.cls)==0:
            x1,y1,x2,y2 = map(int, box.xyxy[0])
            cv2.rectangle(frame,(x1,y1),(x2,y2),(0,255,0),2)
            detect_objects_within_box(frame,(x1,y1,x2,y2))
    return frame

def recognition_worker():
    """Worker that receives (track_id, face_img) where face_img is a BGR crop (aligned).
       It must always produce a results_queue item even for Unknown names so behavior detection continues.
    """
    while True:
        tid, face_img = recognition_queue.get()
        if face_img is None:
            break
        # face_img may be full roi; preprocess & embed
        try:
            emb_arr = extract_embeddings([face_img])
            if emb_arr.shape[0] == 0:
                # couldn't embed -> mark unknown
                results_queue.put((tid, "Unknown", False, 0.0, time.time()))
                continue
            emb = emb_arr[0]
        except Exception as e:
            logging.error(f"[Monitor] embedding error in recognition_worker: {e}")
            results_queue.put((tid, "Unknown", False, 0.0, time.time()))
            continue

        name, sim = recognize(emb)
        auth = check_authorization(name) if name else False
        results_queue.put((tid, name or "Unknown", auth, sim, time.time()))

def capture_thread(cap):
    last=0
    global stop_threads
    while not stop_threads:
        now=time.time()
        if now-last>=FRAME_INTERVAL:
            ret,fr=cap.read()
            if ret and not frame_queue.full(): frame_queue.put(fr); last=now

def fetch_worker_details(name):
    """Return BadgeID, Position, Company, AccessLevel for a given PersonName."""
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

def main(source=0):
    global stop_threads, track_info, last_identity
    # Start the recognition worker thread
    threading.Thread(target=recognition_worker, daemon=True).start()
    
    # Open video source
    cap = cv2.VideoCapture(source)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 4096)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 2160)
    if not cap.isOpened():
        print("Cannot open source, exiting.")
        return
    
    # Start the capture thread
    threading.Thread(target=capture_thread, args=(cap,), daemon=True).start()
    
    prev = time.time()
    while True:
        # Wait for next frame
        if frame_queue.empty():
            time.sleep(0.001)
            continue
        frame = frame_queue.get()
        
        # Run behavior detection first
        frame = run_behavior(frame)
        
        # Prepare face detections for tracking
        dets = []
        for b in face_model(frame)[0].boxes:
            if int(b.cls) == 0:
                x1, y1, x2, y2 = map(int, b.xyxy[0])
                dets.append(([x1, y1, x2 - x1, y2 - y1], 1.0, 'face'))
        
        # Update tracks
        tracks = deep_sort.update_tracks(dets, frame=frame)
        now = time.time()
        
        # Prune old track_info entries
        track_info = {
            tid: info
            for tid, info in track_info.items()
            if now - info['last_seen'] < TRACK_MEMORY_TTL
        }
        # ALSO prune last_identity entries older than IDENTITY_PERSISTENCE_TTL
        last_identity = {
            tid: info
            for tid, info in last_identity.items()
            if now - info['last_seen'] < IDENTITY_PERSISTENCE_TTL
        }
        
        # Pull any completed recognition results
        while not results_queue.empty():
            tid, name, auth, sim, tstamp = results_queue.get()
            # update both track_info and last_identity on recognition result
            entry = {
                'name': name,
                'auth': auth,
                'similarity': sim,
                'last_seen': tstamp
            }
            track_info[tid] = entry
            last_identity[tid] = entry.copy()
        
        vcnt = ucnt = 0
        for tr in tracks:
            if not tr.is_confirmed() or tr.time_since_update > 0:
                continue
            tid = tr.track_id
            l, t, w, h = map(int, tr.to_ltwh())
            roi = frame[t:t+h, l:l+w]
            if roi.size == 0:
                continue
            
            info = track_info.get(tid)
            if not info:
                # NEW: check last-known identity persistence before re-queuing recognition
                last_info = last_identity.get(tid)
                if last_info and (now - last_info['last_seen'] < IDENTITY_PERSISTENCE_TTL):
                    # reuse last-known identity to avoid flicker
                    info = last_info
                    # also keep in track_info for this loop
                    track_info[tid] = info
                else:
                    # First‐time face or stale identity, queue for recognition (original behavior)
                    rgb = cv2.cvtColor(roi, cv2.COLOR_BGR2RGB)
                    lm_res = mp_face_mesh.process(rgb)
                    if not lm_res.multi_face_landmarks:
                        continue
                    pts = lm_res.multi_face_landmarks[0].landmark
                    left = (int(pts[33].x * w), int(pts[33].y * h))
                    right = (int(pts[263].x * w), int(pts[263].y * h))
                    aligned = align_face(roi, [left, right])
                    recognition_queue.put((tid, aligned))
                    continue
            
            name, auth, sim = info['name'], info['auth'], info['similarity']
            col = (0, 255, 0) if auth else (0, 0, 255)
            if auth:
                vcnt += 1
            else:
                ucnt += 1
                log_unauthorized(name, datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), tid)
            
            # Draw bounding box and extended labels
            cv2.rectangle(frame, (l, t), (l+w, t+h), col, 2)
            text_x = l + w + 5
            
            # Line 1: PersonName
            line_y = t + 15
            cv2.putText(frame, f"Name: {name}", (text_x, line_y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, col, 2)
            
            # Fetch and draw BadgeID, Position, Company, AccessLevel
            details = fetch_worker_details(name)
            if details:
                for key in ("BadgeID", "Position", "Company", "AccessLevel"):
                    line_y += 20
                    cv2.putText(frame, f"{key}: {details[key]}",
                                (text_x, line_y),
                                cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 2)
            else:
                line_y += 20
                cv2.putText(frame, "(details not found)", (text_x, line_y),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.5, col, 1)
        
        # Overlay counts and FPS
        fps = 1.0 / (time.time() - prev)
        prev = time.time()
        overlay_text(frame, vcnt, ucnt, fps)
        
        # Display the frame
        cv2.imshow("Behaviour Monitoring", frame)
        if cv2.waitKey(1) & 0xFF == ord('q'):
            stop_threads = True
            break
    
    # Signal recognition thread to exit and clean up
    recognition_queue.put((None, None))
    cap.release()
    cv2.destroyAllWindows()


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument('--video', default='rtsp://admin:RMKRCX@169.254.58.237/', help="camera index or video file")
    #parser.add_argument('--video', default='0', help="camera index or video file")
    parser.add_argument('--identity-persistence-ttl', type=float, default=IDENTITY_PERSISTENCE_TTL,
                        help="Seconds to keep last-known identity per track (0 to disable)")
    args = parser.parse_args()
    
    IDENTITY_PERSISTENCE_TTL = float(args.identity_persistence_ttl)
    src = int(args.video) if args.video.isdigit() else args.video
    main(src)
