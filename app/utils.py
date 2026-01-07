import time
import jwt
import shutil
import logging
from datetime import datetime, timedelta
from passlib.context import CryptContext # type: ignore
from flask import current_app

from pathlib import Path

from app.database import get_db_connection
from app.config import Config # Import Config to access paths

# Initialize the password context once
pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")

# --- AUTH/JWT HELPERS ---

def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)

def create_token(data: dict, expires: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires or timedelta(minutes=current_app.config["ACCESS_TOKEN_EXPIRE_MINUTES"]))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, current_app.config["SECRET_KEY"], algorithm=current_app.config["ALGORITHM"])

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, current_app.config["SECRET_KEY"], algorithms=[current_app.config["ALGORITHM"]])
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")


# --- DB HELPERS (CRUD lookups) ---

def get_user_by_username(username: str):
    db = get_db_connection(); cur = db.cursor()
    cur.execute("""
        SELECT U.username, U.employee_id, U.hashed_password, U.disabled, W.PersonName
        FROM users U
        LEFT JOIN workeridentity W USING (employee_id)
        WHERE U.username = %s
    """, (username,))
    r = cur.fetchone()
    cur.close(); db.close()
    return r

def get_access_level(employee_id: str):
    db = get_db_connection(); cur = db.cursor()
    cur.execute("""
        SELECT WI.accesslevel
        FROM workeridentity WI
        WHERE WI.employee_id = %s
    """, (employee_id,))
    r = cur.fetchone()
    cur.close(); db.close()
    return r

# --- FILE/FS HELPERS ---

_last_touch_time = 0
def touch_pkltimestamp_debounced():
    global _last_touch_time
    now = time.time()
    # Debounce check moved from 2 seconds to 1 second
    if now - _last_touch_time < 1:
        return

    _last_touch_time = now

    # Use paths from Config
    PKL_TIMESTAMP_FILE = current_app.config["PKL_TIMESTAMP_FILE"]
    PKL_TIMESTAMP_FILE.parent.mkdir(parents=True, exist_ok=True)

    with open(PKL_TIMESTAMP_FILE, "w") as f:
        f.write(datetime.utcnow().isoformat())
        f.flush()
    logging.info("pkltimestamp updated")

def _normalize_for_compare(name: str) -> str:
    return name.strip().lower().replace(" ", "_")

def resolve_person_folder(person_name: str) -> Path: # type: ignore
    # Use paths from Config
    FACE_DATA_DIR = current_app.config["FACE_DATA_DIR"]

    normalized_target = _normalize_for_compare(person_name)
    FACE_DATA_DIR.mkdir(parents=True, exist_ok=True)
    for existing in FACE_DATA_DIR.iterdir():
        if existing.is_dir() and _normalize_for_compare(existing.name) == normalized_target:
            return existing
    return FACE_DATA_DIR / person_name

def delete_face_data(person_name: str):
    """Deletes the employee's face data folder."""
    try:
        folder_path = resolve_person_folder(person_name)
        if folder_path.exists():
            shutil.rmtree(folder_path)
            logging.info(f"Deleted face data folder: {folder_path}")
            touch_pkltimestamp_debounced()
            return True
        return False
    except Exception as e:
        logging.error(f"Failed to delete face data for {person_name}: {e}")
        return False

def count_weekdays(start_date, end_date):
    """
    Calculate number of weekdays (Mon-Fri) between two dates inclusive.
    """
    days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5: # 0-4 are Mon-Fri
            days += 1
        current += timedelta(days=1)
    return days

# ----------------------------------------------------------------------
# Helper to fetch full employee profile data and map it to the required schema
# Modified to look up by BadgeID (employee_code) instead of internal integer ID
# ----------------------------------------------------------------------
def fetch_and_map_employee_details(db_cursor, employee_id):
    """
    Fetches employee data using BadgeID and maps workeridentity fields to the target 'Employee' schema.
    """
    db_cursor.execute("""
        SELECT
            WI.PersonName,
            WI.Employee_ID,
            WI.Position,
            WI.Department,
            WI.EMail,
            WI.Phone,
            WI.Status,
            IM.Certificate1, IM.Certificate3
        FROM workeridentity WI
        LEFT JOIN identitymanagement IM ON WI.Employee_ID = IM.Employee_ID
        WHERE WI.Employee_ID = %s
    """, (employee_id,)) # Query using the BadgeID string
    worker = db_cursor.fetchone()

    if not worker:
        return None

    # Map database fields to the requested 'Employee' schema fields
    person_name_parts = worker['PersonName'].split()

    # Assuming Certificate1 is the primary validity field (valid_to)
    valid_to = worker.get('Certificate1')
    if valid_to and isinstance(valid_to, datetime):
        valid_to = valid_to.strftime('%Y-%m-%d')

    # Map Status enum to boolean is_active
    is_active = worker.get('Status') == 'Active'

    return {
        "id": worker['ID'], # Internal integer ID
        "employee_id": worker['employee_id'], # Maps to BadgeID
        "first_name": person_name_parts[0] if person_name_parts else "",
        "last_name": " ".join(person_name_parts[1:]) if len(person_name_parts) > 1 else "",
        "email": worker['EMail'],
        "phone": worker['Phone'],
        "department": worker['Department'],
        "designation": worker['Position'],
        "valid_from": None,
        "valid_to": valid_to,
        "shift_start_time": None,
        "shift_end_time": None,
        "is_active": is_active,
        "created_at": None,
        "updated_at": None
    }