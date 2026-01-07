from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging

# Import helpers and decorators
from app.decorators import require_admin, require_super_admin
from app.database import get_db_connection
from app.utils import delete_face_data, resolve_person_folder
from app.enums import (
    AccessLevel,
    StatusEnum,
    ACCESS_LEVEL_VALUES, STATUS_VALUES, CERTBOOL_VALUES,
    YEAR_VALUES, MONTH_VALUES, DAY_VALUES
)


# Define the Blueprint
worker_bp = Blueprint('worker', __name__)

# ---------- IDENTITY MANAGEMENT (Read/Delete) ----------

@worker_bp.route("/workers", methods=["GET"])
@swag_from({
    "tags": ["worker"],
    "summary": "Get list of all workers with identity and certificate data",
    "responses": {200: {"description": "List of workers"}},
    "security": [{"Bearer": []}]
})
@require_admin
def get_all_workers():
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("""
            SELECT
                WI.*,
                IM.Certificate1, IM.Certificate2, IM.Certificate3, IM.Certificate4
            FROM WorkerIdentity WI
            LEFT JOIN IdentityManagement IM ON WI.employee_id = IM.employee_id
            ORDER BY WI.PersonName
        """)
        workers = cur.fetchall()
        return jsonify(workers)
    except pymysql.MySQLError as e:
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

@worker_bp.route("/worker/<employee_id>", methods=["GET"])
@swag_from({
    "tags": ["worker"],
    "summary": "Get details for a single worker",
    "parameters": [{"name": "employee_id", "in": "path", "type": "string", "required": True}],
    "responses": {200: {"description": "Worker details"}, 404: {"description": "Worker not found"}},
    "security": [{"Bearer": []}]
})
@require_admin
def get_worker(employee_id):
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("""
            SELECT
                WI.*,
                IM.Certificate1, IM.Certificate2, IM.Certificate3, IM.Certificate4
            FROM WorkerIdentity WI
            LEFT JOIN IdentityManagement IM ON WI.employee_id = IM.employee_id
            WHERE WI.employee_id = %s
        """, (employee_id,))
        worker = cur.fetchone()
        if not worker:
            return jsonify({"detail": "Worker not found"}), 404
        return jsonify(worker)
    except pymysql.MySQLError as e:
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

@worker_bp.route("/worker/delete/<employee_id>", methods=["DELETE"])
@swag_from({
    "tags": ["worker"],
    "summary": "Permanently delete a worker's identity and face data",
    "parameters": [{"name": "employee_id", "in": "path", "type": "string", "required": True}],
    "responses": {200: {"description": "Worker deleted"}, 404: {"description": "Worker not found"}},
    "security": [{"Bearer": []}]
})
@require_super_admin
def delete_worker(employee_id):
    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Get the worker name for file system deletion
        cur.execute("SELECT PersonName FROM WorkerIdentity WHERE employee_id = %s", (employee_id,))
        worker_info = cur.fetchone()

        if not worker_info:
            return jsonify({"detail": f"Worker with employee_id {employee_id} not found"}), 404

        person_name = worker_info['PersonName']

        # 2. Delete DB records in transactional order
        cur.execute("DELETE FROM IdentityManagement WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM users WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM WorkerIdentity WHERE employee_id = %s", (employee_id,))

        # 3. Delete face data (using imported utility function)
        delete_face_data(person_name)

        db.commit()

        return jsonify({"msg": f"Worker {person_name} ({employee_id}) and associated data deleted."})

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Worker deletion failed: {e}")
        return jsonify({"detail": f"Database error during deletion: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ---------- WORKER IDENTITY UPDATE ----------

@worker_bp.route("/workeridentity/update", methods=["PUT"])
@swag_from({
    "tags": ["worker"],
    "summary": "Upsert WorkerIdentity (Admin only)",
    "parameters": [
        {"name": "person_name", "in": "formData", "type": "string", "required": True},
        {"name": "access_level", "in": "formData", "type": "string", "enum": ACCESS_LEVEL_VALUES, "required": True},
        {"name": "status", "in": "formData", "type": "string", "enum": STATUS_VALUES, "required": True},
        # ... (rest of the fields) ...
    ],
    "security": [{"Bearer": []}]
})
@require_admin
def update_workeridentity():
    form = request.form
    person_name = form.get("person_name")
    employee_id = form.get("employee_id")
    position = form.get("position")
    department = form.get("department")
    company = form.get("company")
    access_level = form.get("access_level")
    email = form.get("email")
    phone = form.get("phone")
    status = form.get("status")
    if not person_name or not employee_id:
        return jsonify({"detail": "person_name and employee_id required"}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        badge = employee_id.strip()
        cur.execute("SELECT * FROM WorkerIdentity WHERE employee_id = %s", (badge,))
        existing = cur.fetchone()
        if existing:
            cur.execute("""
                UPDATE WorkerIdentity
                SET PersonName=%s, Position=%s, Department=%s, Company=%s,
                    AccessLevel=%s, EMail=%s, Phone=%s, Status=%s
                WHERE employee_id=%s
            """, (person_name, position, department, company, access_level, email, phone, status, badge))
        else:
            cur.execute("""
                INSERT INTO WorkerIdentity
                (PersonName, employee_id, Position, Department, Company, AccessLevel, EMail, Phone, Status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
            """, (person_name, badge, position, department, company, access_level, email, phone, status))

            # Auto-create face folder for a new worker
            folder_path = resolve_person_folder(person_name)
            folder_path.mkdir(parents=True, exist_ok=True)
            logging.info(f"Auto-created face folder: {folder_path}")

        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()
    return jsonify({"msg": "WorkerIdentity upserted", "employee_id": badge})

# ---------- IDENTITY MANAGEMENT (CERTIFICATE UPDATE) ----------

@worker_bp.route("/identitymanagement/update", methods=["PUT"])
@require_admin
def update_identitymanagement():
    form = request.form
    employee_id = form.get("employee_id")
    if not employee_id:
        return jsonify({"detail": "employee_id required"}), 400

    badge = employee_id.strip()

    # Logic to skip certificate updates for Admin/SuperAdmin B#### IDs
    if badge.startswith("B"):
        logging.info(f"Skipping IdentityManagement update for employee_id: {badge} (Admin/SuperAdmin)")
        return jsonify({"msg": "IdentityManagement upserted (skipped for B#### badge)", "employee_id": badge})

    c1y, c1m, c1d = form.get("certificate1_year"), form.get("certificate1_month"), form.get("certificate1_day")
    c3y, c3m, c3d = form.get("certificate3_year"), form.get("certificate3_month"), form.get("certificate3_day")
    certificate2 = form.get("certificate2")
    certificate4 = form.get("certificate4")

    cert1 = f"{c1y}-{c1m}-{c1d}" if c1y and c1m and c1d else None
    cert3 = f"{c3y}-{c3m}-{c3d}" if c3y and c3m and c3d else None

    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("SELECT * FROM IdentityManagement WHERE employee_id = %s", (badge,))
        existing = cur.fetchone()

        if existing:
            cur.execute("""
                UPDATE IdentityManagement
                SET Certificate1=%s, Certificate2=%s, Certificate3=%s, Certificate4=%s
                WHERE employee_id=%s
            """, (cert1, certificate2, cert3, certificate4, badge))
        else:
            # Must retrieve PersonName from WorkerIdentity to insert into IdentityManagement
            cur.execute("SELECT PersonName FROM WorkerIdentity WHERE employee_id = %s LIMIT 1", (badge,))
            w = cur.fetchone()
            pname = w["PersonName"] if w else None

            cur.execute("""
                INSERT INTO IdentityManagement (PersonName, employee_id, Certificate1, Certificate2, Certificate3, Certificate4)
                VALUES (%s, %s, %s, %s, %s, %s)
            """, (pname, badge, cert1, certificate2, cert3, certificate4))

        db.commit()
    except pymysql.MySQLError as e:
        db.rollback()
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()

    return jsonify({"msg": "IdentityManagement upserted", "employee_id": badge})

# ---------- EMPLOYEE REGISTRATION ----------
@worker_bp.route("/employee/register", methods=["POST"])
@swag_from({
    "tags": ["worker"],
    "summary": "Register a new Employee (Admin only)",
    "description": "Creates entries in WorkerIdentity, IdentityManagement, and Users tables.",
    "parameters": [
        # WorkerIdentity Parameters
        {"name": "person_name", "in": "formData", "type": "string", "required": True, "description": "Full name of the employee."},
        {"name": "employee_id", "in": "formData", "type": "string", "required": True, "description": "Unique badge ID (e.g., E1234)."},
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
        409: {"description": "employee_id or Username already exists"},
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
    employee_id = form.get("employee_id")
    position = form.get("position")
    department = form.get("department")
    company = form.get("company")
    email = form.get("email")
    phone = form.get("phone")
    access_level = AccessLevel.Employee.value
    status = StatusEnum.Active.value

    # IdentityManagement Fields
    c1y = form.get("certificate1_year", "2035"); c1m = form.get("certificate1_month", "12"); c1d = form.get("certificate1_day", "31")
    certificate2 = form.get("certificate2", "0")
    c3y = form.get("certificate3_year", "2035"); c3m = form.get("certificate3_month", "12"); c3d = form.get("certificate3_day", "31")
    certificate4 = form.get("certificate4", "0")
    cert1 = f"{c1y}-{c1m}-{c1d}"
    cert3 = f"{c3y}-{c3m}-{c3d}"

    required_fields = {
        "person_name": person_name, "employee_id": employee_id, "position": position, "department": department,
        "company": company, "email": email, "phone": phone
    }

    if not all(required_fields.values()):
        missing = [k for k, v in required_fields.items() if not v]
        return jsonify({"detail": f"Missing required fields: {', '.join(missing)}"}), 400

    file_list = request.files.getlist('files')

    if not file_list or not any(f.filename for f in file_list):
        return jsonify({"detail": "At least one face image file is required."}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Check for existing employee_id
        cur.execute("SELECT employee_id FROM WorkerIdentity WHERE employee_id = %s", (employee_id,))
        if cur.fetchone():
            return jsonify({"detail": f"employee_id '{employee_id}' already exists"}), 409

        # 2. Insert into WorkerIdentity
        cur.execute("""
            INSERT INTO WorkerIdentity
            (PersonName, employee_id, Position, Department, Company, AccessLevel, EMail, Phone, Status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (person_name, employee_id, position, department, company, access_level, email, phone, status))

        # 3. Insert into IdentityManagement
        cur.execute("""
            INSERT INTO IdentityManagement (PersonName, employee_id, Certificate1, Certificate2, Certificate3, Certificate4)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (person_name, employee_id, cert1, certificate2, cert3, certificate4))

        # 4. Create face data folder and update pkl timestamp
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
        from app.utils import touch_pkltimestamp_debounced
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
        "employee_id": employee_id,
        "person_name": person_name,
        "images_saved": saved_files})