from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging
from datetime import datetime

# Import helpers
from app.decorators import require_admin
from app.database import get_db_connection

# Define the Blueprint
attendance_bp = Blueprint('attendance', __name__)
logging.basicConfig(level=logging.INFO)

# ----------------------------------------------------------------------
# 1. GET /attendance - LIST ATTENDANCE RECORDS
# ----------------------------------------------------------------------
@attendance_bp.route("/attendance", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Attendance"],
    "summary": "List attendance records",
    "parameters": [
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "limit", "in": "query", "type": "integer", "default": 20},
        {"name": "employee_id", "in": "query", "type": "integer", "description": "Filter by Employee Internal ID"},
        {"name": "start_date", "in": "query", "type": "string", "format": "date"},
        {"name": "end_date", "in": "query", "type": "string", "format": "date"}
    ],
    "responses": {
        200: {
            "description": "List of attendance records",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "page": {"type": "integer"},
                            "limit": {"type": "integer"},
                            "total": {"type": "integer"},
                            "total_pages": {"type": "integer"},
                            "data": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "ar_id": {"type": "integer"},
                                        "employee_id": {"type": "integer"},
                                        "employee": {"type": "object"},
                                        "cameraId": {"type": "integer"},
                                        "camera": {"type": "object"},
                                        "event_type": {"type": "string"},
                                        "timestamp": {"type": "string", "format": "date-time"},
                                        "confidence_score": {"type": "number"},
                                        "snapshot_url": {"type": "string"},
                                        "created_at": {"type": "string", "format": "date-time"}
                                    }
                                }
                            }
                        }
                    }
                }
            }
        }
    }
})
def list_attendance():
    # Parse Query Params
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    employee_id = request.args.get('employee_id', type=int)
    start_date = request.args.get('start_date')
    end_date = request.args.get('end_date')

    offset = (page - 1) * limit

    # Build Filter Query
    # Note: We filter on WorkerIdentity ID for employee_id if provided
    where_clauses = ["1=1"]
    params = []

    if employee_id:
        where_clauses.append("W.employee_id = %s")
        params.append(employee_id)

    if start_date:
        where_clauses.append("DATE(A.timestamp) >= %s")
        params.append(start_date)

    if end_date:
        where_clauses.append("DATE(A.timestamp) <= %s")
        params.append(end_date)

    where_sql = " AND ".join(where_clauses)

    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Get Total Count
        # We need to join WorkerIdentity to filter by employee_id correctly if it's passed
        count_sql = f"""
            SELECT COUNT(*) as total
            FROM attendancerecords A
            LEFT JOIN workeridentity W ON A.employee_id = W.employee_id
            WHERE {where_sql}
        """
        cur.execute(count_sql, tuple(params))
        total = cur.fetchone()['total'] # type: ignore

        # 2. Get Data with Multiple Joins (Worker, Camera, Area)
        # Note: Assuming AttendanceRecords has a cameraId column.
        # If not, camera fields will be null.
        sql = f"""
            SELECT
                A.ar_id as ar_id,
                A.event_type,
                A.timestamp,
                A.confidence_score,
                A.snapshot_url,
                A.created_at,
                -- Employee Details
                W.employee_id as emp_pk,
                W.PersonName,
                W.EMail,
                W.Phone,
                W.Department,
                W.Position,
                W.Status as emp_status,
                -- Camera Details (Assuming cameraId exists in A, otherwise these match nothing)
                A.cameraId,
                C.name as cam_name,
                C.rtsp_url,
                C.location_description as cam_loc,
                C.camera_type,
                C.resolution,
                C.fps,
                C.is_active as cam_active,
                C.status as cam_status,
                C.last_health_check_at,
                C.created_at as cam_created,
                C.updated_at as cam_updated,
                -- Area Details
                C.areaId,
                Ar.name as area_name,
                Ar.description as area_desc,
                Ar.parent_area_id,
                Ar.created_at as area_created,
                Ar.updated_at as area_updated
            FROM attendancerecords A
            LEFT JOIN workeridentity W ON A.employee_id = W.employee_id
            LEFT JOIN cameras C ON A.cameraId = C.cameraId
            LEFT JOIN areas Ar ON C.areaId = Ar.areaId
            WHERE {where_sql}
            ORDER BY A.timestamp DESC
            LIMIT %s OFFSET %s
        """
        cur.execute(sql, tuple(params + [limit, offset]))
        rows = cur.fetchall()

        # Format Data
        formatted_rows = []
        for row in rows:
            # Helper to split name
            person_name = row.get('PersonName', '') or ''
            name_parts = person_name.split(' ', 1)
            first_name = name_parts[0]
            last_name = name_parts[1] if len(name_parts) > 1 else ''

            # Construct Nested Employee Object
            employee_obj = {
                "employee_id": row.get('emp_pk') or 0,
                "first_name": first_name,
                "last_name": last_name,
                "email": row.get('EMail'),
                "phone": row.get('Phone'),
                "department": row.get('Department'),
                "designation": row.get('Position'),
                "valid_from": None, # Placeholder: Needs IdentityManagement join if required
                "valid_to": None,   # Placeholder
                "shift_start_time": None, # Placeholder
                "shift_end_time": None,   # Placeholder
                "is_active": row.get('emp_status') == 'Active',
                "created_at": None, # Not strictly tracked in WorkerIdentity usually
                "updated_at": None
            }

            # Construct Nested Area Object
            area_obj = None
            if row.get('areaId'):
                area_obj = {
                    "areaId": row.get('areaId'),
                    "name": row.get('area_name'),
                    "description": row.get('area_desc'),
                    "parent_area_id": row.get('parent_area_id') or 0,
                    "created_at": row.get('area_created'),
                    "updated_at": row.get('area_updated')
                }

            # Construct Nested Camera Object
            camera_obj = None
            if row.get('cameraId'):
                camera_obj = {
                    "cameraId": row.get('cameraId'),
                    "name": row.get('cam_name'),
                    "rtsp_url": row.get('rtsp_url'),
                    "areaId": row.get('areaId') or 0,
                    "area": area_obj,
                    "location_description": row.get('cam_loc'),
                    "camera_type": row.get('camera_type'),
                    "resolution": row.get('resolution'),
                    "fps": row.get('fps'),
                    "is_active": bool(row.get('cam_active')),
                    "status": row.get('cam_status'),
                    "last_health_check_at": row.get('last_health_check_at'),
                    "created_at": row.get('cam_created'),
                    "updated_at": row.get('cam_updated')
                }

            # Main Record
            formatted_rows.append({
                "ar_id": row['ar_id'],
                "employee_id": row.get('emp_pk') or 0,
                "employee": employee_obj,
                "cameraId": row.get('cameraId') or 0,
                "camera": camera_obj,
                "event_type": row['event_type'],
                "timestamp": row['timestamp'],
                "confidence_score": row['confidence_score'] or 0,
                "snapshot_url": row['snapshot_url'] or "",
                "created_at": row['created_at']
            })

        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return jsonify({
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "data": formatted_rows
        })

    except pymysql.MySQLError as e:
        logging.error(f"Failed to list attendance: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------------------
# 2. GET /attendance/{ar_id} - GET ATTENDANCE RECORD BY ID
# ----------------------------------------------------------------------
@attendance_bp.route("/attendance/<int:ar_id>", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Attendance"],
    "summary": "Get attendance record by ID",
    "parameters": [{"name": "ar_id", "in": "path", "type": "integer", "required": True}],
    "responses": {
        200: {
            "description": "Attendance record details",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "ar_id": {"type": "integer"},
                            "employee_id": {"type": "integer"},
                            "employee": {"type": "object"},
                            "cameraId": {"type": "integer"},
                            "camera": {"type": "object"},
                            "event_type": {"type": "string"},
                            "timestamp": {"type": "string", "format": "date-time"},
                            "confidence_score": {"type": "number"},
                            "snapshot_url": {"type": "string"},
                            "created_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
        },
        404: {"description": "Attendance record not found"}
    }
})
def get_attendance_record(ar_id):
    db = get_db_connection(); cur = db.cursor()
    try:
        sql = """
            SELECT
                A.ar_id as ar_id,
                A.event_type,
                A.timestamp,
                A.confidence_score,
                A.snapshot_url,
                A.created_at,
                -- Employee Details
                W.employee_id as emp_pk,
                W.PersonName,
                W.EMail,
                W.Phone,
                W.Department,
                W.Position,
                W.Status as emp_status,
                -- Camera Details
                A.cameraId,
                C.name as cam_name,
                C.rtsp_url,
                C.location_description as cam_loc,
                C.camera_type,
                C.resolution,
                C.fps,
                C.is_active as cam_active,
                C.status as cam_status,
                C.last_health_check_at,
                C.created_at as cam_created,
                C.updated_at as cam_updated,
                -- Area Details
                C.areaId,
                Ar.name as area_name,
                Ar.description as area_desc,
                Ar.parent_area_id,
                Ar.created_at as area_created,
                Ar.updated_at as area_updated
            FROM attendancerecords A
            LEFT JOIN workeridentity W ON A.employee_id = W.employee_id
            LEFT JOIN cameras C ON A.cameraId = C.cameraId
            LEFT JOIN areas Ar ON C.areaId = Ar.areaId
            WHERE A.ar_id = %s
        """
        cur.execute(sql, (ar_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({"detail": "Attendance record not found"}), 404

        def fmt_dt(dt):
            return dt.isoformat() if isinstance(dt, datetime) else dt

        # Helper to split name
        person_name = row.get('PersonName', '') or ''
        name_parts = person_name.split(' ', 1)
        first_name = name_parts[0]
        last_name = name_parts[1] if len(name_parts) > 1 else ''

        # Construct Nested Employee Object
        employee_obj = {
            "employee_id": row.get('emp_pk') or 0,
            "first_name": first_name,
            "last_name": last_name,
            "email": row.get('EMail'),
            "phone": row.get('Phone'),
            "department": row.get('Department'),
            "designation": row.get('Position'),
            "valid_from": None,
            "valid_to": None,
            "shift_start_time": None,
            "shift_end_time": None,
            "is_active": row.get('emp_status') == 'Active',
            "created_at": None,
            "updated_at": None
        }

        # Construct Nested Area Object
        area_obj = None
        if row.get('areaId'):
            area_obj = {
                "areaId": row.get('areaId'),
                "name": row.get('area_name'),
                "description": row.get('area_desc'),
                "parent_area_id": row.get('parent_area_id') or 0,
                "created_at": row.get('area_created'),
                "updated_at": row.get('area_updated')
            }

        # Construct Nested Camera Object
        camera_obj = None
        if row.get('cameraId'):
            camera_obj = {
                "cameraId": row.get('cameraId'),
                "name": row.get('cam_name'),
                "rtsp_url": row.get('rtsp_url'),
                "areaId": row.get('areaId') or 0,
                "area": area_obj,
                "location_description": row.get('cam_loc'),
                "camera_type": row.get('camera_type'),
                "resolution": row.get('resolution'),
                "fps": row.get('fps'),
                "is_active": bool(row.get('cam_active')),
                "status": row.get('cam_status'),
                "last_health_check_at": row.get('last_health_check_at'),
                "created_at": row.get('cam_created'),
                "updated_at": row.get('cam_updated')
            }

        # Construct Final Response
        response = {
            "ar_id": row['ar_id'],
            "employee_id": row.get('emp_pk') or 0,
            "employee": employee_obj,
            "cameraId": row.get('cameraId') or 0,
            "camera": camera_obj,
            "event_type": row['event_type'],
            "timestamp": row['timestamp'],
            "confidence_score": row['confidence_score'] or 0,
            "snapshot_url": row['snapshot_url'] or "",
            "created_at": row['created_at']
        }

        return jsonify(response)

    except pymysql.MySQLError as e:
        logging.error(f"Failed to get attendance record: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()