from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging
from datetime import datetime, timedelta

# Import helpers
from app.decorators import require_admin
from app.database import get_db_connection

# Define the Blueprint
report_bp = Blueprint('reports', __name__)

def count_weekdays(start_date, end_date):
    """
    Calculate number of weekdays (Mon-Fri) between two dates inclusive.
    """
    days = 0
    current = start_date
    while current <= end_date:
        if current.weekday() < 5: # 0-4 are Mon-Fri
            days += 1
        current += timedelta(days=1)
    return days

# ----------------------------------------------------------------------
# Helper to fetch full employee profile data and map it to the required schema
# ----------------------------------------------------------------------
def fetch_and_map_employee_details(db_cursor, employee_id):
    """
    Fetches employee data using BadgeID (employee_id) and maps fields to the schema.
    """
    # Note: Adjust column names (WI.Employee_ID vs WI.BadgeID) to match your actual WorkerIdentity table.
    # Based on previous context, we use Employee_ID or BadgeID as the string identifier.
    db_cursor.execute("""
        SELECT
            WI.employee_id,
            WI.PersonName,
            WI.Position,
            WI.Department,
            WI.EMail,
            WI.Phone,
            WI.Status,
            IM.Certificate1
        FROM workeridentity WI
        LEFT JOIN dentitymanagement IM ON WI.employee_id = IM.employee_id
        WHERE WI.employee_id = %s
    """, (employee_id,))
    worker = db_cursor.fetchone()

    if not worker:
        return None

    # Helper to split name safely
    person_name = worker.get('PersonName', '') or ''
    name_parts = person_name.split(' ', 1)
    first_name = name_parts[0]
    last_name = name_parts[1] if len(name_parts) > 1 else ''

    # Map valid_to date
    valid_to = worker.get('Certificate1')
    if valid_to and isinstance(valid_to, datetime):
        valid_to = valid_to.strftime('%Y-%m-%d')

    # Map Status
    is_active = worker.get('Status') == 'Active'

    return {
        "employee_id": worker['employee_id'],
        "first_name": first_name,
        "last_name": last_name,
        "email": worker['EMail'],
        "phone": worker['Phone'],
        "department": worker['Department'],
        "designation": worker['Position'],
        "valid_from": None, # Placeholder
        "valid_to": valid_to,
        "shift_start_time": None, # Placeholder
        "shift_end_time": None,   # Placeholder
        "is_active": is_active,
        "created_at": None,
        "updated_at": None
    }

# ----------------------------------------------------------------------
# 2. GET /reports/attendance/{employee_id}
# ----------------------------------------------------------------------
@report_bp.route("/reports/attendance/<string:employee_id>", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Reports"],
    "summary": "Get employee attendance report",
    "description": "Calculates attendance rate based on AttendanceRecords vs expected weekdays.",
    "parameters": [
        {"name": "employee_id", "in": "path", "type": "string", "required": True, "description": "Employee Code/Badge ID"},
        {"name": "start_date", "in": "query", "type": "string", "format": "date", "required": True, "example": "2023-11-01"},
        {"name": "end_date", "in": "query", "type": "string", "format": "date", "required": True, "example": "2023-11-30"}
    ],
    "responses": {
        200: {
            "description": "Attendance report",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "employee": {
                                "type": "object",
                                "properties": {
                                    "employee_id": {"type": "string"},
                                    "first_name": {"type": "string"},
                                    "last_name": {"type": "string"},
                                    "email": {"type": "string"},
                                    "phone": {"type": "string"},
                                    "department": {"type": "string"},
                                    "designation": {"type": "string"},
                                    "valid_from": {"type": "string"},
                                    "valid_to": {"type": "string"},
                                    "shift_start_time": {"type": "string"},
                                    "shift_end_time": {"type": "string"},
                                    "is_active": {"type": "boolean"},
                                    "created_at": {"type": "string"},
                                    "updated_at": {"type": "string"}
                                }
                            },
                            "period": {
                                "type": "object",
                                "properties": {
                                    "start_date": {"type": "string", "format": "date"},
                                    "end_date": {"type": "string", "format": "date"}
                                }
                            },
                            "summary": {
                                "type": "object",
                                "properties": {
                                    "total_expected_days": {"type": "integer"},
                                    "total_present_days": {"type": "integer"},
                                    "attendance_rate": {"type": "number"}
                                }
                            }
                        }
                    }
                }
            }
        },
        404: {"description": "Employee not found"}
    }
})
def get_attendance_report(employee_id):
    # 1. Parse Dates
    start_str = request.args.get('start_date')
    end_str = request.args.get('end_date')

    if not start_str or not end_str:
        return jsonify({"detail": "start_date and end_date query parameters are required."}), 400

    try:
        start_date = datetime.strptime(start_str, '%Y-%m-%d').date()
        end_date = datetime.strptime(end_str, '%Y-%m-%d').date()
    except ValueError:
        return jsonify({"detail": "Invalid date format. Use YYYY-MM-DD."}), 400

    if start_date > end_date:
        return jsonify({"detail": "start_date cannot be after end_date."}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        # 2. Fetch Employee Details using the employee_code (BadgeID)
        employee_details = fetch_and_map_employee_details(cur, employee_id)

        if not employee_details:
            return jsonify({"detail": f"Employee with code {employee_id} not found"}), 404

        # 3. Calculate Attendance Stats from AttendanceRecords
        # We count distinct days where records exist for this employee within the range.
        cur.execute("""
            SELECT COUNT(DISTINCT DATE(timestamp)) as days_present
            FROM attendancerecords
            WHERE employee_id = %s
            AND DATE(timestamp) BETWEEN %s AND %s
        """, (employee_id, start_date, end_date))

        result = cur.fetchone()
        present_days = result['days_present'] if result else 0
        present_days = int(present_days/2)

        # Calculate expected days (Weekdays only)
        expected_days = count_weekdays(start_date, end_date)

        # Avoid division by zero
        attendance_rate = 0.0
        if expected_days > 0:
            attendance_rate = round((present_days / expected_days) * 100, 2)
        elif present_days > 0:
            # Edge case: Weekend work but 0 expected weekdays
            attendance_rate = 100.0

        return jsonify({
            "employee": employee_details,
            "period": {
                "start_date": start_str,
                "end_date": end_str
            },
            "summary": {
                "total_expected_days": expected_days,
                "total_present_days": present_days,
                "attendance_rate": f'{attendance_rate} %'
            }
        })

    except pymysql.MySQLError as e:
        logging.error(f"Report generation failed: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()