import os
import base64
import pickle
import time
import threading

import cv2
import numpy as np
from scipy.spatial.distance import cdist
from ultralytics import YOLO
from keras_facenet import FaceNet
import mysql.connector

from fastapi import FastAPI, HTTPException, File, UploadFile
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from typing import List, Dict, Any

# --- Database Configuration ---
DB_CONFIG = {
    'host': 'localhost',
    'user': 'admin123',
    'password': 'Petro@123',
    'database': 'RestrictedAreaDB'
}

# --- Base Directory (scripts/) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))   

# --- Models & Embeddings Paths ---
YOLO_FACE_PATH     = os.path.join(BASE_DIR, "..", "model", "yolov11n-face.pt")              
YOLO_BEHAVIOR_PATH = os.path.join(BASE_DIR, "..", "model", "inappropriate_behaviour.pt")    
EMBEDDINGS_FILE    = os.path.join(BASE_DIR, "face_encodings.pkl")                           
TIMESTAMP_FILE     = os.path.join(BASE_DIR, "pkltimestamp")                                 
SIMILARITY_THRESHOLD        = 0.5
OBJECT_CONFIDENCE_THRESHOLD = 0.5

# --- Initialize Models & Embedder ---
face_model     = YOLO(YOLO_FACE_PATH)
behavior_model = YOLO(YOLO_BEHAVIOR_PATH)
embedder       = FaceNet()

enbeddings_dict: Dict[str, Dict[str, np.ndarray]] = {}

# --- Load Embeddings ---
def load_embeddings():
    global enbeddings_dict
    try:
        with open(EMBEDDINGS_FILE, 'rb') as f:
            enbeddings_dict = pickle.load(f)
        print(f"[API] Loaded embeddings for {len(enbeddings_dict)} identities")
    except Exception as e:
        print(f"[API] Failed to load embeddings: {e}")

load_embeddings()

# --- Watcher Thread for Auto-Reload ---
def watch_embeddings(interval=5):
    last_ts = 0.0
    while True:
        try:
            ts = float(open(TIMESTAMP_FILE, 'r').read())
            if ts > last_ts:
                load_embeddings()
                last_ts = ts
        except Exception:
            pass
        time.sleep(interval)

threading.Thread(target=watch_embeddings, daemon=True).start()

# --- Database Helper ---
def connect_to_db():
    return mysql.connector.connect(**DB_CONFIG)

def fetch_worker_details(name: str) -> Dict[str, Any]:
    conn = connect_to_db()
    cur = conn.cursor(dictionary=True)
    cur.execute(
        """
        SELECT BadgeID, PersonName AS name, Position, Department,
               Company, AccessLevel, EMail, Phone, Status
          FROM WorkerIdentity
         WHERE PersonName = %s
        """,
        (name,)
    )
    row = cur.fetchone()
    conn.close()
    if not row:
        raise HTTPException(status_code=404, detail="Person not found")
    return row

# --- FastAPI App & Models ---
app = FastAPI()

class WorkerResponse(BaseModel):
    BadgeID: str
    name: str
    details: Dict[str, Any]

class RecognizeRequest(BaseModel):
    frame_b64: str

class RecognizedFace(BaseModel):
    BadgeID: str
    name: str
    details: Dict[str, Any]
    behavior: List[str]

class RecognizeResponse(BaseModel):
    faces: List[RecognizedFace]

# --- Root Redirect to Docs ---
@app.get("/")
def root():
    return RedirectResponse(url="/docs")

# --- Worker Details Endpoint ---
@app.get("/worker/{person_name}", response_model=WorkerResponse)
def get_worker(person_name: str):
    row = fetch_worker_details(person_name)
    return WorkerResponse(
        BadgeID=row['BadgeID'],
        name=row['name'],
        details={k: v for k, v in row.items() if k not in ('BadgeID', 'name')}
    )

# --- /recognize Endpoint ---
@app.post("/recognize", response_model=RecognizeResponse)
def recognize(request: RecognizeRequest):
    # Decode image
    try:
        img_data = base64.b64decode(request.frame_b64)
        nparr = np.frombuffer(img_data, np.uint8)
        frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid image data")

    # Behavior detection
    beh_res = behavior_model(frame)[0]
    behaviors = [beh_res.names[int(b.cls)] for b in beh_res.boxes if b.conf > OBJECT_CONFIDENCE_THRESHOLD]

    # Face detection & recognition
    face_res = face_model(frame)[0]
    faces_out: List[RecognizedFace] = []
    for b in face_res.boxes:
        if int(b.cls) != 0:
            continue
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        face = frame[y1:y2, x1:x2]
        name = "Unknown"
        if face.size and enbeddings_dict:
            face_rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
            face_resized = cv2.resize(face_rgb, (160, 160))
            emb = embedder.embeddings([face_resized])[0]

            # --- Use centroid from embeddings dict ---
            names, embs = zip(*[(n, v["centroid"]) for n, v in enbeddings_dict.items()])

            dists = cdist([emb], np.vstack(embs), metric='cosine')
            idx = dists.argmin()
            sim = 1 - dists[0, idx]
            if sim >= SIMILARITY_THRESHOLD:
                name = names[idx]

        # Lookup details if known
        row = {}
        if name != "Unknown":
            try:
                row = fetch_worker_details(name)
            except HTTPException:
                row = {}

        faces_out.append(RecognizedFace(
            BadgeID=row.get("BadgeID", ""),
            name=name,
            details={k: v for k, v in row.items() if k not in ("BadgeID", "name")},
            behavior=behaviors
        ))

    return RecognizeResponse(faces=faces_out)

# --- /recognize_file Endpoint ---
@app.post("/recognize_file", response_model=RecognizeResponse)
async def recognize_file(file: UploadFile = File(...)):
    # Read uploaded image
    data = await file.read()
    nparr = np.frombuffer(data, np.uint8)
    frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if frame is None:
        raise HTTPException(status_code=400, detail="Invalid image file")

    # Behavior detection
    beh_res = behavior_model(frame)[0]
    behaviors = [beh_res.names[int(b.cls)] for b in beh_res.boxes if b.conf > OBJECT_CONFIDENCE_THRESHOLD]

    # Face detection & recognition
    face_res = face_model(frame)[0]
    faces_out: List[RecognizedFace] = []
    for b in face_res.boxes:
        if int(b.cls) != 0:
            continue
        x1, y1, x2, y2 = map(int, b.xyxy[0])
        face = frame[y1:y2, x1:x2]
        name = "Unknown"
        if face.size and enbeddings_dict:
            face_rgb = cv2.cvtColor(face, cv2.COLOR_BGR2RGB)
            face_resized = cv2.resize(face_rgb, (160, 160))
            emb = embedder.embeddings([face_resized])[0]

            # --- Use centroid from embeddings dict ---
            names, embs = zip(*[(n, v["centroid"]) for n, v in enbeddings_dict.items()])

            dists = cdist([emb], np.vstack(embs), metric='cosine')
            idx = dists.argmin()
            sim = 1 - dists[0, idx]
            if sim >= SIMILARITY_THRESHOLD:
                name = names[idx]

        # Lookup details if known
        row = {}
        if name != "Unknown":
            try:
                row = fetch_worker_details(name)
            except HTTPException:
                row = {}

        faces_out.append(RecognizedFace(
            BadgeID=row.get("BadgeID", ""),
            name=name,
            details={k: v for k, v in row.items() if k not in ("BadgeID", "name")},
            behavior=behaviors
        ))

    return RecognizeResponse(faces=faces_out)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="127.0.0.1", port=8000)
