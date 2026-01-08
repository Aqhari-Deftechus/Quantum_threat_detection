from flask import Blueprint, request, jsonify
from flasgger import swag_from  # type: ignore
import logging
from datetime import datetime
import traceback

# Import helpers from other modules
from app.decorators import require_auth, require_admin
from app.utils import (
    get_user_by_username,
    verify_password,
    hash_password,
    create_token,
    get_access_level,
    pwd_ctx,               # IMPORTANT: needed for needs_update()
)
from app.database import get_db_connection
from app.enums import AccessLevel, ACCESS_LEVEL_VALUES

# Define the Blueprint
auth_bp = Blueprint("Authentication", __name__)

# ---------- AUTH ----------

@auth_bp.route("/auth/login", methods=["POST"])
@swag_from({
    "tags": ["Authentication"],
    "summary": "User login",
    "description": "Authenticate user and receive JWT token",
    "security": [],
    "parameters": [
        {
            "name": "credentials",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["username", "password"],
                "properties": {
                    "username": {"type": "string", "example": "afiq"},
                    "password": {"type": "string", "format": "password", "example": "654321"},
                    "remember_me": {
                        "type": "boolean",
                        "default": False,
                        "description": "Extend token expiry"
                    }
                }
            }
        }
    ],
    "responses": {
        200: {"description": "Login successful"},
        401: {"description": "Bad username or password"},
        403: {"description": "Access Denied"}
    }
})
def login():
    try:
        data = request.get_json()
        if not data:
            return jsonify({"detail": "Invalid JSON body"}), 400

        username = data.get("username")
        password = data.get("password")
        remember_me = data.get("remember_me", False)

        if not username or not password:
            return jsonify({"detail": "username and password required"}), 400

        user = get_user_by_username(username)

        # ---- BASIC VALIDATION ----
        if not user or user.get("disabled"):
            return jsonify({"detail": "Bad username or password"}), 401

        # ---- PASSWORD VERIFICATION (SAFE) ----
        if not verify_password(password, user["hashed_password"]):
            return jsonify({"detail": "Bad username or password"}), 401

        # ---- AUTO UPGRADE PASSWORD HASH (IMPORTANT) ----
        if pwd_ctx.needs_update(user["hashed_password"]):
            try:
                new_hash = hash_password(password)
                db = get_db_connection()
                cur = db.cursor()
                cur.execute(
                    "UPDATE users SET hashed_password = %s WHERE username = %s",
                    (new_hash, user["username"])
                )
                db.commit()
                cur.close()
                db.close()
            except Exception as e:
                logging.warning(f"Password rehash failed for {username}: {e}")

        # ---- ACCESS LEVEL CHECK ----
        employee_id = user.get("employee_id")
        access_row = get_access_level(employee_id)
        access_level = access_row.get("accesslevel") if access_row else None

        if access_level not in ["Admin", "SuperAdmin"] and employee_id != "B0000":
            return jsonify({
                "detail": "Access Denied: Only Admin or SuperAdmin can access the dashboard."
            }), 403

        # ---- TOKEN CREATION ----
        token = create_token({
    "sub": user["username"],
    "employee_id": employee_id,
    "username": user["username"]
}, remember_me)
        expiry_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

        user_info = {
            "employee_id": employee_id,
            "username": user["username"],
            "person_name": user.get("PersonName", "N/A"),
            "role": access_level
        }

        return jsonify({
            "token": token,
            "user": user_info,
            "expires_at": expiry_time
        }), 200

    except Exception as e:
        return jsonify({
            "error_type": str(type(e)),
            "error_message": str(e),
            "traceback": traceback.format_exc()
        }), 500


@auth_bp.route("/auth/logout", methods=["POST"])
@swag_from({
    "tags": ["Authentication"],
    "summary": "User logout",
    "description": "Client discards JWT token",
})
@require_auth
def logout():
    return jsonify({"message": "Logged out successfully"}), 200


@auth_bp.route("/auth/me", methods=["GET"])
@swag_from({
    "tags": ["Authentication"],
    "summary": "Get current user info",
    "security": [{"Bearer": []}]
})
@require_auth
def read_me():
    u = request.user  # type: ignore
    employee_id = u["employee_id"]

    try:
        db = get_db_connection()
        cur = db.cursor()
        cur.execute(
            "SELECT AccessLevel, PersonName FROM workeridentity WHERE employee_id = %s",
            (employee_id,)
        )
        worker = cur.fetchone()
    finally:
        cur.close()
        db.close()

    return jsonify({
        "username": u["username"],
        "employee_id": employee_id,
        "person_name": worker.get("PersonName") if worker else "",
        "role": worker.get("AccessLevel", "Admin") if worker else "Admin",
        "disabled": u.get("disabled", False)
    })


@auth_bp.route("/auth/refresh", methods=["POST"])
@swag_from({
    "tags": ["Authentication"],
    "summary": "Refresh access token",
})
@require_auth
def refresh():
    u = request.user  # type: ignore
    new_token = create_token({"sub": u["username"]}, remember_me=False)
    expiry_time = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")

    return jsonify({
        "token": new_token,
        "expires_at": expiry_time
    }), 200
