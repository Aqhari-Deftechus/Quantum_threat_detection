from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import logging
from datetime import datetime
import traceback

# Import helpers from other modules
from app.decorators import require_auth, require_admin
from app.utils import (
    get_user_by_username, verify_password, hash_password, create_token,
    get_access_level#, get_worker_by_badge # type: ignore
)
from app.database import get_db_connection
from app.enums import AccessLevel, ACCESS_LEVEL_VALUES # Import Enums for swagger lists

# Define the Blueprint
auth_bp = Blueprint('Authentication', __name__)

# ---------- AUTH ----------

@auth_bp.route("/auth/login", methods=["POST"])
@swag_from({
    "tags": ["Authentication"],
    "summary": "User login",
    "description": "Authenticate user and receive JWT token",
    "security": [],
    # FIX: Use Swagger 2.0 'parameters' array to ensure inputs are rendered correctly in Flasgger's UI
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
                    "remember_me": {"type": "boolean", "default": False, "description": "Extend token expiry to 30 days"}
                }
            },
            "description": "User login credentials"
        }
    ],
    "responses": {
        200: {
            "description": "Login successful",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string", "description": "JWT access token"},
                            "user": { # Simplified inline schema for User info
                                "type": "object",
                                "properties": {
                                    "employee_id": {"type": "string"},
                                    "username": {"type": "string"},
                                    "person_name": {"type": "string"},
                                    "role": {"type": "string"}
                                }
                            },
                            "expires_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
        },
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

        if not user or not verify_password(password, user["hashed_password"]) or user.get("disabled"):
            return jsonify({"detail": "Bad username or password"}), 401

        employee_id = user.get("employee_id")
        print("employee_id:", employee_id)
        access_level = get_access_level(employee_id).get("accesslevel") if get_access_level(employee_id) else None # type: ignore
        print(access_level)
        # Enforce access for dashboard login
        if access_level not in ["Admin", "SuperAdmin"] and user.get("employee_id") != "B0000":
            return jsonify({"detail": "Access Denied: Only Admin or SuperAdmin can access the dashboard."}), 403

        token = create_token({"sub": user["username"]}, remember_me)
        # NOTE: Calculating actual expiry time is complex. For a real app, you'd calculate it here.
        expiry_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ") # Placeholder

        user_info = {
            "employee_id": user["employee_id"],
            "username": user["username"],
            "person_name": user.get("PersonName", "N/A"),
            "role": access_level
        }

        return jsonify({
            "token": token,
            "user": user_info,
            "expires_at": expiry_time
        })
    
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
    "description": "The client should discard the token. This endpoint confirms the session closure.",
    "responses": {
        200: {
            "description": "Logout successful",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {"message": {"type": "string", "example": "Logged out successfully"}}
                    }
                }
            }
        }
    }
})
@require_auth
def logout():
    # In a JWT system, logout is achieved client-side by discarding the token.
    # This endpoint simply confirms the action.
    return jsonify({"message": "Logged out successfully"}), 200

@auth_bp.route("/auth/me", methods=["GET"])
@swag_from({"tags": ["Authentication"], "summary": "Get current user info", "security": [{"Bearer": []}]})
@require_auth
def read_me():
    u = request.user # type: ignore
    employee_id = u["employee_id"]

    try:
        db = get_db_connection(); cur = db.cursor()
        cur.execute("SELECT AccessLevel, PersonName FROM workeridentity WHERE employee_id = %s", (employee_id,))
        worker = cur.fetchone()

        if worker is None:
            access_level = "Admin" # Default fallback
            person_name = u.get("PersonName", "")
        else:
            access_level = worker.get("accesslevel", "Admin")
            person_name = worker.get("PersonName", u.get("PersonName", ""))
    finally:
        cur.close(); db.close() # type: ignore

    return jsonify({
        "username": u["username"],
        "employee_id": employee_id,
        "person_name": person_name,
        "role": access_level,
        "disabled": u.get("disabled", False)
    })


@auth_bp.route("/auth/refresh", methods=["POST"])
@swag_from({
    "tags": ["Authentication"],
    "summary": "Refresh access token",
    "description": "Generates a new short-lived access token using the current valid token.",
    "responses": {
        200: {
            "description": "Token refreshed",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "token": {"type": "string"},
                            "expires_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
        },
        401: {"description": "Invalid or expired token."}
    }
})
@require_auth # Requires a valid but potentially short-lived token to refresh
def refresh():
    u = request.user # type: ignore
    remember_me = False # Standard refresh returns a short-lived token

    # Re-issue a new token based on the existing token payload (sub: username)
    new_token = create_token({"sub": u["username"]}, remember_me) # type: ignore

    # Placeholder expiry time
    expiry_time = datetime.now().strftime("%Y-%m-%dT%H:%M:%SZ")

    return jsonify({
        "token": new_token,
        "expires_at": expiry_time
    }), 200