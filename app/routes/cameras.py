from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging
from datetime import datetime

# Import helpers
from app.decorators import require_admin
from app.database import get_db_connection

# Define the Blueprint
camera_bp = Blueprint('camera', __name__)
logging.basicConfig(level=logging.INFO)

def format_camera_response(row):
    if not row:
        return None

    # Construct the nested Area object if area_id exists
    area_obj = None
    if row.get('areaId'):
        area_obj = {
            "areaId": row.get('area_pk'),
            "name": row.get('area_name'),
            "description": row.get('area_description'),
            "parent_area_id": row.get('area_parent_id') or 0,
            "created_at": row.get('area_created_at'),
            "updated_at": row.get('area_updated_at')
        }

    return {
        "cameraId": row['cameraId'],
        "name": row['name'],
        "rtsp_url": row['rtsp_url'],
        "areaId": row['areaId'] or 0,
        "area": area_obj,
        "location_description": row['location_description'],
        "camera_type": row['camera_type'],
        "resolution": row['resolution'],
        "fps": row['fps'],
        "is_active": bool(row['is_active']),
        "status": row['status'],
        "last_health_check_at": row['last_health_check_at'],
        "created_at": row['created_at'],
        "updated_at": row['updated_at']
    }

# ----------------------------------------------------------------------
# 1. GET /cameras - LIST CAMERAS
# ----------------------------------------------------------------------
@camera_bp.route("/cameras", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Cameras"],
    "summary": "List cameras",
    "description": "Retrieve a list of all cameras with optional filtering.",
    "parameters": [
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "limit", "in": "query", "type": "integer", "default": 20},
        {"name": "areaId", "in": "query", "type": "integer", "description": "Filter by Area ID"},
        {"name": "status", "in": "query", "type": "string", "enum": ["online", "offline", "error", "maintenance"]},
        {"name": "camera_type", "in": "query", "type": "string", "enum": ["entrance", "exit", "zone", "ppe_check"]}
    ],
    "responses": {
        200: {
            "description": "List of cameras",
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
                                        "cameraId": {"type": "integer", "example": 101},
                                        "name": {"type": "string", "example": "Main Entrance Cam"},
                                        "rtsp_url": {"type": "string", "example": "rtsp://192.168.1.50:554/stream1"},
                                        "areaId": {"type": "integer", "example": 5},
                                        "area": {
                                            "type": "object",
                                            "properties": {
                                                "areaId": {"type": "integer"},
                                                "name": {"type": "string"},
                                                "description": {"type": "string"},
                                                "parent_area_id": {"type": "integer"},
                                                "created_at": {"type": "string", "format": "date-time"},
                                                "updated_at": {"type": "string", "format": "date-time"}
                                            }
                                        },
                                        "location_description": {"type": "string", "example": "Mounted on ceiling"},
                                        "camera_type": {"type": "string", "example": "entrance"},
                                        "resolution": {"type": "string"},
                                        "fps": {"type": "integer"},
                                        "status": {"type": "string", "example": "online"},
                                        "is_active": {"type": "boolean", "example": True},
                                        "last_health_check_at": {"type": "string", "format": "date-time"},
                                        "created_at": {"type": "string", "format": "date-time"},
                                        "updated_at": {"type": "string", "format": "date-time"}
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
def list_cameras():
    # Parse Query Params
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    areaId = request.args.get('areaId', type=int)
    status = request.args.get('status')
    camera_type = request.args.get('camera_type')

    offset = (page - 1) * limit

    # Build Query
    where_clauses = ["1=1"]
    params = []

    if areaId:
        where_clauses.append("C.areaId = %s")
        params.append(areaId)
    if status:
        where_clauses.append("C.status = %s")
        params.append(status)
    if camera_type:
        where_clauses.append("C.camera_type = %s")
        params.append(camera_type)

    where_sql = " AND ".join(where_clauses)

    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Get Total Count
        cur.execute(f"SELECT COUNT(*) as total FROM cameras C WHERE {where_sql}", tuple(params))
        total = cur.fetchone()['total'] # type: ignore

        # 2. Get Data
        # Directly selecting 'cameraId' as it is now the column name
        sql = f"""
            SELECT
                C.cameraId, C.name, C.rtsp_url, C.areaId as areaId,
                C.location_description, C.camera_type, C.resolution, C.fps,
                C.is_active, C.status, C.last_health_check_at, C.created_at, C.updated_at,
                A.areaId as area_pk, A.name as area_name, A.description as area_description,
                A.parent_area_id as area_parent_id, A.created_at as area_created_at, A.updated_at as area_updated_at
            FROM cameras C
            LEFT JOIN areas A ON C.areaId = A.areaId
            WHERE {where_sql}
            ORDER BY C.name
            LIMIT %s OFFSET %s
        """
        cur.execute(sql, tuple(params + [limit, offset]))
        rows = cur.fetchall()

        # Format rows using the helper
        cameras = [format_camera_response(row) for row in rows]
        total_pages = (total + limit - 1) // limit if total > 0 else 0
        return jsonify({
            "data": cameras,
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages
        })

    except pymysql.MySQLError as e:
        logging.error(f"Failed to list cameras: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------------------
# 2. POST /cameras - CREATE CAMERA
# ----------------------------------------------------------------------
@camera_bp.route("/cameras", methods=["POST"])
@require_admin
@swag_from({
    "tags": ["Cameras"],
    "summary": "Create camera",
    "description": "Register a new camera device.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["name", "rtsp_url", "camera_type"],
                "properties": {
                    "name": {"type": "string", "example": "Entrance Cam 1"},
                    "rtsp_url": {"type": "string", "example": "rtsp://admin:12345@192.168.1.100:554/h264"},
                    "areaId": {"type": "integer", "example": 1, "description": "ID of the area this camera monitors"},
                    "location_description": {"type": "string", "example": "Mounted on North Wall"},
                    "camera_type": {"type": "string", "enum": ["entrance", "exit", "zone", "ppe_check"]},
                    "resolution": {"type": "string", "default": "1080p"},
                    "fps": {"type": "integer", "default": 15},
                    "is_active": {"type": "boolean", "default": True}
                }
            }
        }
    ],
    "responses": {
        201: {
            "description": "Camera created",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "cameraId": {"type": "integer"},
                            "name": {"type": "string"},
                            "status": {"type": "string", "example": "offline"}
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid input"},
        409: {"description": "Camera name already exists"}
    }
})
def create_camera():
    data = request.get_json()
    if not data:
        return jsonify({"detail": "Invalid JSON body"}), 400

    # Required Fields
    name = data.get("name")
    rtsp_url = data.get("rtsp_url")
    camera_type = data.get("camera_type")

    # Optional Fields
    areaId = data.get("areaId") # Maps to areaId
    location_desc = data.get("location_description", "")
    resolution = data.get("resolution", "1080p")
    fps = data.get("fps", 15)
    is_active = data.get("is_active", True)

    if not all([name, rtsp_url, camera_type]):
        return jsonify({"detail": "Missing required fields: name, rtsp_url, camera_type"}), 400

    # Convert areaId to int or None
    if areaId is not None:
        try:
            areaId = int(areaId)
            if areaId == 0: areaId = None
        except ValueError:
             return jsonify({"detail": "areaId must be a valid integer."}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Check Duplicates
        cur.execute("SELECT cameraId FROM cameras WHERE name = %s", (name,))
        if cur.fetchone():
            return jsonify({"detail": f"Camera '{name}' already exists."}), 409

        # 2. Check Area Existence (Foreign Key Safety)
        if areaId:
            cur.execute("SELECT areaId FROM Areas WHERE areaId = %s", (areaId,))
            if not cur.fetchone():
                return jsonify({"detail": f"Area ID {areaId} not found."}), 400

        # 3. Insert Camera
        cur.execute("""
            INSERT INTO cameras
            (name, rtsp_url, areaId, location_description, camera_type, resolution, fps, is_active, status)
            VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'offline')
        """, (name, rtsp_url, areaId, location_desc, camera_type, resolution, fps, is_active))

        new_id = cur.lastrowid
        db.commit()

        sql = """
            SELECT
                C.cameraId, C.name, C.rtsp_url, C.areaId,
                C.location_description, C.camera_type, C.resolution, C.fps,
                C.is_active, C.status, C.last_health_check_at, C.created_at, C.updated_at,
                A.areaId as area_pk, A.name as area_name, A.description as area_description,
                A.parent_area_id as area_parent_id, A.created_at as area_created_at, A.updated_at as area_updated_at
            FROM cameras C
            LEFT JOIN areas A ON C.areaId = A.areaId
            WHERE C.cameraId = %s
        """
        cur.execute(sql, (new_id,))
        row = cur.fetchone()

        return jsonify(format_camera_response(row)), 201

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Failed to create camera: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

    # ----------------------------------------------------------------------

# ----------------------------------------------------------------------
# 3. GET /cameras/{cameraId} - GET CAMERA BY ID
# ----------------------------------------------------------------------
@camera_bp.route("/cameras/<int:camera_id>", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Cameras"],
    "summary": "Get camera by ID",
    "parameters": [{"name": "camera_id", "in": "path", "type": "integer", "required": True}],
    "responses": {
        200: {
            "description": "Camera details",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "cameraId": {"type": "integer"},
                            "name": {"type": "string"},
                            "rtsp_url": {"type": "string"},
                            "area_id": {"type": "integer"},
                            "area": {
                                "type": "object",
                                "properties": {
                                    "areaId": {"type": "integer"},
                                    "name": {"type": "string"},
                                    "description": {"type": "string"},
                                    "parent_area_id": {"type": "integer"},
                                    "created_at": {"type": "string", "format": "date-time"},
                                    "updated_at": {"type": "string", "format": "date-time"}
                                }
                            },
                            "location_description": {"type": "string"},
                            "camera_type": {"type": "string"},
                            "resolution": {"type": "string"},
                            "fps": {"type": "integer"},
                            "is_active": {"type": "boolean"},
                            "status": {"type": "string"},
                            "last_health_check_at": {"type": "string", "format": "date-time"},
                            "created_at": {"type": "string", "format": "date-time"},
                            "updated_at": {"type": "string", "format": "date-time"},
                            "recent_health_checks": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "ch_id": {"type": "integer"},
                                        "camera_id": {"type": "integer"},
                                        "status": {"type": "string"},
                                        "checked_at": {"type": "string", "format": "date-time"},
                                        "response_time_ms": {"type": "integer"},
                                        "error_details": {"type": "string"}
                                    }
                                }
                            },
                            "uptime_24h": {"type": "number", "format": "float"}
                        }
                    }
                }
            }
        },
        404: {"description": "Camera not found"}
    }
})
def get_camera(camera_id):
    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Fetch Basic Camera Info + Area
        sql = """
            SELECT
                C.cameraId, C.name, C.rtsp_url, C.areaId,
                C.location_description, C.camera_type, C.resolution, C.fps,
                C.is_active, C.status, C.last_health_check_at, C.created_at, C.updated_at,
                A.areaId as area_pk, A.name as area_name, A.description as area_description,
                A.parent_area_id as area_parent_id, A.created_at as area_created_at, A.updated_at as area_updated_at
            FROM cameras C
            LEFT JOIN areas A ON C.areaId = A.areaId
            WHERE C.cameraId = %s
        """
        cur.execute(sql, (camera_id,))
        row = cur.fetchone()

        if not row:
            return jsonify({"detail": "Camera not found"}), 404

        # 2. Fetch Recent Health Checks (Last 10)
        health_checks = []
        uptime_24h = 0
        try:
            # Map 'id' to 'ch_id' explicitly in the query
            cur.execute("""
                SELECT
                    id as ch_id,
                    camera_id,
                    status,
                    checked_at,
                    response_time_ms,
                    error_details
                FROM camerahealthlogs
                WHERE camera_id = %s
                ORDER BY checked_at DESC
                LIMIT 10
            """, (camera_id,))
            health_checks = cur.fetchall()

            # 3. Calculate 24h Uptime
            cur.execute("""
                SELECT
                    COUNT(*) as total_checks,
                    SUM(CASE WHEN status = 'online' THEN 1 ELSE 0 END) as online_checks
                FROM camerahealthlogs
                WHERE camera_id = %s AND checked_at >= NOW() - INTERVAL 1 DAY
            """, (camera_id,))
            stats = cur.fetchone()

            if stats and stats['total_checks'] > 0:
                uptime_24h = (stats['online_checks'] / stats['total_checks']) * 100
            else:
                uptime_24h = 0 if not health_checks else 100

        except Exception as e:
            logging.warning(f"Health logs query failed (table might be missing): {e}")
            health_checks = []
            uptime_24h = 0

        # 4. Construct Response (Exact format requested)
        area_obj = None
        if row.get('areaId'):
            area_obj = {
                "areaId": row.get('area_pk'),
                "name": row.get('area_name'),
                "description": row.get('area_description'),
                "parent_area_id": row.get('area_parent_id') or 0,
                "created_at": row.get('area_created_at'),
                "updated_at": row.get('area_updated_at')
            }

        response = {
            "cameraId": row['cameraId'],
            "name": row['name'],
            "rtsp_url": row['rtsp_url'],
            "areaId": row['areaId'] or 0,
            "area": area_obj,
            "location_description": row['location_description'],
            "camera_type": row['camera_type'],
            "resolution": row['resolution'],
            "fps": row['fps'],
            "is_active": bool(row['is_active']),
            "status": row['status'],
            "last_health_check_at": row['last_health_check_at'],
            "created_at": row['created_at'],
            "updated_at": row['updated_at'],
            "recent_health_checks": health_checks,
            "uptime_24h": round(uptime_24h, 2)
        }

        return jsonify(response)

    except pymysql.MySQLError as e:
        logging.error(f"Failed to get camera: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------------------
# 4. PUT /cameras/{cameraId} - UPDATE CAMERA
# ----------------------------------------------------------------------
@camera_bp.route("/cameras/<int:camera_id>", methods=["PUT"])
@require_admin
@swag_from({
    "tags": ["Cameras"],
    "summary": "Update camera",
    "parameters": [
        {"name": "camera_id", "in": "path", "type": "integer", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "rtsp_url": {"type": "string"},
                    "areaId": {"type": "integer"},
                    "location_description": {"type": "string"},
                    "camera_type": {"type": "string", "enum": ["entrance", "exit", "zone", "ppe_check"]},
                    "resolution": {"type": "string"},
                    "fps": {"type": "integer"},
                    "is_active": {"type": "boolean"}
                }
            }
        }
    ],
    "responses": {
        200: {
            "description": "Camera updated",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "cameraId": {"type": "integer"},
                            "name": {"type": "string"},
                            "status": {"type": "string"}
                        }
                    }
                }
            }
        },
        404: {"description": "Camera not found"}
    }
})
def update_camera(camera_id):
    data = request.get_json()
    if not data: return jsonify({"detail": "Invalid JSON body"}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("SELECT cameraId FROM cameras WHERE cameraId = %s", (camera_id,))
        if not cur.fetchone():
            return jsonify({"detail": "Camera not found"}), 404
        cur.fetchall()

        updates = []
        params = []

        fields_map = {
            'name': 'name',
            'rtsp_url': 'rtsp_url',
            'location_description': 'location_description',
            'camera_type': 'camera_type',
            'resolution': 'resolution',
            'fps': 'fps',
            'is_active': 'is_active',
            'status': 'status'
        }

        for api_key, db_col in fields_map.items():
            if api_key in data:
                updates.append(f"{db_col} = %s")
                params.append(data[api_key])

        # Handle areaId specially
        areaId = data.get('areaId')
        if 'areaId' in data:
            if areaId is not None:
                try:
                    areaId = int(areaId)
                    if areaId == 0: areaId = None
                except ValueError:
                    return jsonify({"detail": "areaId must be valid integer"}), 400

                if areaId is not None:
                    cur.execute("SELECT areaId FROM Areas WHERE areaId = %s", (areaId,))
                    if not cur.fetchone():
                        return jsonify({"detail": f"Area ID {areaId} not found"}), 400
                    cur.fetchall()

            updates.append("areaId = %s")
            params.append(areaId)

        if not updates:
            return jsonify({"detail": "No fields to update"}), 400

        params.append(camera_id)
        sql = f"UPDATE cameras SET {', '.join(updates)} WHERE cameraId = %s"
        cur.execute(sql, tuple(params))
        db.commit()

        # Return updated record using the list format
        sql_fetch = """
            SELECT
                C.cameraId, C.name, C.rtsp_url, C.areaId,
                C.location_description, C.camera_type, C.resolution, C.fps,
                C.is_active, C.status, C.last_health_check_at, C.created_at, C.updated_at,
                A.areaId as area_pk, A.name as area_name, A.description as area_description,
                A.parent_area_id as area_parent_id, A.created_at as area_created_at, A.updated_at as area_updated_at
            FROM cameras C
            LEFT JOIN areas A ON C.areaId = A.areaId
            WHERE C.cameraId = %s
        """
        cur.execute(sql_fetch, (camera_id,))
        row = cur.fetchone()

        return jsonify(format_camera_response(row))

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Failed to update camera: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

    # ----------------------------------------------------------------------
# 5. DELETE /cameras/{cameraId} - DELETE CAMERA
# ----------------------------------------------------------------------
@camera_bp.route("/cameras/<int:camera_id>", methods=["DELETE"])
@require_admin
@swag_from({
    "tags": ["Cameras"],
    "summary": "Delete camera",
    "parameters": [{"name": "camera_id", "in": "path", "type": "integer", "required": True}],
    "responses": {
        204: {"description": "Camera deleted"},
        404: {"description": "Camera not found"}
    }
})
def delete_camera(camera_id):
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("SELECT cameraId FROM cameras WHERE cameraId = %s", (camera_id,))
        if not cur.fetchone():
            return jsonify({"detail": "Camera not found"}), 404

        cur.execute("DELETE FROM cameras WHERE cameraId = %s", (camera_id,))
        db.commit()

        return "", 204

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Failed to delete camera: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()