# train_face2.py

import os
import cv2
import numpy as np
import pickle
from keras_facenet import FaceNet
import mediapipe as mp
import datetime
from pathlib import Path
from mediapipe.tasks import python
from mediapipe.tasks.python import vision

from mediapipe.tasks.python.core import base_options



# --- Paths relative to repo root ---
BASE_DIR = Path(__file__).resolve().parent      # scripts/
ROOT_DIR = BASE_DIR.parent                      # inappropriate_behaviour_v3/

DATA_DIR = ROOT_DIR / "face_data"
OUTPUT_FILE = BASE_DIR / "face_encodings.pkl"
TIMESTAMP_FILE = BASE_DIR / "pkltimestamp"

# Ensure training directory exists
os.makedirs(BASE_DIR, exist_ok=True)

# Face detection helper (MediaPipe)
#mp_face_detection = mp.solutions.face_detection

# -------- MediaPipe Tasks FaceLandmarker (TRAINING) --------
face_landmarker_options = vision.FaceLandmarkerOptions(
    base_options=base_options.BaseOptions(
        model_asset_path=str(ROOT_DIR / "model" / "face_landmarker.task")
  
    ),
    running_mode=vision.RunningMode.IMAGE,
    num_faces=1
)

face_landmarker = vision.FaceLandmarker.create_from_options(face_landmarker_options)



def scale_box(box, scale_factor=1.2):
    x, y, w, h = box
    cx, cy = x + w // 2, y + h // 2
    w, h = int(w * scale_factor), int(h * scale_factor)
    x, y = cx - w // 2, cy - h // 2
    return max(0, x), max(0, y), w, h


def detect_faces_facelandmarker(image):
    """
    Detect faces using MediaPipe FaceLandmarker.
    Returns list of (face_crop, (x,y,w,h)) — SAME FORMAT as before.
    """
    h_img, w_img, _ = image.shape
    mp_image = mp.Image(image_format=mp.ImageFormat.SRGB,
                        data=cv2.cvtColor(image, cv2.COLOR_BGR2RGB))

    result = face_landmarker.detect(mp_image)
    faces = []

    if not result.face_landmarks:
        return faces

    for landmarks in result.face_landmarks:
        xs = [lm.x for lm in landmarks]
        ys = [lm.y for lm in landmarks]

        x1 = int(min(xs) * w_img)
        y1 = int(min(ys) * h_img)
        x2 = int(max(xs) * w_img)
        y2 = int(max(ys) * h_img)

        # safety clamp
        x1, y1 = max(0, x1), max(0, y1)
        x2, y2 = min(w_img, x2), min(h_img, y2)

        if x2 <= x1 or y2 <= y1:
            continue

        face_crop = image[y1:y2, x1:x2]
        if face_crop.size == 0:
            continue
        faces.append((face_crop, (x1, y1, x2 - x1, y2 - y1)))

    return faces




# Preprocessing for FaceNet
INPUT_SIZE = (160, 160)

def preprocess_image(image):
    """Resize and convert image for FaceNet."""
    return cv2.resize(cv2.cvtColor(image, cv2.COLOR_BGR2RGB), INPUT_SIZE)

# Initialize embedder
embedder = FaceNet()

# --- Quality & normalization helpers ---
MIN_FACE_AREA = 32 * 32      # pixels; adjust for distant cameras
BLUR_VAR_THRESHOLD = 40.0    # variance of Laplacian threshold for blur (tweak as needed)
_EMB_EPS = 1e-10

def face_quality_ok(face_crop):
    """Basic quality checks: size and blur. Return True if acceptable."""
    try:
        h, w = face_crop.shape[:2]
    except Exception:
        return False
    if h * w < MIN_FACE_AREA:
        return False
    # blur check using variance of Laplacian
    try:
        gray = cv2.cvtColor(face_crop, cv2.COLOR_BGR2GRAY)
        var = cv2.Laplacian(gray, cv2.CV_64F).var()
        if var < BLUR_VAR_THRESHOLD:
            return False
    except Exception:
        return False
    return True

def l2_normalize(v):
    v = np.array(v, dtype=np.float32)
    n = np.linalg.norm(v)
    if n < _EMB_EPS:
        return v
    return v / n

def extract_embeddings(faces):
    """Generate L2-normalized embeddings for list of face crops.
    Input `faces` is list of tuples (face_crop, bbox) to preserve original signature.
    Returns numpy array shape (N, D)
    """
    imgs = []
    for face, _ in faces:
        try:
            imgs.append(preprocess_image(face))
        except Exception as e:
            # skip problematic images
            print(f"[train] skipping preprocessing of a face: {e}")
    if not imgs:
        return np.zeros((0, 512), dtype=np.float32)  # FaceNet default dim is 512
    try:
        embs = embedder.embeddings(imgs)
    except Exception as e:
        print(f"[train] FaceNet embeddings call failed: {e}")
        return np.zeros((0, 512), dtype=np.float32)
    # normalize each embedding
    embs = np.asarray(embs, dtype=np.float32)
    embs = np.array([l2_normalize(e) for e in embs], dtype=np.float32)
    return embs

# Training function
def train_model():
    embeddings_dict = {}

    persons = [p for p in os.listdir(DATA_DIR) if (DATA_DIR / p).is_dir()]
    print(f"[train] Found {len(persons)} person folders in {DATA_DIR}")

    for person in persons:
        person_path = DATA_DIR / person
        person_embeddings = []

        image_files = [f for f in os.listdir(person_path)
                       if f.lower().endswith(('.jpg', '.jpeg', '.png'))]

        if not image_files:
            print(f"[train] no image files for {person}, skipping")
            continue

        for img_name in image_files:
            img_path = person_path / img_name
            image = cv2.imread(str(img_path))

            if image is None:
                print(f"[train] failed to read {img_path}, skipping")
                continue

            faces = detect_faces_facelandmarker(image)
            if not faces:
                continue

            good_faces = []
            for face_crop, bbox in faces:
                if face_quality_ok(face_crop):
                    good_faces.append((face_crop, bbox))

            if not good_faces:
                continue

            try:
                embs = extract_embeddings(good_faces)
                for e in embs:
                    person_embeddings.append(e)
            except Exception as e:
                print(f"[train] embedding error for {img_path}: {e}")

        if person_embeddings:
            arr = np.vstack(person_embeddings).astype(np.float32)
            arr = np.array([l2_normalize(e) for e in arr], dtype=np.float32)
            centroid = l2_normalize(np.mean(arr, axis=0))

            embeddings_dict[person] = {
                "embeddings": arr,
                "centroid": centroid
            }

            print(f"[train] processed {person}: {arr.shape[0]} embeddings")
        else:
            print(f"[train] no valid embeddings for {person}, skipping")

    # Save pickle
    with open(OUTPUT_FILE, "wb") as f:
        pickle.dump(embeddings_dict, f)

    with open(TIMESTAMP_FILE, "w") as flag:
        flag.write(str(datetime.datetime.now().timestamp()))

    print("[train] Training complete")


# Entry point for training
if __name__ == "__main__":
    train_model()
