import logging
from fastapi import FastAPI

# Import apps from existing files
from auth_api6 import app as auth_app
from api2 import app as recognition_app

# --- Logging ---
logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# --- Main app ---
main_app = FastAPI(title="Inappropriate Behaviour Detection System")

# Mount both apps as sub-apps
main_app.mount("/auth", auth_app)           # Auth service routes will be under /auth
main_app.mount("/recognition", recognition_app)  # Recognition service routes under /recognition


@main_app.get("/")
def root():
    return {
        "status": "running",
        "services": {
            "auth": "/auth",
            "recognition": "/recognition"
        }
    }

# --- Run (for local debugging only) ---
if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:main_app", host="127.0.0.1", port=8000, reload=True)
