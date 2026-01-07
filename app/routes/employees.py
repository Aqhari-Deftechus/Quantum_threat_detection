from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging
from datetime import datetime
from werkzeug.utils import secure_filename
import pandas as pd

# Assuming these utilities are available in your Flask app structure
from app.decorators import require_admin, require_super_admin
from app.database import get_db_connection
from app.utils import delete_face_data, resolve_person_folder, touch_pkltimestamp_debounced
from app.enums import AccessLevel, StatusEnum, CERTBOOL_VALUES # Assuming enums like AccessLevel are defined

# Define the Blueprint
employee_bp = Blueprint('employee', __name__)
logging.basicConfig(level=logging.INFO)

# Utility to convert internal ID to employee_id (used for deletion, face data)
def get_employee_id_from_employee_id(db_cursor, employee_id):
    db_cursor.execute("SELECT employee_id, PersonName FROM workeridentity WHERE employee_id = %s", (employee_id,))
    return db_cursor.fetchone()

# Utility to fetch full employee profile
def fetch_employee_details(db_cursor, employee_id):
    db_cursor.execute("""
        SELECT
            WI.*,
            IM.Certificate1, IM.Certificate2, IM.Certificate3, IM.Certificate4
        FROM workeridentity WI
        LEFT JOIN identitymanagement IM ON WI.employee_id = IM.employee_id
        WHERE WI.employee_id = %s
    """, (employee_id,))
    return db_cursor.fetchone()

# Helper for GET /employees filter mapping
def get_validity_status(cert_date_str):
    if not cert_date_str: return "invalid"
    try:
        cert_date = datetime.strptime(cert_date_str, '%Y-%m-%d').date()
        today = datetime.now().date()
        if cert_date < today: return "expired"
        if cert_date > today: return "future"
        return "active" # Today is the expiration date
    except ValueError:
        return "invalid"


# ----------------------------------------------------------------------
# 1. GET /employees - LIST EMPLOYEES (with Advanced Filtering & Pagination)
# ----------------------------------------------------------------------
@employee_bp.route("/employees", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Employees"],
    "summary": "List employees",
    "description": "Get paginated list of employees with filtering.",
    "parameters": [
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "limit", "in": "query", "type": "integer", "default": 20},
        {"name": "search", "in": "query", "type": "string", "description": "Search name, badge ID"},
        {"name": "department", "in": "query", "type": "string"},
        {"name": "is_active", "in": "query", "type": "boolean", "description": "Filter by active status"},
        {"name": "validity_status", "in": "query", "type": "string", "enum": ["active", "expired", "future", "invalid"]}
    ],
    "responses": {200: {"description": "Paginated list of employees"}}
})
def list_employees():
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    search = request.args.get('search', '').strip()
    department = request.args.get('department', '').strip()
    is_active_param = request.args.get('is_active')
    validity_status = request.args.get('validity_status', '').strip()

    offset = (page - 1) * limit
    db = get_db_connection(); cur = db.cursor()

    base_query = """
        FROM workeridentity WI
        LEFT JOIN identitymanagement IM ON WI.employee_id = IM.employee_id
        WHERE WI.AccessLevel NOT IN ('Admin', 'SuperAdmin')
    """
    params = []

    # Filtering Logic
    if department:
        base_query += " AND WI.Department = %s"
        params.append(department)

    if is_active_param is not None:
        is_active = is_active_param.lower() == 'true'
        status = StatusEnum.Active.value if is_active else StatusEnum.Suspended.value
        base_query += " AND WI.Status = %s"
        params.append(status)

    if search:
        base_query += " AND (WI.PersonName LIKE %s OR WI.employee_id LIKE %s OR WI.Department LIKE %s)"
        search_term = f"%{search}%"
        params.extend([search_term, search_term, search_term])

    try:
        # 1. Get total count
        cur.execute(f"SELECT COUNT(*) as total {base_query}", tuple(params))
        total_records = cur.fetchone()['total'] # type: ignore

        # 2. Get paginated data
        data_query = f"""
            SELECT
                WI.PersonName, WI.employee_id, WI.Position, WI.Department, WI.AccessLevel, WI.Status,
                IM.Certificate1, IM.Certificate2, IM.Certificate3, IM.Certificate4
            {base_query}
            ORDER BY WI.PersonName
            LIMIT %s OFFSET %s
        """
        select_params = params + [limit, offset]

        cur.execute(data_query, tuple(select_params))
        employees = cur.fetchall()

        # 3. Apply validity_status filtering in Python (easier than complex SQL date logic)
        if validity_status:
            employees = [
                emp for emp in employees
                if get_validity_status(str(emp.get('Certificate1'))) == validity_status
            ]
        print(employees)
        total_pages = (total_records + limit - 1) // limit if total_records else 0

        return jsonify({
            "items": employees,
            "total": total_records,
            "page": page,
            "pages": total_pages,
            "limit": limit
        })

    except pymysql.MySQLError as e:
        logging.error(f"Employee list failed: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------
# 2. POST /employees - CREATE EMPLOYEE (JSON Body, no files)
# ----------------------------------------------------------
# Note: This route expects JSON input, different from the /employee/register form-data route.
@employee_bp.route("/employees", methods=["POST"])
@require_admin
@swag_from({
    "tags": ["Employees"],
    "summary": "Create employee",
    "description": "Creates entries in workeridentity and identitymanagement tables using JSON payload.",
    # ---------------------------------------------------------
    # CHANGE: Use 'parameters' with 'in: body' for Swagger 2.0
    # ---------------------------------------------------------
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["person_name", "employee_id", "email"],
                "properties": {
                    "person_name": {"type": "string", "example": "John Doe"},
                    "employee_id": {"type": "string", "example": "E12345"},
                    "email": {"type": "string", "example": "john@qtech.com"},
                    "position": {"type": "string", "default": "Worker"},
                    "department": {"type": "string", "default": "Operations"},
                    "company": {"type": "string", "default": "QTech"},
                    "phone": {"type": "string", "example": "+123456789"},
                    "access_level": {"type": "string", "default": "Employee"},
                    "cert1": {"type": "string", "format": "date", "default": "2035-12-31"},
                    "cert2": {"type": "integer", "default": 0},
                    "cert3": {"type": "string", "format": "date", "default": "2035-12-31"},
                    "cert4": {"type": "integer", "default": 0}
                }
            }
        }
    ],
    "responses": {
        "201": {
            "description": "Employee created",
            "schema": {
                "type": "object",
                "properties": {
                    "msg": {"type": "string"},
                    "employeeId": {"type": "integer"},
                    "employee_id": {"type": "string"}
                }
            }
        },
        "400": {"description": "Invalid input / Missing fields"},
        "409": {"description": "employee_id already exists"},
        "500": {"description": "Database error"}
    }
})
def create_employee():
    data = request.get_json()
    if not data: return jsonify({"detail": "Invalid JSON body"}), 400

    # Required and default fields
    person_name = data.get("person_name")
    employee_id = data.get("employee_id")
    email = data.get("email")
    position = data.get("position", "Worker")
    department = data.get("department", "Operations")
    company = data.get("company", "QTech")
    phone = data.get("phone", "")

    # Defaulting to Employee access level unless specifically overridden (but still restricted)
    access_level = data.get("access_level", AccessLevel.Employee.value)
    status = StatusEnum.Active.value

    # Certificate fields (simplified for JSON: expecting YYYY-MM-DD string or 0/1 integer)
    cert1 = data.get("cert1", "2035-12-31")
    cert2 = data.get("cert2", 0)
    cert3 = data.get("cert3", "2035-12-31")
    cert4 = data.get("cert4", 0)

    if not all([person_name, employee_id, email]):
        return jsonify({"detail": "Missing required fields: person_name, employee_id, email"}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Check for existing employee_id
        cur.execute("SELECT employee_id FROM workeridentity WHERE employee_id = %s", (employee_id,))
        if cur.fetchone():
            return jsonify({"detail": f"employee_id '{employee_id}' already exists"}), 409

        # 2. Insert into workeridentity
        cur.execute("""
            INSERT INTO workeridentity
            (PersonName, employee_id, Position, Department, Company, AccessLevel, EMail, Phone, Status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
        """, (person_name, employee_id, position, department, company, access_level, email, phone, status))

        # 3. Insert into identitymanagement
        cur.execute("""
            INSERT INTO identitymanagement (PersonName, employee_id, Certificate1, Certificate2, Certificate3, Certificate4)
            VALUES (%s, %s, %s, %s, %s, %s)
        """, (person_name, employee_id, cert1, cert2, cert3, cert4))

        # 4. Auto-create face folder (face images are uploaded later via /faces endpoint)
        folder_path = resolve_person_folder(person_name)
        folder_path.mkdir(parents=True, exist_ok=True)
        logging.info(f"Auto-created face folder for new employee {person_name}")

        db.commit()


        return jsonify({
            "msg": "Employee registered successfully",
            "employee_id": employee_id,
            "person_name": person_name
        }), 201

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Employee registration failed: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    except Exception as e:
        db.rollback()
        logging.error(f"Registration error: {e}")
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()

# -------------------------------------------------
# 3. GET /employees/{employeeId} - GET EMPLOYEE
# -------------------------------------------------
@employee_bp.route("/employees/<string:employee_id>", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Employees"],
    "summary": "Get employee by ID",
    "parameters": [{"name": "employee_id", "in": "path", "type": "string", "required": True}],
    "responses": {200: {"description": "Employee details"}, 404: {"description": "Employee not found"}}
})
def get_employee(employee_id):
    db = get_db_connection(); cur = db.cursor()
    try:
        employee = fetch_employee_details(cur, employee_id)
        if not employee:
            return jsonify({"detail": "Employee not found"}), 404
        return jsonify(employee)
    except pymysql.MySQLError as e:
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# -------------------------------------------------
# 4. PUT /employees/{employeeId} - UPDATE EMPLOYEE
# -------------------------------------------------
@employee_bp.route("/employees/<string:employee_id>", methods=["PUT"])
@require_admin
@swag_from({
    "tags": ["Employees"],
    "summary": "Update employee",
    "parameters": [
        {"name": "employee_id", "in": "path", "type": "string", "required": True},
        {"name": "body", "in": "body", "required": True, "schema": {"type": "object", "properties": {
            "person_name": {"type": "string"}, "position": {"type": "string"}, "department": {"type": "string"},
            "company": {"type": "string"}, "access_level": {"type": "string"}, "email": {"type": "string"},
            "phone": {"type": "string"}, "status": {"type": "string"},
            "certificate1": {"type": "string", "format": "date"}, "certificate2": {"type": "integer"},
            "certificate3": {"type": "string", "format": "date"}, "certificate4": {"type": "integer"}
        }}}
    ],
    "responses": {200: {"description": "Employee updated"}, 404: {"description": "Employee not found"}}
})
def update_employee(employee_id):
    data = request.get_json()
    if not data: return jsonify({"detail": "Invalid JSON body"}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        worker_info = get_employee_id_from_employee_id(cur, employee_id)
        if not worker_info: return jsonify({"detail": "Employee not found"}), 404
        employee_id = worker_info['employee_id']
        person_name = worker_info['PersonName']

        # 1. Update workeridentity (Identity details)
        identity_updates = []
        identity_params = []
        identity_fields = {
            'person_name': 'PersonName', 'position': 'Position', 'department': 'Department',
            'company': 'Company', 'access_level': 'AccessLevel', 'email': 'EMail',
            'phone': 'Phone', 'status': 'Status'
        }
        for api_key, db_col in identity_fields.items():
            if api_key in data:
                identity_updates.append(f"{db_col} = %s")
                identity_params.append(data[api_key])

        if identity_updates:
            identity_params.append(employee_id)
            cur.execute(f"UPDATE workeridentity SET {', '.join(identity_updates)} WHERE employee_id = %s", tuple(identity_params))

            # If PersonName changed, face data folder name needs to be updated.
            if 'person_name' in data and data['person_name'] != person_name:
                old_folder = resolve_person_folder(person_name)
                new_folder = resolve_person_folder(data['person_name'])
                if old_folder.exists():
                    old_folder.rename(new_folder)
                    logging.info(f"Renamed face folder from {person_name} to {data['person_name']}")
                touch_pkltimestamp_debounced()


        # 2. Update identitymanagement (Certificate details)
        cert_updates = []
        cert_params = []
        cert_fields = {
            'certificate1': 'Certificate1', 'certificate2': 'Certificate2',
            'certificate3': 'Certificate3', 'certificate4': 'Certificate4'
        }
        for api_key, db_col in cert_fields.items():
            if api_key in data:
                cert_updates.append(f"{db_col} = %s")
                cert_params.append(data[api_key])

        if cert_updates:
            cert_params.append(employee_id)
            cur.execute(f"UPDATE identitymanagement SET {', '.join(cert_updates)} WHERE employee_id = %s", tuple(cert_params))

        db.commit()

        # 3. Return updated employee details
        return jsonify(fetch_employee_details(cur, employee_id))

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Employee update failed: {e}")
        return jsonify({"detail": f"Database error during update: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# -------------------------------------------------
# 5. DELETE /employees/{employeeId} - DELETE EMPLOYEE
# -------------------------------------------------
@employee_bp.route("/employees/<string:employee_id>", methods=["DELETE"])
@require_super_admin # Restrict deletion to SuperAdmin
@swag_from({
    "tags": ["Employees"],
    "summary": "Delete employee",
    "parameters": [{"name": "employee_id", "in": "path", "type": "string", "required": True}],
    "responses": {204: {"description": "Employee deleted"}, 404: {"description": "Employee not found"}}
})
def delete_employee(employee_id):
    db = get_db_connection(); cur = db.cursor()
    try:
        worker_info = get_employee_id_from_employee_id(cur, employee_id)
        if not worker_info: return jsonify({"detail": "Employee not found"}), 404

        employee_id = worker_info['employee_id']
        person_name = worker_info['PersonName']

        # 1. Delete DB records
        # Note: Employees may not have a user account, so deleting from Users is optional/safe.
        cur.execute("DELETE FROM identitymanagement WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM users WHERE employee_id = %s", (employee_id,))
        cur.execute("DELETE FROM workeridentity WHERE employee_id = %s", (employee_id,))

        # 2. Delete Face Data
        delete_face_data(person_name)
        touch_pkltimestamp_debounced()

        db.commit()
        return "", 204
    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Employee deletion failed: {e}")
        return jsonify({"detail": f"Database error during deletion: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# -------------------------------------------------
# 6. POST /employees/{employeeId}/faces - ENROLL FACE
# -------------------------------------------------
@employee_bp.route("/employees/<string:employee_id>/faces", methods=["POST"])
@require_admin
@swag_from({
    "tags": ["Employees"],
    "summary": "Enroll face images",
    "description": "Upload one or more face images to root/face_data/{person_name} using employee_id.",
    "consumes": ["multipart/form-data"],
    "parameters": [
        {
            "name": "employee_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Employee Badge ID (e.g., E001, 10234)"
        },
        {
            "name": "images",
            "in": "formData",
            "type": "file",
            "required": True,
            "description": "Select images to upload."
        }
    ],
    "responses": {
        "201": {
            "description": "Images saved successfully",
            "schema": {
                "type": "object",
                "properties": {
                    "msg": {"type": "string"},
                    "path": {"type": "string"},
                    "images_saved": {"type": "array", "items": {"type": "string"}}
                }
            }
        },
        "404": {"description": "employee_id not found"},
        "400": {"description": "No files provided"}
    }
})
def enroll_face(employee_id):
    db = get_db_connection()
    cur = db.cursor()
    try:
        # 1. Get PersonName directly from workeridentity using employee_id
        cur.execute("SELECT PersonName FROM workeridentity WHERE employee_id = %s", (employee_id,))
        worker = cur.fetchone()

        if not worker:
            return jsonify({"detail": f"Employee with employee_id '{employee_id}' not found"}), 404

        person_name = worker['PersonName']

        # 2. Get Files
        file_list = request.files.getlist('images')

        if not file_list or not any(f.filename for f in file_list):
            return jsonify({"detail": "At least one image file is required."}), 400

        # 3. Resolve Path: root/face_data/Person_Name
        folder_path = resolve_person_folder(person_name)

        # Create directory if it doesn't exist
        if not folder_path.exists():
            folder_path.mkdir(parents=True, exist_ok=True)
            logging.info(f"Created new face folder: {folder_path}")

        saved_files = []

        # 4. Save Files
        for f in file_list:
            if not f or not f.filename:
                continue

            # Secure the filename
            safe_name = secure_filename(f.filename)

            # Save to: root/face_data/Name/filename.jpg
            dest = folder_path / safe_name
            f.save(str(dest))
            saved_files.append(safe_name)

        if not saved_files:
            return jsonify({"detail": "No valid files were saved."}), 400

        return jsonify({
            "msg": f"{len(saved_files)} image(s) saved for {person_name} ({employee_id}).",
            "path": str(folder_path),
            "images_saved": saved_files
        }), 201

    except Exception as e:
        logging.error(f"Face enrollment error: {e}")
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close()
        db.close()


# -------------------------------------------------
# 7. GET /employees/{employeeId}/faces - LIST FACE ENCODINGS
# -------------------------------------------------
@employee_bp.route("/employees/<string:employee_id>/faces", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Employees"],
    "summary": "List face images",
    "description": "Get a list of registered face image filenames for an employee using their employee_id.",
    "parameters": [
        {
            "name": "employee_id",
            "in": "path",
            "required": True,
            "type": "string",
            "description": "Employee Badge ID (e.g., E001)"
        }
    ],
    "responses": {
        "200": {
            "description": "List of filenames",
            "schema": {
                "type": "object",
                "properties": {
                    "files": {"type": "array", "items": {"type": "string"}},
                    "count": {"type": "integer"},
                    "person_name": {"type": "string"}
                }
            }
        },
        "404": {"description": "Employee not found"}
    }
})
def list_face_images(employee_id):
    db = get_db_connection()
    cur = db.cursor()
    try:
        # 1. Get PersonName directly using employee_id
        cur.execute("SELECT PersonName FROM workeridentity WHERE employee_id = %s", (employee_id,))
        worker = cur.fetchone()

        if not worker:
            return jsonify({"detail": f"Employee with employee_id '{employee_id}' not found"}), 404

        person_name = worker['PersonName']

        # 2. Resolve folder path
        folder_path = resolve_person_folder(person_name)

        # 3. Check if folder exists
        if not folder_path.exists():
            # Valid employee, but no photos uploaded yet -> return empty list
            return jsonify({
                "files": [],
                "count": 0,
                "person_name": person_name,
                "detail": "No face data folder exists for this user yet."
            })

        # 4. List image files
        valid_extensions = {'.jpg', '.jpeg', '.png'}
        files = [
            f.name for f in folder_path.iterdir()
            if f.is_file() and f.suffix.lower() in valid_extensions
        ]

        return jsonify({
            "files": files,
            "count": len(files),
            "person_name": person_name
        })

    except Exception as e:
        logging.error(f"Error listing faces for {employee_id}: {e}")
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close()
        db.close()


# -------------------------------------------------
# 7. GET /employees/{employeeId}/faces - LIST FACE ENCODINGS
# -------------------------------------------------
@employee_bp.route("/employees/import/upload", methods=["POST"])
@require_admin
@swag_from({
    "tags": ["Employees"],
    "summary": "Bulk Import Employees",
    "description": "Upload an Excel (.xlsx) or CSV file.",
    "consumes": ["multipart/form-data"],
    "parameters": [
        {
            "name": "file",
            "in": "formData",
            "type": "file",
            "required": True,
            "description": "File with columns: person_name, employee_id, email, position, department, company, phone, access_level, cert1, cert2, cert3, cert4"
        }
    ],
    "responses": {
        "200": {"description": "Import finished"},
        "400": {"description": "Invalid file"}
    }
})
def bulk_import_employees():
    file = request.files.get('file')
    if not file:
        return jsonify({"detail": "No file uploaded"}), 400

    filename = secure_filename(file.filename) # type: ignore

    # 1. Read file
    try:
        if filename.endswith('.csv'):
            df = pd.read_csv(file) # type: ignore
        elif filename.endswith(('.xls', '.xlsx')):
            df = pd.read_excel(file)
        else:
            return jsonify({"detail": "Unsupported file format. Use .csv or .xlsx"}), 400
    except Exception as e:
        return jsonify({"detail": f"Error reading file: {str(e)}"}), 400

    # 2. Normalize headers (lowercase, strip spaces)
    df.columns = [c.strip().lower() for c in df.columns]

    # Validate required columns
    required_cols = ['person_name', 'employee_id', 'email']
    if not all(col in df.columns for col in required_cols):
        return jsonify({"detail": f"Missing columns. Found: {list(df.columns)}"}), 400

    db = get_db_connection()
    cur = db.cursor()

    success_count = 0
    errors = []

    try:
        # 3. Iterate rows
        for index, row in df.iterrows():
            # Get Required Fields
            p_name = row['person_name']
            b_id = str(row['employee_id'])
            email = row['email']

            # Skip if critical info missing
            if pd.isna(p_name) or pd.isna(b_id):
                continue

            # Get Optional Fields (with defaults)
            pos = row.get('position', 'Worker')
            dept = row.get('department', 'Operations')
            comp = row.get('company', 'QTech')
            phone = str(row.get('phone', ''))
            acc_lvl = row.get('access_level', 'Employee')

            # Handle NaN values for optionals
            pos = pos if pd.notna(pos) else 'Worker'
            dept = dept if pd.notna(dept) else 'Operations'
            comp = comp if pd.notna(comp) else 'QTech'
            acc_lvl = acc_lvl if pd.notna(acc_lvl) else 'Employee'
            phone = phone.replace('.0', '') if pd.notna(phone) else '' # Fix potential float conversion "12345.0"

            # Get Certificates (Handle all 4)
            c1 = row.get('cert1', '2035-12-31')
            c2 = row.get('cert2', 0)
            c3 = row.get('cert3', '2035-12-31') # Added
            c4 = row.get('cert4', 0)            # Added

            # Clean up dates/ints if they are NaN
            c1 = c1 if pd.notna(c1) else '2035-12-31'
            c2 = int(c2) if pd.notna(c2) else 0
            c3 = c3 if pd.notna(c3) else '2035-12-31'
            c4 = int(c4) if pd.notna(c4) else 0

            try:
                # Check duplicate
                cur.execute("SELECT 1 FROM workeridentity WHERE employee_id = %s", (b_id,))
                if cur.fetchone():
                    errors.append(f"Row {index+2}: Skipped - employee_id {b_id} exists.") # type: ignore
                    continue

                # Insert workeridentity (8 placeholders for 8 values)
                cur.execute("""
                    INSERT INTO workeridentity
                    (PersonName, employee_id, Position, Department, Company, AccessLevel, EMail, Phone, Status)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Active')
                """, (p_name, b_id, pos, dept, comp, acc_lvl, email, phone))

                # Insert identitymanagement (6 placeholders for 6 values)
                # FIX: Added Certificate3, Certificate4 and corresponding %s
                cur.execute("""
                    INSERT INTO identitymanagement
                    (PersonName, employee_id, Certificate1, Certificate2, Certificate3, Certificate4)
                    VALUES (%s, %s, %s, %s, %s, %s)
                """, (p_name, b_id, c1, c2, c3, c4))

                # Create Folder
                folder_path = resolve_person_folder(p_name)
                folder_path.mkdir(parents=True, exist_ok=True)

                db.commit()
                success_count += 1

            except Exception as row_error:
                db.rollback()
                # Log the specific error for this row
                errors.append(f"Row {index+2} ({p_name}): {str(row_error)}") # type: ignore

    except Exception as e:
        return jsonify({"detail": f"Critical error: {str(e)}"}), 500
    finally:
        cur.close()
        db.close()

    return jsonify({
        "message": "Bulk import finished",
        "total_processed": len(df),
        "success_count": success_count,
        "failed_count": len(errors),
        "errors": errors
    }), 200