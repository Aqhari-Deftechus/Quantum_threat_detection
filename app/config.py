import os
from pathlib import Path

class Config:
    # Basic Flask Config
    SECRET_KEY = os.getenv("SECRET_KEY", "CHANGE_THIS_TO_A_RANDOM_SECRET")

    # Database Config
    DB_HOST = "localhost"
    DB_USER = "admin123"
    DB_PASSWORD = "Petro@123"
    DB_NAME = "RestrictedAreaDB"

    # Paths
    # We use .parent.parent to get out of the 'app' folder to the project root
    BASE_DIR = Path(__file__).resolve().parent.parent
    FACE_DATA_DIR = BASE_DIR / "face_data"
    PKL_TIMESTAMP_FILE = BASE_DIR / "pkltimestamp"

    # JWT Config
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60

    # VAPID_PRIVATE_KEY = "xzM-BZWCsjKBzPv-UUAs82jzRlixKg6Q1HUPhjOTadg"
    # VAPID_PUBLIC_KEY = "BCOmDMpiERjTmeUmsUImLkHj3ClhLHcJ6KTR4rq9MkMq1llf6zyfoTdeFaaatvfN88mo-4HFTI4XWgV9l6NA5CI"