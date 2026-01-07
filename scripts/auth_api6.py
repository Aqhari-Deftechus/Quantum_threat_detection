import os
import logging
import time
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
import pymysql

from flask import Flask, request, jsonify
from flask_cors import CORS
from flasgger import Swagger, swag_from # type: ignore
from passlib.context import CryptContext
import jwt
from functools import wraps

# ======================================================
# CONFIGURATION
# ======================================================
DB_CONFIG = {
    "host": "localhost",
    "user": "root",
    "password": "2200",
    "database": "restrictedareadb"
}

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_TO_A_RANDOM_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

BASE_DIR = Path(__file__).resolve().parent
FACE_DATA_DIR = BASE_DIR.parent / "face_data"
PKL_TIMESTAMP_FILE = BASE_DIR / "pkltimestamp"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = Flask(__name__)
app.config["SECRET_KEY"] = SECRET_KEY
application=app  #<---- Afiq add
CORS(app)

pwd_ctx = CryptContext(schemes=["argon2"], deprecated="auto")

# ======================================================
# ENUMS (source of truth)
# ======================================================
class AccessLevel(str, Enum):
    Visitor = "Visitor"
    Employee = "Employee"
    Contractor = "Contractor"
    Security = "Security"
    Admin = "Admin"
    SuperAdmin = "SuperAdmin"

class StatusEnum(str, Enum):
    Active = "Active"
    Suspended = "Suspended"
    Terminated = "Terminated"

class CertBool(str, Enum):
    None_ = "0"
    Yes = "1"

class YearEnum(str, Enum):
    _2025 = "2025"; _2026 = "2026"; _2027 = "2027"; _2028 = "2028"; _2029 = "2029"
    _2030 = "2030"; _2031 = "2031"; _2032 = "2032"; _2033 = "2033"; _2034 = "2034"; _2035 = "2035"

class MonthEnum(str, Enum):
    Jan = "01"; Feb = "02"; Mar = "03"; Apr = "04"; May = "05"; Jun = "06"
    Jul = "07"; Aug = "08"; Sep = "09"; Oct = "10"; Nov = "11"; Dec = "12"

class DayEnum(str, Enum):
    _01="01"; _02="02"; _03="03"; _04="04"; _05="05"; _06="06"; _07="07"; _08="08"; _09="09"; _10="10"
    _11="11"; _12="12"; _13="13"; _14="14"; _15="15"; _16="16"; _17="17"; _18="18"; _19="19"; _20="20"
    _21="21"; _22="22"; _23="23"; _24="24"; _25="25"; _26="26"; _27="27"; _28="28"; _29="29"; _30="30"; _31="31"

# Helper lists for Swagger enum parameters (strings)
ACCESS_LEVEL_VALUES = [e.value for e in AccessLevel]
STATUS_VALUES = [e.value for e in StatusEnum]
CERTBOOL_VALUES = [e.value for e in CertBool]
YEAR_VALUES = [e.value for e in YearEnum]
MONTH_VALUES = [e.value for e in MonthEnum]
DAY_VALUES = [e.value for e in DayEnum]

# ======================================================
# SWAGGER CONFIG (Swagger 2.0 - includes tags)
# ======================================================
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Auth & Face API (Flask) - Full",
        "description": "Feature-parity with your FastAPI app. Enums shown as scrollable dropdowns in /workeridentity/update and /identitymanagement/update.",
        "version": "1.0.0"
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header. Example: 'Bearer <token>'"
        }
    },
    "security": [{"Bearer": []}],
    "tags": [
        {"name": "auth", "description": "Authentication endpoints"},
        {"name": "worker", "description": "Worker / identity endpoints"},
        {"name": "face", "description": "Face data endpoints"}
    ]
}
swagger_config = {
    "headers": [],
    "specs": [
        {"endpoint": "apispec_1", "route": "/apispec_1.json", "rule_filter": lambda rule: True, "model_filter": lambda tag: True}
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/"
}
Swagger(app, template=swagger_template, config=swagger_config)

# ======================================================
# DATABASE
# ======================================================
def connect_db():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
        connect_timeout=5
    )

# Safe dynamic badge enum loader (non-blocking)
# def load_badge_enum():
#     try:
#         db = connect_db(); cur = db.cursor()
#         cur.execute("SELECT BadgeID FROM WorkerIdentity")
#         badge_ids = [r["BadgeID"] for r in cur.fetchall()]
#         cur.close(); db.close()
#     except Exception as e:
#         logging.warning(f"load_badge_enum failed: {e}")
#         badge_ids = []
#     if not badge_ids:
#         badge_ids = ["B0000"]
#     return Enum("BadgeEnum", {bid: bid for bid in badge_ids})

# BadgeEnum = load_badge_enum()

# ======================================================
# AUTH / JWT HELPERS
# ======================================================
def verify_password(plain: str, hashed: str) -> bool:
    return pwd_ctx.verify(plain, hashed)

def hash_password(password: str) -> str:
    return pwd_ctx.hash(password)

def create_token(data: dict, expires: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

def decode_token(token: str) -> dict:
    try:
        return jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except jwt.ExpiredSignatureError:
        raise Exception("Token expired")
    except jwt.InvalidTokenError:
        raise Exception("Invalid token")

# ======================================================
# DB helpers
# ======================================================
def get_user(username: str):
    db = connect_db(); cur = db.cursor()
    cur.execute("""
        SELECT U.username, U.BadgeID, U.hashed_password, U.disabled, W.PersonName
        FROM Users U
        LEFT JOIN WorkerIdentity W USING (BadgeID)
        WHERE U.username = %s
    """, (username,))
    r = cur.fetchone()
    cur.close(); db.close()
    return r

def get_access_level(badgeID: str):
    db = connect_db(); cur = db.cursor()
    cur.execute("""
        SELECT WI.accesslevel
        FROM WorkerIdentity WI
        LEFT JOIN WorkerIdentity W USING (BadgeID)
        WHERE WI.badgeid = %s
    """, (badgeID,))
    r = cur.fetchone()
    cur.close(); db.close()
    return r

def get_worker_by_badge(badgeID: str):
    db = connect_db(); cur = db.cursor()
    cur.execute("""
        SELECT W.PersonName
        FROM WorkerIdentity W
        JOIN IdentityManagement I USING (BadgeID)
        WHERE W.BadgeID = %s
    """, (badgeID,))
    r = cur.fetchone()
    cur.close(); db.close()
    return r

# ======================================================
# DECORATORS: require_auth / require_admin
# ======================================================
def require_auth(func):
    @wraps(func)
    def wrapper(*args, **kwargs):
        auth = request.headers.get("Authorization", "")
        if not auth.startswith("Bearer "):
            return jsonify({"detail": "Missing or invalid Authorization header"}), 401
        token = auth.split(" ", 1)[1]
        try:
            payload = decode_token(token)
            username = payload.get("sub")
            if not username:
                return jsonify({"detail": "Invalid token payload"}), 401
            user = get_user(username)
            if not user:
                return jsonify({"detail": "User not found"}), 401
            request.user = user # type: ignore
        except Exception as e:
            return jsonify({"detail": str(e)}), 401
        return func(*args, **kwargs)
    return wrapper

# UPDATED: Explicitly fetches role from DB
def require_admin(func):
    @wraps(func)
    @require_auth
    def wrapper(*args, **kwargs):
        user = request.user
        badgeID = user.get("BadgeID")

        # B0000 is always considered SuperAdmin/Admin
        if badgeID == "B0000":
            return func(*args, **kwargs)

        # Explicit check against WorkerIdentity
        db = connect_db(); cur = db.cursor()
        try:
            cur.execute("SELECT AccessLevel FROM WorkerIdentity WHERE BadgeID = %s", (badgeID,))
            row = cur.fetchone()
            access = row["AccessLevel"] if row else None
        finally:
            cur.close(); db.close()

        if access not in ["Admin", "SuperAdmin"]:
            return jsonify({"detail": "Admin privileges required"}), 403

        return func(*args, **kwargs)
    return wrapper

# UPDATED: Explicitly fetches role from DB
def require_super_admin(func):
    @wraps(func)
    @require_auth
    def wrapper(*args, **kwargs):
        user = request.user
        badgeID = user.get("BadgeID")

        if badgeID == "B0000":
             return func(*args, **kwargs)

        # Explicit check against WorkerIdentity
        db = connect_db(); cur = db.cursor()
        try:
            cur.execute("SELECT AccessLevel FROM WorkerIdentity WHERE BadgeID = %s", (badgeID,))
            row = cur.fetchone()
            access = row["AccessLevel"] if row else None
        finally:
            cur.close(); db.close()

        if access != "SuperAdmin":
            return jsonify({"detail": "SuperAdmin privileges required"}), 403

        return func(*args, **kwargs)
    return wrapper
# ======================================================
# UTILITIES
# ======================================================
_last_touch_time = 0
def touch_pkltimestamp_debounced():
    global _last_touch_time
    now = time.time()
    if now - _last_touch_time < 2:
        return
    _last_touch_time = now
    PKL_TIMESTAMP_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(PKL_TIMESTAMP_FILE, "w") as f:
        f.write(datetime.utcnow().isoformat())
        f.flush()
    logging.info("pkltimestamp updated")

def _normalize_for_compare(name: str) -> str:
    return name.strip().lower().replace(" ", "_")

def resolve_person_folder(person_name: str) -> Path:
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
            import shutil
            shutil.rmtree(folder_path)
            logging.info(f"Deleted face data folder: {folder_path}")
            touch_pkltimestamp_debounced()
            return True
        return False
    except Exception as e:
        logging.error(f"Failed to delete face data for {person_name}: {e}")
        return False
# ======================================================
# ROUTES
# ======================================================

@app.route("/", methods=["GET"])
def health():
    """Health check"""
    return jsonify({"status": "Auth service running"})

# ---------- AUTH ----------
@app.route("/token", methods=["POST"])
@swag_from({
    "tags": ["auth"],
    "summary": "Login and generate JWT token",
    "consumes": ["application/x-www-form-urlencoded"],
    "produces": ["application/json"],
    "parameters": [
        {"name": "username", "in": "formData", "type": "string", "required": True},
        {"name": "password", "in": "formData", "type": "string", "required": True}
    ],
    "responses": {
        200: {
            "description": "Successful login",
            "schema": {
                "type": "object",
                "properties": {
                    "access_token": {"type": "string"},
                    "token_type": {"type": "string"},
                    "badgeID": {"type": "string"},
                    "username": {"type": "string"}
                }
            }
        },
        400: {"description": "Missing username or password"},
        401: {"description": "Bad username or password"}
    }
})
def login():
    username = request.form.get("username")
    password = request.form.get("password")
    # print("username:", username)
    # print("password:", password)
    if not username or not password:
        return jsonify({"detail": "username and password required"}), 400


    user = get_user(username)
    # print("user:", user)

    if not user or not verify_password(password, user["hashed_password"]) or user.get("disabled"):
        return jsonify({"detail": "Bad username or password"}), 401
    badgeID=user.get("BadgeID")

    # print("user:", get_access_level(badgeID)["accesslevel"])
    access_level=get_access_level(badgeID)["accesslevel"] # type: ignore

    if access_level not in ["Admin", "SuperAdmin"] and user.get("BadgeID") != "B0000":
        return jsonify({"detail": "Access Denied: Only Admin or SuperAdmin can access the dashboard."}), 403

    token = create_token({"sub": user["username"]})
    # print("token:", token, type(token))

    return jsonify({
        "access_token": token,
        "token_type": "bearer",
        "badgeID": user["BadgeID"],
        "username": user["username"],
        "role": user.get("AccessLevel", "Admin") # Return role for frontend logic
    })

@app.route("/signup", methods=["POST"])
@swag_from({
    "tags": ["auth"],
    "summary": "Register a new user (account only)",
    "description": "Auto-creates a worker profile if the Badge ID does not exist.",
    "parameters": [
        {"name": "username", "in": "formData", "type": "string", "required": True},
        {"name": "password", "in": "formData", "type": "string", "required": True},
        {"name": "badgeID", "in": "formData", "type": "string", "required": False},
        {"name": "PersonName", "in": "formData", "type": "string", "required": True},
        {"name": "Position", "in": "formData", "type": "string", "required": True},
        {"name": "Department", "in": "formData", "type": "string", "required": True},
        {"name": "Company", "in": "formData", "type": "string", "required": True},
        {"name": "AccessLevel", "in": "formData", "type": "string", "required": True},
        {"name": "EMail", "in": "formData", "type": "string", "required": True},
        {"name": "Phone", "in": "formData", "type": "string", "required": True}
    ],
    "responses": {200: {"description": "User account created"}, 409: {"description": "Username already exists"}}
})
def signup():
    username = request.form.get("username")
    password = request.form.get("password")
    # BadgeID must be explicitly provided and validated against WorkerIdentity
    badgeID = request.form.get("badgeID")
    person_name = request.form.get("PersonName")
    position = request.form.get("Position")
    department = request.form.get("Department")
    company = request.form.get("Company")
    access_level = request.form.get("AccessLevel")
    email = request.form.get("EMail")
    phone = request.form.get("Phone")

    if not username or not password:
        return jsonify({"detail": "Username and password are required"}), 4000

    db = connect_db(); cur = db.cursor()
    try:
        # 1. Check if Username is taken
        cur.execute("SELECT username FROM Users WHERE username = %s", (username,))
        if cur.fetchone():
            return jsonify({"detail": f"Username '{username}' already exists"}), 409

        # ---------------------------------------------------------------
        # 2. AUTO-GENERATE BADGE ID IF NOT PROVIDED
        # ---------------------------------------------------------------
        if not badgeID:
            cur.execute("""
                            SELECT BadgeID
                            FROM WorkerIdentity
                            WHERE BadgeID LIKE 'B%%%%'
                            ORDER BY BadgeID DESC
                            LIMIT 1
                        """)
            row = cur.fetchone()

            if row:
                last_badge = row["BadgeID"]          # e.g., "B0023"
                num = int(last_badge[1:])    # -> 23
                new_num = num + 1            # -> 24
                badgeID = f"B{new_num:04d}"  # -> "B0024"
            else:
                badgeID = "B0001"            # Table empty → first ID

        # 2. Check if Account already exists for this Badge
        cur.execute("SELECT BadgeID FROM Users WHERE BadgeID = %s", (badgeID,))
        if cur.fetchone():
            return jsonify({"detail": f"An account is already registered for Badge ID '{badgeID}'"}), 409

        # 3. FIX: Check if WorkerIdentity exists. If NOT, create a placeholder.
        cur.execute("SELECT BadgeID FROM WorkerIdentity WHERE BadgeID = %s", (badgeID,))
        if not cur.fetchone():
            logging.info(f"BadgeID {badgeID} not found. Auto-creating System User profile.")
            # Create base worker record to satisfy Foreign Key
            cur.execute("""
                INSERT INTO WorkerIdentity
                (PersonName, BadgeID, Position, Department, Company, AccessLevel, EMail, Phone, Status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Active')
                """, (person_name,badgeID,position,department,company,access_level,email,phone))

        # 4. Create the User Account
        hashed_password = hash_password(password)
        cur.execute("""
            INSERT INTO Users (username, BadgeID, hashed_password, disabled)
            VALUES (%s, %s, %s, %s)
        """, (username, badgeID, hashed_password, False))

        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"User signup failed: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

    return jsonify({"msg": "User account created successfully", "username": username, "badgeID": badgeID})

@app.route("/me", methods=["GET"])
@swag_from({
    "tags": ["auth"],
    "summary": "Get current user info",
    "security": [{"Bearer": []}]
})
@require_auth
def read_me():
    u = request.user  # user from 'users' table
    badge_id = u["BadgeID"]

    # Connect to DB and fetch AccessLevel from workeridentity
    try:
        db = connect_db(); cur = db.cursor()

        # Fetch worker info
        cur.execute("SELECT AccessLevel, PersonName FROM workeridentity WHERE BadgeID = %s", (badge_id,))
        worker = cur.fetchone()

        if worker is None:
            # fallback if badgeID not found in workeridentity
            access_level = "Admin"
            person_name = u.get("PersonName", "")
        else:
            access_level = worker.get("AccessLevel", "Admin")
            # Use PersonName from workeridentity if exists
            person_name = worker.get("PersonName", u.get("PersonName", ""))

    finally:
        cur.close()
        db.close()
    return jsonify({
        "username": u["username"],
        "badgeID": badge_id,
        "person_name": person_name,
        "role": access_level,          # ✅ Correct AccessLevel from workeridentity
        "disabled": u.get("disabled", False)
    })
# @app.route("/password", methods=["POST"])
# @swag_from({
#     "tags": ["auth"],
#     "summary": "Change password",
#     "parameters": [
#         {"name": "old_password", "in": "formData", "type": "string", "required": True},
#         {"name": "new_password", "in": "formData", "type": "string", "required": True}
#     ],
#     "security": [{"Bearer": []}]
# })
# def change_password():
#     old = request.form.get("old_password")
#     new = request.form.get("new_password")
#     if not old or not new:
#         return jsonify({"detail": "old_password and new_password required"}), 400
#     current = request.user
#     if not verify_password(old, current["hashed_password"]):
#         return jsonify({"detail": "Old password is incorrect"}), 400
#     new_hash = hash_password(new)
#     db = connect_db(); cur = db.cursor()
#     try:
#         cur.execute("UPDATE Users SET hashed_password=%s WHERE username=%s", (new_hash, current["username"]))
#         db.commit()
#     except pymysql.MySQLError as e:
#         db.rollback()
#         return jsonify({"detail": str(e)}), 500
#     finally:
#         cur.close(); db.close()
#     return jsonify({"msg": "Password changed"})

# ---------- IDENTITY MANAGEMENT (Read/Delete) ----------

@app.route("/workers", methods=["GET"])
@swag_from({
    "tags": ["worker"],
    "summary": "Get list of all workers with identity and certificate data",
    "responses": {200: {"description": "List of workers"}},
    "security": [{"Bearer": []}]
})
@require_admin
def get_all_workers():
    db = connect_db(); cur = db.cursor()
    try:
        cur.execute("""
         SELECT
                WI.*,
                IM.Certificate1, IM.Certificate2, IM.Certificate3, IM.Certificate4
            FROM WorkerIdentity WI
            LEFT JOIN IdentityManagement IM ON WI.BadgeID = IM.BadgeID
            ORDER BY WI.PersonName
        """)
        workers = cur.fetchall()
        return jsonify(workers)
    except pymysql.MySQLError as e:
         return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

@app.route("/worker/<badgeID>", methods=["GET"])
@swag_from({
    "tags": ["worker"],
    "summary": "Get details for a single worker",
    "parameters": [{"name": "badgeID", "in": "path", "type": "string", "required": True}],
    "responses": {200: {"description": "Worker details"}, 404: {"description": "Worker not found"}},
    "security": [{"Bearer": []}]
})
@require_admin
def get_worker(badgeID):
    db = connect_db(); cur = db.cursor()
    try:
        cur.execute("""
            SELECT
                WI.*,
                IM.Certificate1, IM.Certificate2, IM.Certificate3, IM.Certificate4
            FROM WorkerIdentity WI
             LEFT JOIN IdentityManagement IM ON WI.BadgeID = IM.BadgeID
             WHERE WI.BadgeID = %s
         """, (badgeID,))
        worker = cur.fetchone()
        if not worker:
            return jsonify({"detail": "Worker not found"}), 404
        return jsonify(worker)
    except pymysql.MySQLError as e:
         return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
         cur.close(); db.close()

@app.route("/worker/delete/<badgeID>", methods=["DELETE"])
@swag_from({
     "tags": ["worker"],
    "summary": "Permanently delete a worker's identity and face data",
    "parameters": [{"name": "badgeID", "in": "path", "type": "string", "required": True}],
     "responses": {200: {"description": "Worker deleted"}, 404: {"description": "Worker not found"}},
     "security": [{"Bearer": []}]
})
@require_super_admin
def delete_worker(badgeID):
    db = connect_db(); cur = db.cursor()
    try:
        # 1. Get the worker name for file system deletion
        cur.execute("SELECT PersonName FROM WorkerIdentity WHERE BadgeID = %s", (badgeID,))
        worker_info = cur.fetchone()

        if not worker_info:
            return jsonify({"detail": f"Worker with BadgeID {badgeID} not found"}), 404

        person_name = worker_info['PersonName']

        # 2. Delete DB records in transactional order
        cur.execute("DELETE FROM IdentityManagement WHERE BadgeID = %s", (badgeID,))
        cur.execute("DELETE FROM users WHERE BadgeID = %s", (badgeID,))
        cur.execute("DELETE FROM WorkerIdentity WHERE BadgeID = %s", (badgeID,))

         # 3. Delete face data (use utility function)
        delete_face_data(person_name)

        db.commit()

        return jsonify({"msg": f"Worker {person_name} ({badgeID}) and associated data deleted."})

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Worker deletion failed: {e}")
        return jsonify({"detail": f"Database error during deletion: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ---------- WORKER IDENTITY ----------
@app.route("/workeridentity/update", methods=["PUT"])
@swag_from({
    "tags": ["worker"],
    "summary": "Upsert WorkerIdentity (Admin only)",
    "parameters": [
        {"name": "person_name", "in": "formData", "type": "string", "required": True},
        {"name": "badgeID", "in": "formData", "type": "string", "required": True},
        {"name": "position", "in": "formData", "type": "string", "required": True},
        {"name": "department", "in": "formData", "type": "string", "required": True},
        {"name": "company", "in": "formData", "type": "string", "required": True},
        {"name": "access_level", "in": "formData", "type": "string", "enum": ACCESS_LEVEL_VALUES, "required": True},
        {"name": "email", "in": "formData", "type": "string", "required": True},
        {"name": "phone", "in": "formData", "type": "string", "required": True},
        {"name": "status", "in": "formData", "type": "string", "enum": STATUS_VALUES, "required": True}
    ],
    "security": [{"Bearer": []}]
})
@require_admin
def update_workeridentity():
    form = request.form
    person_name = form.get("person_name")
    badgeID = form.get("badgeID")
    position = form.get("position")
    department = form.get("department")
    company = form.get("company")
    access_level = form.get("access_level")
    email = form.get("email")
    phone = form.get("phone")
    status = form.get("status")
    if not person_name or not badgeID:
        return jsonify({"detail": "person_name and badgeID required"}), 400

    db = connect_db(); cur = db.cursor()
    try:
        badge = badgeID.strip()
        cur.execute("SELECT * FROM WorkerIdentity WHERE BadgeID = %s", (badge,))
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE WorkerIdentity
                SET PersonName=%s, Position=%s, Department=%s, Company=%s,
                    AccessLevel=%s, EMail=%s, Phone=%s, Status=%s
                WHERE BadgeID=%s
            """, (person_name, position, department, company, access_level, email, phone, status, badge))
        else:
            cur.execute("""
                INSERT INTO WorkerIdentity
                (PersonName, BadgeID, Position, Department, Company, AccessLevel, EMail, Phone, Status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (person_name, badge, position, department, company, access_level, email, phone, status))
            folder_path = resolve_person_folder(person_name)
            folder_path.mkdir(parents=True, exist_ok=True)
            logging.info(f"Auto-created face folder: {folder_path}")
        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()
    return jsonify({"msg": "WorkerIdentity upserted", "badgeID": badge})

# ---------- IDENTITY MANAGEMENT ----------
@app.route("/identitymanagement/update", methods=["PUT"])
@require_admin
def update_identitymanagement():
    form = request.form
    badgeID = form.get("badgeID")
    if not badgeID:
        return jsonify({"detail": "badgeID required"}), 400

    badge = badgeID.strip()

    # Only update certificates if BadgeID doesn't start with 'B'
    if not badge.startswith("B"):
        c1y, c1m, c1d = form.get("certificate1_year"), form.get("certificate1_month"), form.get("certificate1_day")
        c3y, c3m, c3d = form.get("certificate3_year"), form.get("certificate3_month"), form.get("certificate3_day")
        certificate2 = form.get("certificate2")
        certificate4 = form.get("certificate4")

        cert1 = f"{c1y}-{c1m}-{c1d}" if c1y and c1m and c1d else None
        cert3 = f"{c3y}-{c3m}-{c3d}" if c3y and c3m and c3d else None

        db = connect_db(); cur = db.cursor()
        try:
            cur.execute("SELECT * FROM IdentityManagement WHERE BadgeID = %s", (badge,))
            existing = cur.fetchone()
            if existing:
                cur.execute("""
                    UPDATE IdentityManagement
                    SET Certificate1=%s, Certificate2=%s, Certificate3=%s, Certificate4=%s
                    WHERE BadgeID=%s
                """, (cert1, certificate2, cert3, certificate4, badge))
            else:
                cur.execute("SELECT PersonName FROM WorkerIdentity WHERE BadgeID = %s LIMIT 1", (badge,))
                w = cur.fetchone()
                pname = w["PersonName"] if w else None
                cur.execute("""
                    INSERT INTO IdentityManagement (PersonName, BadgeID, Certificate1, Certificate2, Certificate3, Certificate4)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (pname, badge, cert1, certificate2, cert3, certificate4))
            db.commit()
        except pymysql.MySQLError as e:
            db.rollback()
            return jsonify({"detail": str(e)}), 500
        finally:
            cur.close(); db.close()
    else:
        # Skip certificate update for Admin/SuperAdmin
        logging.info(f"Skipping IdentityManagement update for BadgeID: {badge} (Admin/SuperAdmin)")

    return jsonify({"msg": "IdentityManagement upserted (if applicable)", "badgeID": badge})




# ---------- EMPLOYEE REGISTRATION ----------
@app.route("/employee/register", methods=["POST"])
@swag_from({
    "tags": ["worker"],
    "summary": "Register a new Employee (Admin only)",
    "description": "Creates entries in WorkerIdentity, IdentityManagement, and Users tables.",
    "parameters": [
        # WorkerIdentity Parameters
        {"name": "person_name", "in": "formData", "type": "string", "required": True, "description": "Full name of the employee."},
        {"name": "badgeID", "in": "formData", "type": "string", "required": True, "description": "Unique badge ID (e.g., E1234)."},
        {"name": "position", "in": "formData", "type": "string", "required": True},
        {"name": "department", "in": "formData", "type": "string", "required": True},
        {"name": "company", "in": "formData", "type": "string", "required": True},
        {"name": "email", "in": "formData", "type": "string", "required": True},
        {"name": "phone", "in": "formData", "type": "string", "required": True},
        {"name": "files", "in": "formData", "type": "file", "required": True, "collectionFormat": "multi", "description": "Multiple face images for the employee."},
        # IdentityManagement/Certificate Parameters (Using defaults/0 for a new user)
        {"name": "certificate1_year", "in": "formData", "type": "string", "enum": YEAR_VALUES, "required": False, "default": "2035"},
        {"name": "certificate1_month", "in": "formData", "type": "string", "enum": MONTH_VALUES, "required": False, "default": "12"},
        {"name": "certificate1_day", "in": "formData", "type": "string", "enum": DAY_VALUES, "required": False, "default": "31"},
        {"name": "certificate2", "in": "formData", "type": "string", "enum": CERTBOOL_VALUES, "required": False, "default": "0"},
        {"name": "certificate3_year", "in": "formData", "type": "string", "enum": YEAR_VALUES, "required": False, "default": "2035"},
        {"name": "certificate3_month", "in": "formData", "type": "string", "enum": MONTH_VALUES, "required": False, "default": "12"},
        {"name": "certificate3_day", "in": "formData", "type": "string", "enum": DAY_VALUES, "required": False, "default": "31"},
        {"name": "certificate4", "in": "formData", "type": "string", "enum": CERTBOOL_VALUES, "required": False, "default": "0"},
        # Users Table Parameters
        # {"name": "username", "in": "formData", "type": "string", "required": True, "description": "Username for login."},
        # {"name": "password", "in": "formData", "type": "string", "required": True, "description": "Default password for the user."}
    ],
    "responses": {
        200: {"description": "Employee registered successfully"},
        400: {"description": "Invalid input"},
        409: {"description": "BadgeID or Username already exists"},
        403: {"description": "Admin privileges required"}
    },
    "security": [{"Bearer": []}]
})
@require_admin
def register_employee():
    form = request.form
    files = request.files
    # WorkerIdentity Fields
    person_name = form.get("person_name")
    badgeID = form.get("badgeID")
    position = form.get("position")
    department = form.get("department")
    company = form.get("company")
    email = form.get("email")
    phone = form.get("phone")
    access_level = AccessLevel.Employee.value # Force Employee for this route
    status = StatusEnum.Active.value # Force Active for new registration

    # IdentityManagement Fields (Use defaults if not provided, for simplicity)
    c1y = form.get("certificate1_year", "2035"); c1m = form.get("certificate1_month", "12"); c1d = form.get("certificate1_day", "31")
    certificate2 = form.get("certificate2", "0")
    c3y = form.get("certificate3_year", "2035"); c3m = form.get("certificate3_month", "12"); c3d = form.get("certificate3_day", "31")
    certificate4 = form.get("certificate4", "0")
    cert1 = f"{c1y}-{c1m}-{c1d}"
    cert3 = f"{c3y}-{c3m}-{c3d}"

    # Users Fields
    # username = form.get("username")
    # password = form.get("password")

    required_fields = {
        "person_name": person_name, "badgeID": badgeID, "position": position, "department": department,
        "company": company, "email": email, "phone": phone#, "username": username, "password": password
    }

    if not all(required_fields.values()):
        missing = [k for k, v in required_fields.items() if not v]
        return jsonify({"detail": f"Missing required fields: {', '.join(missing)}"}), 400

    file_list = request.files.getlist('files')

    # Check for required files
    if not file_list or not any(f.filename for f in file_list):
        return jsonify({"detail": "At least one face image file is required."}), 400

    db = connect_db(); cur = db.cursor()
    try:
        # 1. Check for existing BadgeID
        cur.execute("SELECT BadgeID FROM WorkerIdentity WHERE BadgeID = %s", (badgeID,))
        if cur.fetchone():
            return jsonify({"detail": f"BadgeID '{badgeID}' already exists"}), 409

        # 2. Check for existing Username
        # cur.execute("SELECT person_name FROM Users WHERE person_name = %s", (person_name,))
        # if cur.fetchone():
        #     return jsonify({"detail": f"person_name '{person_name}' already exists"}), 409

        # 3. Insert into WorkerIdentity
        cur.execute("""
            INSERT INTO WorkerIdentity
            (PersonName, BadgeID, Position, Department, Company, AccessLevel, EMail, Phone, Status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (person_name, badgeID, position, department, company, access_level, email, phone, status))

        # 4. Insert into IdentityManagement
        cur.execute("""
            INSERT INTO IdentityManagement (PersonName, BadgeID, Certificate1, Certificate2, Certificate3, Certificate4)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (person_name, badgeID, cert1, certificate2, cert3, certificate4))

        # 5. Insert into Users
        # hashed_password = hash_password(password)
        # cur.execute("""
        #     INSERT INTO Users (username, BadgeID, hashed_password, disabled)
        #     VALUES (%s, %s, %s, %s)
        # """, (username, badgeID, hashed_password, False))

        # 6. Create face data folder and update pkl timestamp
        folder_path = resolve_person_folder(person_name) # type: ignore
        folder_path.mkdir(parents=True, exist_ok=True)

        saved_files = []
        for f in file_list:
            if not f or not f.filename:
                continue

            filename = f.filename.replace('/', '_').replace('\\', '_')
            dest = folder_path / filename
            f.save(dest)
            saved_files.append(filename)

        if not saved_files:
            raise Exception("Registration failed: No valid files were saved.")

        logging.info(f"Auto-created face folder: {folder_path} for new employee {person_name}")
        touch_pkltimestamp_debounced() # Notify face recognition service to reload data

        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Employee registration failed: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    except Exception as e:
        db.rollback()
        logging.error(f"File handling error: {e}")
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()

    return jsonify({
        "msg": "Employee and face data successfully registered",
        "badgeID": badgeID,
        "person_name": person_name,
        "images_saved": saved_files})


# ---------- FACE UPLOAD ----------
@app.route("/face/upload_images", methods=["POST"])
@swag_from({
    "tags": ["face"],
    "summary": "Upload multiple face images for user (Admin only)",
    "parameters": [
        {"name": "badgeID", "in": "formData", "type": "string", "required": True},
        {"name": "files", "in": "formData", "type": "file", "required": True, "collectionFormat": "multi"}
    ],
    "security": [{"Bearer": []}]
})
@require_admin
def upload_images():
    badgeID = request.form.get("badgeID")
    if not badgeID:
        return jsonify({"detail": "badgeID required"}), 400

    db = connect_db(); cur = db.cursor()
    try:
        cur.execute("""
            SELECT W.PersonName
              FROM WorkerIdentity W
              JOIN IdentityManagement I USING (BadgeID)
             WHERE W.BadgeID = %s
        """, (badgeID,))
        row = cur.fetchone()
        if not row:
            return jsonify({"detail": "BadgeID not found"}), 400
        person_name = row["PersonName"]
    finally:
        cur.close(); db.close()

    folder_path = resolve_person_folder(person_name)
    folder_path.mkdir(parents=True, exist_ok=True)

    saved_files = []
    file_list = request.files.getlist('files')
    for f in file_list:
        if not f or not f.filename:
            continue

        dest = folder_path / f.filename
        f.save(dest)
        saved_files.append(f.filename)

    touch_pkltimestamp_debounced()
    return jsonify({"msg": f"{len(saved_files)} images uploaded", "badgeID": badgeID, "files": saved_files})
# ======================================================
# DB CONNECTION TEST (Temporary)
# ======================================================
def test_db_connection():
    logging.info("Attempting database connection test...")
    db = None
    try:
        db = connect_db()
        # Test a simple query
        cur = db.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        if result and list(result.values())[0] == 1:
            logging.info("✅ Database connection successful and basic query executed.")
        else:
            logging.error("❌ Database test query failed.")
        cur.close()
    except pymysql.err.OperationalError as e:
        logging.error(f"❌ Database connection failed: {e}. Check host, user, and password in DB_CONFIG.")
    except Exception as e:
        logging.error(f"❌ An unexpected error occurred during DB test: {e}")
    finally:
        if db:
            db.close()
# ======================================================
# MAIN
# ======================================================
if __name__ == "__main__":
    test_db_connection()
    app.run(host="127.0.0.1", port=8000, debug=True)
