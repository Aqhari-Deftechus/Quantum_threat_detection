from flask import Blueprint, logging, request, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore

# Import necessary modules
from app.decorators import require_admin, require_super_admin # user usually require Admin access
from app.database import get_db_connection
from app.enums import AccessLevel, ACCESS_LEVEL_VALUES # Example of importing Enum data
from app.utils import (hash_password,delete_face_data)

# Define the Blueprint
user_bp = Blueprint('users', __name__, url_prefix='/users')

# ==================== USERS ====================

# ---------- GET LIST OF USER ----------
@user_bp.route("/", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Users"],
    "summary": "List admin users",
    "description": "Get paginated list of Admin and SuperAdmin users",
    "parameters": [
        {"name": "page", "in": "query", "type": "integer", "default": 1, "description": "Page number"},
        {"name": "limit", "in": "query", "type": "integer", "default": 20, "description": "Items per page"},
        {"name": "search", "in": "query", "type": "string", "description": "Search by name, username, or badge ID"},
        {"name": "role", "in": "query", "type": "string", "enum": ["Admin", "SuperAdmin"], "description": "Filter by specific admin role"},
        {"name": "is_active", "in": "query", "type": "boolean", "description": "Filter by active status"}
    ],
    "responses": {
        "200": {
            "description": "List of users",
            "schema": {
                "type": "object",
                "properties": {
                    "items": {"type": "array", "items": {"type": "object"}},
                    "total": {"type": "integer"},
                    "page": {"type": "integer"},
                    "pages": {"type": "integer"},
                    "limit": {"type": "integer"}
                }
            }
        }
    }
})
def list_users():
    db = get_db_connection(); cur = db.cursor()
    # 1. Parse Query Parameters
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    search = request.args.get('search', '').strip()
    role_filter = request.args.get('role')
    is_active_param = request.args.get('is_active')

    # Calculate Offset
    offset = (page - 1) * limit

    # 2. Build Dynamic SQL
    # We join user with workeridentity to get full details
    base_query = """
        FROM users U
        JOIN workeridentity W ON U.employee_id = W.employee_id
        WHERE W.AccessLevel IN ('Admin', 'SuperAdmin')
    """
    params = []

    # Filter: Role (Specific Admin vs SuperAdmin)
    if role_filter:
        base_query += " AND W.AccessLevel = %s"
        params.append(role_filter)

    # Filter: Is Active (Boolean to Enum mapping)
    if is_active_param is not None:
        is_active = is_active_param.lower() == 'true'
        if is_active:
            base_query += " AND W.Status = 'Active'"
        else:
            base_query += " AND W.Status != 'Active'"

    # Filter: Search (Username, Real Name, or Badge)
    if search:
        base_query += " AND (U.username LIKE %s OR W.PersonName LIKE %s OR U.employee_id LIKE %s)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    # 3. Execute Queries
    try:
        # A. Get Total Count (for pagination)
        count_query = f"SELECT COUNT(*) as total {base_query}"
        cur.execute(count_query, tuple(params))
        total_records = cur.fetchone()['total'] # type: ignore

        # B. Get Data
        data_query = f"""
            SELECT
                U.id, U.username, U.employee_id, U.disabled,W.PersonName,
                W.AccessLevel as role, W.Status, W.EMail, W.Department
            {base_query}
            ORDER BY U.employee_id ASC
            LIMIT %s OFFSET %s
        """
        # Add limit/offset to params
        select_params = params + [limit, offset]

        cur.execute(data_query, tuple(select_params))
        users = cur.fetchall()

        # 4. Construct Response
        total_pages = (total_records + limit - 1) // limit

        return jsonify({
            "items": users,
            "total": total_records,
            "page": page,
            "pages": total_pages,
            "limit": limit
        })

    except Exception as e:
        print(f"Error listing users: {e}")
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close()
        db.close()

# ---------- CREATE NEW USER ----------
@user_bp.route("/", methods=["POST"])
# @require_admin
@swag_from({
    "tags": ["Users"],
    "summary": "Create user",
    "description": "Create new admin/superadmin user. Requires JSON body.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["username", "password", "email", "full_name", "role"],
                "properties": {
                    "username": {"type": "string"},
                    "password": {"type": "string"},
                    "full_name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "role": {"type": "string", "enum": ["Admin", "SuperAdmin"]},
                    "department": {"type": "string"},
                    "position": {"type": "string"},
                    "phone": {"type": "string"},
                    "company": {"type": "string"}
                }
            }
        }
    ],
    "responses": {
        "201": {
            "description": "User created",
            "schema": {
                "type": "object",
                "properties": {
                    "employee_id": {"type": "string"},
                    "username": {"type": "string"},
                    "role": {"type": "string"}
                }
            }
        },
        "400": {"description": "Missing required fields"},
        "409": {"description": "Username or Email already exists"}
    }
})
def create_user():
    db = get_db_connection(); cur = db.cursor(pymysql.cursors.DictCursor)
    # 1. Parse JSON Body
    data = request.get_json()
    if not data:
        return jsonify({"detail": "Invalid JSON body"}), 400

    # 2. Extract & Validate Fields
    username = data.get("username")
    password = data.get("password")
    person_name = data.get("full_name")
    email = data.get("email")
    role = data.get("role", "Admin") # Default to Admin

    # Optional fields
    dept = data.get("department", "Management")
    pos = data.get("position", "Administrator")
    phone = data.get("phone", "")
    company = data.get("company", "QTech")

    if not all([username, password, person_name, email]):
        return jsonify({"detail": "Missing required fields: username, password, full_name, email"}), 400

    # Enforce Admin Creation Policy
    if role not in ["Admin", "SuperAdmin", "Supervisor", "Viewer"]:
        return jsonify({"detail": "This endpoint can only create Admin or SuperAdmin users."}), 400

    try:
        # 3. Check Duplicates (Username or Email)
        cur.execute("SELECT username FROM users WHERE username = %s", (username,))
        if cur.fetchone():
            return jsonify({"detail": f"Username '{username}' already taken"}), 409

        cur.execute("SELECT EMail FROM workeridentity WHERE EMail = %s", (email,))
        if cur.fetchone():
            return jsonify({"detail": f"Email '{email}' already registered"}), 409

        # 4. Generate New employee_id (Bxxxx format)
        cur.execute("SELECT employee_id FROM workeridentity WHERE employee_id LIKE 'B%' ORDER BY employee_id DESC LIMIT 1")
        row = cur.fetchone()
        if row:
            try:
                # Extract number, increment, pad with zeros
                current_num = int(row["employee_id"][1:])
                new_employee_id = f"B{current_num + 1:04d}"
            except ValueError:
                new_employee_id = "B0001"
        else:
            new_employee_id = "B0001"

        # 5. Insert into workeridentity
        cur.execute("""
            INSERT INTO workeridentity
            (PersonName, employee_id, Position, Department, Company, AccessLevel, EMail, Phone, Status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Active')
        """, (person_name, new_employee_id, pos, dept, company, role, email, phone))

        # 6. Insert into user (Authentication)
        hashed_pw = hash_password(password)
        cur.execute("""
            INSERT INTO users (username, employee_id, hashed_password, disabled)
            VALUES (%s, %s, %s, %s)
        """, (username, new_employee_id, hashed_pw, False))

        db.commit()

        return jsonify({
            "msg": "User created successfully",
            "employee_id": new_employee_id,
            "username": username,
            "role": role,
            "status": "Active"
        }), 201

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Database Error: {e}") # type: ignore
        return jsonify({"detail": f"Database Error: {str(e)}"}), 500
    except Exception as e:
        db.rollback()
        logging.error(f"Server Error: {e}") # type: ignore
        return jsonify({"detail": f"Server Error: {str(e)}"}), 500
    finally:
        cur.close()
        db.close()

# ---------- GET BY USER ID ----------
@user_bp.route("/<int:user_id>", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Users"],
    "summary": "Get user by ID",
    "description": "Get detailed information for a specific user by their internal integer ID.",
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "required": True,
            "type": "integer",
            "description": "Internal User ID"
        }
    ],
    "responses": {
        "200": {
            "description": "User details",
            "schema": {
                "type": "object",
                "properties": {
                    "id": {"type": "int"},
                    "username": {"type": "string"},
                    "employee_id": {"type": "string"},
                    "full_name": {"type": "string"},
                    "role": {"type": "string"},
                    "email": {"type": "string"},
                    "department": {"type": "string"},
                    "position": {"type": "string"},
                    "status": {"type": "string"}
                }
            }
        },
        "404": {"description": "User not found"}
    }
})
def get_user_by_id(user_id):
    db = get_db_connection()
    cur = db.cursor()
    try:
        # Join user table with workeridentity to get full profile
        # We assume user table has a primary key 'id' (or 'ID')
        cur.execute("""
            SELECT
                U.id,
                U.username,
                U.employee_id,
                U.disabled,
                W.PersonName as full_name,
                W.AccessLevel as role,
                W.EMail as email,
                W.Department as department,
                W.Position as position,
                W.Phone as phone,
                W.Status as status,
                W.Company as company
            FROM users U
            LEFT JOIN workeridentity W ON U.employee_id = W.employee_id
            WHERE U.id = %s
        """, (user_id,))

        user = cur.fetchone()
        print(user)

        if not user:
            return jsonify({"detail": "User not found"}), 404

        return jsonify(user)

    except Exception as e:
        print(f"Error fetching user {user_id}: {e}")
        return jsonify({"detail": "Internal server error"}), 500
    finally:
        cur.close()
        db.close()

# ---------- UPDATE EXISTING USER ----------
@user_bp.route("/<int:user_id>", methods=["PUT"])
@require_admin
@swag_from({
    "tags": ["Users"],
    "summary": "Update user",
    "description": "Update detailed information for a specific user by their internal integer ID.",
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "required": True,
            "type": "integer",
            "description": "Internal User ID"
        },
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    # User Credentials (Optional updates)
                    "username": {"type": "string", "description": "New username"},
                    "password": {"type": "string", "description": "New password (will be hashed)"},
                    "disabled": {"type": "boolean", "description": "Account disabled status"},
                    # Worker Identity Details (Profile updates)
                    "full_name": {"type": "string"},
                    "email": {"type": "string", "format": "email"},
                    "role": {"type": "string", "enum": ["Visitor", "Employee", "Contractor", "Admin", "SuperAdmin", "Security"]},
                    "department": {"type": "string"},
                    "position": {"type": "string"},
                    "phone": {"type": "string"},
                    "company": {"type": "string"},
                    "status": {"type": "string", "enum": ["Active", "Suspended", "Terminated"]}
                }
            }
        }
    ],
    "responses": {
        "200": {
            "description": "User updated",
            # "schema": {"$ref": "#/components/schemas/User"} # Assuming User schema returns similar detail as GET
        },
        "404": {"description": "User not found"}
    }
})
def update_user(user_id):
    data = request.get_json()
    if not data:
        return jsonify({"detail": "Invalid JSON body"}), 400

    db = get_db_connection()
    cur = db.cursor()

    try:
        # 1. Get current employee_id associated with the internal user_id
        cur.execute("SELECT employee_id FROM users WHERE ID = %s", (user_id,))
        user_info = cur.fetchone()
        if not user_info:
            return jsonify({"detail": "User not found"}), 404

        employee_id = user_info['employee_id']

        # --- A. Update user Table (Credentials) ---
        user_updates = []
        user_params = []

        if 'username' in data:
            user_updates.append("username = %s")
            user_params.append(data['username'])

        if 'password' in data and data['password']:
            hashed_pw = hash_password(data['password'])
            user_updates.append("hashed_password = %s")
            user_params.append(hashed_pw)

        if 'disabled' in data:
            user_updates.append("disabled = %s")
            user_params.append(data['disabled'])

        if user_updates:
            user_params.append(user_id)
            user_sql = f"UPDATE users SET {', '.join(user_updates)} WHERE ID = %s"
            cur.execute(user_sql, tuple(user_params))

        # --- B. Update workeridentity Table (Profile) ---
        identity_updates = []
        identity_params = []

        # Mapping API keys to DB column names (where they differ)
        field_map = {
            'full_name': 'PersonName',
            'email': 'EMail',
            'role': 'AccessLevel',
            'department': 'Department',
            'position': 'Position',
            'phone': 'Phone',
            'company': 'Company',
            'status': 'Status'
        }

        for api_key, db_col in field_map.items():
            if api_key in data:
                identity_updates.append(f"{db_col} = %s")
                identity_params.append(data[api_key])

        if identity_updates:
            identity_params.append(employee_id)
            identity_sql = f"UPDATE workeridentity SET {', '.join(identity_updates)} WHERE employee_id = %s"
            cur.execute(identity_sql, tuple(identity_params))

        db.commit()

        # 3. Retrieve and return the updated user object (reusing GET logic)
        cur.execute("""
            SELECT
                U.id, U.username, U.employee_id, U.disabled,
                W.PersonName as full_name, W.AccessLevel as role, W.EMail as email,
                W.Department as department, W.Position as position, W.Phone as phone,
                W.Status as status, W.Company as company
            FROM users U
            LEFT JOIN workeridentity W ON U.employee_id = W.employee_id
            WHERE U.id = %s
        """, (user_id,))

        updated_user = cur.fetchone()

        return jsonify(updated_user)

    except pymysql.MySQLError as e:
        db.rollback()
        print(f"Database Error during update: {e}")
        return jsonify({"detail": str(e)}), 500
    except Exception as e:
        db.rollback()
        print(f"Error updating user {user_id}: {e}")
        return jsonify({"detail": "Internal server error"}), 500
    finally:
        cur.close()
        db.close()

# ---------- DELETE USER ----------
@user_bp.route("/<int:user_id>", methods=["DELETE"])
@require_super_admin # Requires SuperAdmin privilege for permanent deletion
@swag_from({
    "tags": ["Users"],
    "summary": "Delete user",
    "description": "Permanently deletes a user account, their profile, and associated face data by internal integer ID.",
    "parameters": [
        {
            "name": "user_id",
            "in": "path",
            "required": True,
            "type": "integer",
            "description": "Internal User ID"
        }
    ],
    "responses": {
        "204": {"description": "User successfully deleted (No Content)"},
        "404": {"description": "User not found"}
    }
})
def delete_user(user_id):
    db = get_db_connection()
    cur = db.cursor()

    try:
        # 1. Get employee_id and PersonName from the internal user_id
        print("user_id: ",user_id)
        cur.execute("""
            SELECT U.employee_id, W.PersonName
            FROM users U
            JOIN workeridentity W ON U.employee_id = W.employee_id
            WHERE U.ID = %s
        """, (user_id,))

        user_info = cur.fetchone()

        if not user_info:
            return jsonify({"detail": "User not found"}), 404

        employee_id = user_info['employee_id']
        person_name = user_info['PersonName']

        # 2. Perform Cascading Deletion

        # A. Delete from user table
        cur.execute("DELETE FROM users WHERE ID = %s", (user_id,))

        # B. Delete associated workeridentity (and identitymanagement via employee_id)
        # Note: We rely on the employee_id column for workeridentity/identitymanagement tables
        cur.execute("DELETE FROM identitymanagement WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM workeridentity WHERE employee_id = %s", (employee_id,))

        # C. Delete Face Data (utility function handles this)
        delete_face_data(person_name)

        db.commit()

        # 3. Return 204 No Content for successful deletion
        return "", 204

    except pymysql.MySQLError as e:
        db.rollback()
        print(f"Database Error during deletion: {e}")
        return jsonify({"detail": "Database error during deletion"}), 500
    except Exception as e:
        db.rollback()
        print(f"Error deleting user {user_id}: {e}")
        return jsonify({"detail": "Internal server error"}), 500
    finally:
        cur.close()
        db.close()