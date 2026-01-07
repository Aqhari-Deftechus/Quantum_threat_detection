from functools import wraps
from flask import request, jsonify
import logging

# Import necessary functions/modules from our utils file
from app.utils import decode_token, get_user_by_username, get_access_level
from app.database import get_db_connection

# ======================================================
# DECORATORS
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

            # Use our new utility function to fetch user details
            user = get_user_by_username(username)

            if not user:
                return jsonify({"detail": "User not found"}), 401

            # Attach user to request object for access in the route function
            request.user = user # type: ignore

        except Exception as e:
            return jsonify({"detail": str(e)}), 401

        return func(*args, **kwargs)
    return wrapper

def check_admin_access(employee_id):
    """Internal helper to check if a employee_id has Admin or SuperAdmin access."""
    # B0000 is always considered SuperAdmin/Admin
    if employee_id == "B0000":
        return True, "SuperAdmin"

    db = get_db_connection(); cur = db.cursor()
    access = None
    try:
        cur.execute("SELECT AccessLevel FROM workeridentity WHERE employee_id = %s", (employee_id,))
        row = cur.fetchone()
        access = row["AccessLevel"] if row else None
    finally:
        cur.close(); db.close()

    if access in ["Admin", "SuperAdmin"]:
        return True, access

    return False, access # Return current access level if known

def require_admin(func):
    @wraps(func)
    @require_auth
    def wrapper(*args, **kwargs):
        user = request.user # type: ignore
        employee_id = user.get("employee_id")

        has_access, _ = check_admin_access(employee_id)

        if not has_access:
            return jsonify({"detail": "Admin privileges required"}), 403

        return func(*args, **kwargs)
    return wrapper

def require_super_admin(func):
    @wraps(func)
    @require_auth
    def wrapper(*args, **kwargs):
        user = request.user # type: ignore
        employee_id = user.get("employee_id")

        has_access, access = check_admin_access(employee_id)

        if not has_access or access != "SuperAdmin":
            return jsonify({"detail": "SuperAdmin privileges required"}), 403

        return func(*args, **kwargs)
    return wrapper