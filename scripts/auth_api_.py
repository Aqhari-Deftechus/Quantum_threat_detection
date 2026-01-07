import os
import time
import logging
from datetime import datetime, timedelta
from pathlib import Path
from enum import Enum
from typing import List

import pymysql
from fastapi import FastAPI, HTTPException, Depends, status, Request, UploadFile, File, Form
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from jose import JWTError, jwt
from passlib.context import CryptContext
from pydantic import BaseModel

# ======================================================
# CONFIGURATION
# ======================================================
DB_CONFIG = {
    "host": "localhost",
    "user": "admin123",
    "password": "Petro@123",
    "database": "RestrictedAreaDB"
}

SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_TO_A_RANDOM_SECRET")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60

BASE_DIR = Path(__file__).resolve().parent
FACE_DATA_DIR = BASE_DIR.parent / "face_data"
PKL_TIMESTAMP_FILE = BASE_DIR / "pkltimestamp"

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

app = FastAPI()
pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
oauth2 = OAuth2PasswordBearer(tokenUrl="token")

# ======================================================
# ENUM DEFINITIONS
# ======================================================
class AccessLevel(str, Enum):
    Visitor = "Visitor"
    Employee = "Employee"
    Contractor = "Contractor"
    Admin = "Admin"

class StatusEnum(str, Enum):
    Active = "Active"
    Inactive = "Inactive"

class CertBool(str, Enum):
    None_ = "0"
    Yes = "1"

class YearEnum(str, Enum):
    _2015 = "2015"
    _2016 = "2016"
    _2017 = "2017"
    _2018 = "2018"
    _2019 = "2019"
    _2020 = "2020"
    _2021 = "2021"
    _2022 = "2022"
    _2023 = "2023"
    _2024 = "2024"
    _2025 = "2025"
    _2026 = "2026"
    _2027 = "2027"
    _2028 = "2028"
    _2029 = "2029"
    _2030 = "2030"
    _2031 = "2031"
    _2032 = "2032"
    _2033 = "2033"
    _2034 = "2034"
    _2035 = "2035"

class MonthEnum(str, Enum):
    Jan = "01"
    Feb = "02"
    Mar = "03"
    Apr = "04"
    May = "05"
    Jun = "06"
    Jul = "07"
    Aug = "08"
    Sep = "09"
    Oct = "10"
    Nov = "11"
    Dec = "12"

class DayEnum(str, Enum):
    _01 = "01"
    _02 = "02"
    _03 = "03"
    _04 = "04"
    _05 = "05"
    _06 = "06"
    _07 = "07"
    _08 = "08"
    _09 = "09"
    _10 = "10"
    _11 = "11"
    _12 = "12"
    _13 = "13"
    _14 = "14"
    _15 = "15"
    _16 = "16"
    _17 = "17"
    _18 = "18"
    _19 = "19"
    _20 = "20"
    _21 = "21"
    _22 = "22"
    _23 = "23"
    _24 = "24"
    _25 = "25"
    _26 = "26"
    _27 = "27"
    _28 = "28"
    _29 = "29"
    _30 = "30"
    _31 = "31"

# ======================================================
# DATABASE CONNECTION
# ======================================================
def connect_db():
    return pymysql.connect(
        host=DB_CONFIG["host"],
        user=DB_CONFIG["user"],
        password=DB_CONFIG["password"],
        database=DB_CONFIG["database"],
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False
    )

# ======================================================
# DYNAMIC ENUM LOADER
# ======================================================
def load_badge_enum() -> Enum:
    db = connect_db()
    cur = db.cursor()
    cur.execute("SELECT BadgeID FROM WorkerIdentity")
    badge_ids = [row["BadgeID"] for row in cur.fetchall()]
    cur.close(); db.close()
    if not badge_ids:
        badge_ids = ["B0000"]
    return Enum("BadgeEnum", {bid: bid for bid in badge_ids})

BadgeEnum = load_badge_enum()

# ======================================================
# MODELS
# ======================================================
class Token(BaseModel):
    access_token: str
    token_type: str
    badgeID: str

class UserBase(BaseModel):
    username: str
    badgeID: str
    person_name: str
    disabled: bool

class UserInDB(UserBase):
    hashed_password: str

class ChangePasswordRequest(BaseModel):
    old_password: str
    new_password: str

# ======================================================
# AUTH UTILITIES
# ======================================================
def verify_password(plain, hashed) -> bool:
    return pwd_ctx.verify(plain, hashed)

def hash_password(password) -> str:
    return pwd_ctx.hash(password)

def get_user(username: str) -> UserInDB | None:
    db = connect_db()
    cur = db.cursor()
    cur.execute("""
        SELECT U.username, U.BadgeID, U.hashed_password, U.disabled, W.PersonName
        FROM Users U
        LEFT JOIN WorkerIdentity W USING (BadgeID)
        WHERE U.username = %s
    """, (username,))
    row = cur.fetchone()
    cur.close(); db.close()

    if not row:
        return None

    # FIX: Rename DB fields to match Pydantic model
    user_data = {
        "username": row["username"],
        "badgeID": row["BadgeID"],          # map BadgeID → badgeID
        "person_name": row["PersonName"],   # map PersonName → person_name
        "disabled": bool(row["disabled"]),
        "hashed_password": row["hashed_password"]
    }

    return UserInDB(**user_data)


def authenticate(username: str, password: str) -> UserInDB | None:
    user = get_user(username)
    if not user or not verify_password(password, user.hashed_password):
        return None
    if user.disabled:
        return None
    return user

def create_token(data: dict, expires: timedelta | None = None) -> str:
    to_encode = data.copy()
    expire = datetime.utcnow() + (expires or timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES))
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)

async def require_user(token: str = Depends(oauth2)) -> UserInDB:
    creds_exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid authentication credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
        username: str = payload.get("sub")
        if not username:
            raise creds_exc
    except JWTError:
        raise creds_exc
    user = get_user(username)
    if not user:
        raise creds_exc
    return user

def require_admin(current: UserInDB = Depends(require_user)) -> UserInDB:
    if current.badgeID != "B0000":
        raise HTTPException(status_code=403, detail="Admin privileges required")
    return current

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
    logging.info(f"pkltimestamp updated at {datetime.utcnow().isoformat()}")

def _normalize_for_compare(name: str) -> str:
    return name.strip().lower().replace(" ", "_")

def resolve_person_folder(person_name: str) -> Path:
    normalized_target = _normalize_for_compare(person_name)
    for existing in FACE_DATA_DIR.iterdir():
        if existing.is_dir() and _normalize_for_compare(existing.name) == normalized_target:
            return existing
    return FACE_DATA_DIR / person_name

# ======================================================
# ROUTES
# ======================================================
@app.get("/")
def health():
    return {"status": "Auth service running"}

@app.post("/token", response_model=Token)
def login(form: OAuth2PasswordRequestForm = Depends()):
    user = authenticate(form.username, form.password)
    if not user:
        raise HTTPException(status_code=401, detail="Bad username or password", headers={"WWW-Authenticate": "Bearer"})
    token = create_token({"sub": user.username})
    return {"access_token": token, "token_type": "bearer", "badgeID": user.badgeID}

@app.get("/me", response_model=UserBase)
def read_me(current: UserInDB = Depends(require_user)):
    return current

@app.post("/password")
def change_password(req: ChangePasswordRequest, current: UserInDB = Depends(require_user)):
    if not verify_password(req.old_password, current.hashed_password):
        raise HTTPException(400, "Old password is incorrect")
    new_hash = hash_password(req.new_password)
    db = connect_db(); cur = db.cursor()
    try:
        cur.execute("UPDATE Users SET hashed_password=%s WHERE username=%s", (new_hash, current.username))
        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); db.close()
    return {"msg": "Password changed"}

# ======================================================
# WORKER IDENTITY MANAGEMENT
# ======================================================
@app.put("/workeridentity/update")
def update_workeridentity(
    person_name: str = Form(...),
    badgeID: str = Form(...),
    position: str = Form(...),
    department: str = Form(...),
    company: str = Form(...),
    access_level: AccessLevel = Form(...),
    email: str = Form(...),
    phone: str = Form(...),
    status: StatusEnum = Form(...),
    current: UserInDB = Depends(require_admin)
):
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
            """, (person_name, position, department, company, access_level.value, email, phone, status.value, badge))
        else:
            cur.execute("""
                INSERT INTO WorkerIdentity
                (PersonName, BadgeID, Position, Department, Company, AccessLevel, EMail, Phone, Status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (person_name, badge, position, department, company, access_level.value, email, phone, status.value))

            folder_path = resolve_person_folder(person_name)
            folder_path.mkdir(parents=True, exist_ok=True)
            logging.info(f"Auto-created face folder: {folder_path}")

        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); db.close()
    return {"msg": "WorkerIdentity upserted", "badgeID": badge}

# ======================================================
# IDENTITY MANAGEMENT
# ======================================================
@app.put("/identitymanagement/update")
def update_identitymanagement(
    badgeID: str = Form(...),
    certificate1_year: YearEnum = Form(...),
    certificate1_month: MonthEnum = Form(...),
    certificate1_day: DayEnum = Form(...),
    certificate2: CertBool = Form(...),
    certificate3_year: YearEnum = Form(...),
    certificate3_month: MonthEnum = Form(...),
    certificate3_day: DayEnum = Form(...),
    certificate4: CertBool = Form(...),
    current: UserInDB = Depends(require_admin)
):
    cert1 = f"{certificate1_year.value}-{certificate1_month.value}-{certificate1_day.value}"
    cert3 = f"{certificate3_year.value}-{certificate3_month.value}-{certificate3_day.value}"

    db = connect_db(); cur = db.cursor()
    try:
        badge = badgeID.strip()
        cur.execute("SELECT * FROM IdentityManagement WHERE BadgeID = %s", (badge,))
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE IdentityManagement
                SET Certificate1=%s, Certificate2=%s, Certificate3=%s, Certificate4=%s
                WHERE BadgeID=%s
            """, (cert1, certificate2.value, cert3, certificate4.value, badge))
        else:
            cur.execute("SELECT PersonName FROM WorkerIdentity WHERE BadgeID = %s LIMIT 1", (badge,))
            w = cur.fetchone()
            pname = w["PersonName"] if w else None
            cur.execute("""
                INSERT INTO IdentityManagement (PersonName, BadgeID, Certificate1, Certificate2, Certificate3, Certificate4)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (pname, badge, cert1, certificate2.value, cert3, certificate4.value))
        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
    finally:
        cur.close(); db.close()
    return {"msg": "IdentityManagement upserted", "badgeID": badge}

# ======================================================
# FACE UPLOAD
# ======================================================
@app.post("/face/upload_images")
def upload_images(
    badgeID: BadgeEnum = Form(...),
    files: List[UploadFile] = File(...),
    current: UserInDB = Depends(require_admin)
):
    badgeID = badgeID.value
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
            raise HTTPException(status_code=400, detail="BadgeID not found in WorkerIdentity/IdentityManagement")
        person_name = row["PersonName"]
    finally:
        cur.close(); db.close()

    folder_path = resolve_person_folder(person_name)
    folder_path.mkdir(parents=True, exist_ok=True)

    saved_files = []
    for file in files:
        dest = folder_path / file.filename
        with open(dest, "wb") as f:
            f.write(file.file.read())
        saved_files.append(file.filename)

    touch_pkltimestamp_debounced()
    return {"msg": f"{len(saved_files)} images uploaded", "badgeID": badgeID, "files": saved_files}

# ======================================================
# MAIN ENTRY POINT
# ======================================================
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("auth_api6:app", host="127.0.0.1", port=8000, reload=True)
