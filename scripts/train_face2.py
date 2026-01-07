import os
import cv2
import numpy as np
import pickle
from keras_facenet import FaceNet
import mediapipe as mp
import datetime
from pathlib import Path

# --- Paths relative to repo root ---
BASE_DIR = Path(__file__).resolve().parent      # scripts/
ROOT_DIR = BASE_DIR.parent                      # inappropriate_behaviour_v3/

DATA_DIR = ROOT_DIR / "face_data"
OUTPUT_FILE = BASE_DIR / "face_encodings.pkl"
TIMESTAMP_FILE = BASE_DIR / "pkltimestamp"

# Ensure training directory exists
os.makedirs(BASE_DIR, exist_ok=True)

# Face detection helper (MediaPipe)
mp_face_detection = mp.solutions.face_detection

def scale_box(box, scale_factor=1.2):
    x, y, w, h = box
    cx, cy = x + w // 2, y + h // 2
    w, h = int(w * scale_factor), int(h * scale_factor)
    x, y = cx - w // 2, cy - h // 2
    return max(0, x), max(0, y), w, h


def detect_faces_mediapipe(image, face_detection):
    """Detect and crop faces using MediaPipe.
    Returns list of (face_crop, (x,y,w,h)) as before.
    """
    results = face_detection.process(cv2.cvtColor(image, cv2.COLOR_BGR2RGB))
    faces = []
    if results.detections:
        h_img, w_img, _ = image.shape
        for detection in results.detections:
            bboxC = detection.location_data.relative_bounding_box
            x, y, w, h = int(bboxC.xmin * w_img), int(bboxC.ymin * h_img), int(bboxC.width * w_img), int(bboxC.height * h_img)
            x, y, w, h = scale_box((x, y, w, h))
            # Make sure box is within image
            x2 = max(0, min(x + w, w_img))
            y2 = max(0, min(y + h, h_img))
            x = max(0, x); y = max(0, y)
            if y2 <= y or x2 <= x:
                continue
            face = image[y:y2, x:x2]
            if face.size == 0:
                continue
            faces.append((face, (x, y, x2 - x, y2 - y)))
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
    """Scan data directory, extract embeddings, and pickle them.
    Improved:
      - filters low-quality face crops
      - stores per-person embeddings and centroid (mean) vector (both L2-normalized)
    """
    embeddings_dict = {}
    with mp_face_detection.FaceDetection(min_detection_confidence=0.5) as face_detection:
        persons = [p for p in os.listdir(DATA_DIR) if (DATA_DIR / p).is_dir()]
        print(f"[train] Found {len(persons)} person folders in {DATA_DIR}")
        for person in persons:
            person_path = DATA_DIR / person
            person_embeddings = []
            image_files = [f for f in os.listdir(person_path) if f.lower().endswith(('.jpg', '.jpeg', '.png'))]
            if not image_files:
                print(f"[train] no image files for {person}, skipping")
                continue
            for img_name in image_files:
                img_path = person_path / img_name
                image = cv2.imread(str(img_path))
                if image is None:
                    print(f"[train] failed to read {img_path}, skipping")
                    continue
                faces = detect_faces_mediapipe(image, face_detection)
                if not faces:
                    continue
                good_faces = []
                for (face_crop, bbox) in faces:
                    if face_quality_ok(face_crop):
                        good_faces.append((face_crop, bbox))
                if not good_faces:
                    continue
                try:
                    embs = extract_embeddings(good_faces)
                    if embs.shape[0] > 0:
                        for e in embs:
                            person_embeddings.append(e)
                except Exception as e:
                    print(f"[train] embedding extraction error for {img_path}: {e}")
                    continue
            if person_embeddings:
                arr = np.vstack(person_embeddings).astype(np.float32)
                arr = np.array([l2_normalize(e) for e in arr], dtype=np.float32)
                centroid = np.mean(arr, axis=0)
                centroid = l2_normalize(centroid)
                embeddings_dict[person] = {
                    "embeddings": arr,
                    "centroid": centroid
                }
                print(f"[train] processed {person}: {arr.shape[0]} embeddings, centroid computed")
            else:
                print(f"[train] no valid embeddings for {person}, skipping")

    # Save to disk (pickle)
    try:
        with open(OUTPUT_FILE, "wb") as f:
            pickle.dump(embeddings_dict, f)
        print(f"[train] Saved embeddings for {len(embeddings_dict)} identities to {OUTPUT_FILE}")
    except Exception as e:
        print(f"[train] Failed to save embeddings to {OUTPUT_FILE}: {e}")

    # Update timestamp flag for monitoring
    try:
        with open(TIMESTAMP_FILE, "w") as flag:
            flag.write(str(datetime.datetime.now().timestamp()))
        print(f"[train] Updated timestamp file {TIMESTAMP_FILE}")
    except Exception as e:
        print(f"[train] Failed to update timestamp file: {e}")

# Entry point for training
if __name__ == "__main__":
    train_model()
