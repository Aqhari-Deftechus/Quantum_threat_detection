from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging
from datetime import datetime

# Import helpers
from app.decorators import require_admin
from app.database import get_db_connection

# Define the Blueprint
area_bp = Blueprint('areas', __name__)
logging.basicConfig(level=logging.INFO)

# ----------------------------------------------------------------------
# 1. GET /areas - LIST AREAS
# ----------------------------------------------------------------------
@area_bp.route("/areas", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Areas"],
    "summary": "List areas",
    "description": "Retrieve a list of all defined operational areas.",
    "responses": {
        200: {
            "description": "List of areas",
            "schema": {
                "type": "array",
                "properties": {
                                "areaId": {"type": "integer", "example": 1},
                                "name": {"type": "string", "example": "Warehouse A"},
                                "description": {"type": "string", "example": "Main storage facility"},
                                "parent_area_Id": {"type": "integer", "example": 0},
                                "created_at": {"type": "string", "format": "date-time", "example": "2025-12-04T07:50:28.908Z"},
                                "updated_at": {"type": "string", "format": "date-time", "example": "2025-12-04T07:50:28.908Z"}
                            }
            }
        }
    }
})
def list_areas():
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("""
            SELECT
                areaId, name, description, parent_area_Id, created_at, updated_at
            FROM areas
            ORDER BY name
        """)
        areas = cur.fetchall()

        # NOTE: For a production environment, you might want to fetch camera_count and cameras_online here
        # to satisfy the AreaDetail schema if this endpoint is expected to return full detail.

        return jsonify(areas)

    except pymysql.MySQLError as e:
        logging.error(f"Failed to list areas: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------------------
# 2. POST /areas - CREATE AREA
# ----------------------------------------------------------------------
@area_bp.route("/areas", methods=["POST"])
@require_admin
@swag_from({
    "tags": ["Areas"],
    "summary": "Create area",
    "description": "Create a new operational area, optionally specifying a parent area.",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["name"],
                "properties": {
                    "name": {"type": "string", "example": "Assembly Line 1"},
                    "description": {"type": "string", "example": "Main production line"},
                    "parent_area_Id": {"type": "integer", "default": 0, "example": 0}
                }
            }
        }
    ],
    "responses": {
        201: {
            "description": "Area created",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "areaId": {"type": "integer", "example": 1},
                            "name": {"type": "string", "example": "Assembly Line 1"},
                            "description": {"type": "string", "example": "Main production line"},
                            "parent_area_Id": {"type": "integer", "example": 0},
                            "created_at": {"type": "string", "format": "date-time", "example": "2025-12-04T07:50:28.908Z"},
                            "updated_at": {"type": "string", "format": "date-time", "example": "2025-12-04T07:50:28.908Z"}
                        }
                    }
                }
            }
        },
        400: {"description": "Invalid input"},
        409: {"description": "Area name already exists"}
    }
})
def create_area():
    data = request.get_json()
    if not data:
        return jsonify({"detail": "Invalid JSON body"}), 400

    name = data.get("name")
    description = data.get("description", "")
    parent_area_Id = data.get("parent_area_Id")

    if not name:
        return jsonify({"detail": "Area name is required"}), 400

    if parent_area_Id is not None:
        try:
            parent_area_Id = int(parent_area_Id)
        except ValueError:
            return jsonify({"detail": "Parent Area ID must be a valid integer."}), 400

    # Treat 0 as None (Root Area) for database insertion
    if parent_area_Id == 0:
        parent_area_Id = None

    db = get_db_connection(); cur = db.cursor()
    try:
        # Check for duplicate name
        cur.execute("SELECT name FROM areas WHERE name = %s", (name,))
        if cur.fetchone():
            return jsonify({"detail": f"Area name '{name}' already exists."}), 409

        # Check if parent_area_Id exists, if provided
        if parent_area_Id is not None:
            cur.execute("SELECT areaId FROM areas WHERE areaId = %s", (parent_area_Id,))
            if not cur.fetchone():
                return jsonify({"detail": f"Parent Area ID {parent_area_Id} not found."}), 400

        # Insert the new area
        cur.execute("""
            INSERT INTO areas (name, description, parent_area_Id)
            VALUES (%s, %s, %s)
        """, (name, description, parent_area_Id))

        new_id = cur.lastrowid
        db.commit()

        # Fetch the newly created record to return
        cur.execute("SELECT areaId, name, description, parent_area_Id, created_at, updated_at FROM areas WHERE areaId = %s", (new_id,))
        new_area = cur.fetchone()

        return jsonify(new_area), 201

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Failed to create area: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------------------
# 3. GET /areas/areaId - GET AREA BY ID
# ----------------------------------------------------------------------
@area_bp.route("/areas/<int:areaId>", methods=["GET"])
@require_admin
@swag_from({
    "tags": ["Areas"],
    "summary": "Get area by ID",
    "parameters": [
        {"name": "areaId", "in": "path", "type": "integer", "required": True}
    ],
    "responses": {
        200: {
            "description": "Area details",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "areaId": {"type": "integer"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "parent_area_id": {"type": "integer"},
                            "created_at": {"type": "string", "format": "date-time"},
                            "updated_at": {"type": "string", "format": "date-time"},
                            "camera_count": {"type": "integer"},
                            "cameras_online": {"type": "integer"},
                            "cameras": {
                                "type": "array",
                                "items": {
                                    "type": "object",
                                    "properties": {
                                        "cameraId": {"type": "integer"},
                                        "name": {"type": "string"},
                                        "rtsp_url": {"type": "string"},
                                        "areaId": {"type": "integer"},
                                        "area": {"type": "object"},
                                        "location_description": {"type": "string"},
                                        "camera_type": {"type": "string"},
                                        "resolution": {"type": "string"},
                                        "fps": {"type": "integer"},
                                        "is_active": {"type": "boolean"},
                                        "status": {"type": "string"},
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
        },
        404: {"description": "Area not found"}
    }
})
def get_area(areaId):
    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Fetch Area Basic Info
        cur.execute("""
            SELECT
                areaId, name, description, COALESCE(parent_area_id, 0) as parent_area_id, created_at, updated_at
            FROM areas WHERE areaId = %s
        """, (areaId,))
        area_row = cur.fetchone()

        if not area_row:
            return jsonify({"detail": "Area not found"}), 404

        # Construct the area object explicitly to ensure key structure matches request
        area_obj = {
            "areaId": area_row['areaId'],
            "name": area_row['name'],
            "description": area_row['description'],
            "parent_area_id": area_row['parent_area_id'],
            "created_at": area_row['created_at'],
            "updated_at": area_row['updated_at']
        }

        # 2. Fetch Associated Cameras with Full Details
        cur.execute("""
            SELECT
                cameraId, name, rtsp_url, areaId, location_description,
                camera_type, resolution, fps, is_active, status,
                last_health_check_at, created_at, updated_at
            FROM cameras
            WHERE areaId = %s
        """, (areaId,))
        camera_rows = cur.fetchall()

        cameras_formatted = []
        cameras_online = 0

        for cam in camera_rows:
            if cam['status'] == 'online':
                cameras_online += 1

            cam_obj = {
                "cameraId": cam['cameraId'],
                "name": cam['name'],
                "rtsp_url": cam['rtsp_url'],
                "areaId": cam['areaId'] or 0,
                "area": area_obj,  # Recursive nesting as requested
                "location_description": cam['location_description'],
                "camera_type": cam['camera_type'],
                "resolution": cam['resolution'],
                "fps": cam['fps'],
                "is_active": bool(cam['is_active']),
                "status": cam['status'],
                "last_health_check_at": cam['last_health_check_at'],
                "created_at": cam['created_at'],
                "updated_at": cam['updated_at']
            }
            cameras_formatted.append(cam_obj)

        # 3. Construct Final Response
        response = area_obj.copy()
        response['cameras'] = cameras_formatted
        response['camera_count'] = len(cameras_formatted)
        response['cameras_online'] = cameras_online

        return jsonify(response)

    except pymysql.MySQLError as e:
        logging.error(f"Failed to get area: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------------------
# 4. PUT /areas/{areaId} - UPDATE AREA
# ----------------------------------------------------------------------
@area_bp.route("/areas/<int:areaId>", methods=["PUT"])
@require_admin
@swag_from({
    "tags": ["Areas"],
    "summary": "Update area",
    "parameters": [
        {"name": "areaId", "in": "path", "type": "integer", "required": True},
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "description": {"type": "string"},
                    "parent_area_Id": {"type": "integer"}
                }
            }
        }
    ],
    "responses": {
        200: {
            "description": "Area updated",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "areaId": {"type": "integer"},
                            "name": {"type": "string"},
                            "description": {"type": "string"},
                            "parent_area_Id": {"type": "integer"},
                            "updated_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
        },
        404: {"description": "Area not found"}
    }
})
def update_area(areaId):
    data = request.get_json()
    if not data: return jsonify({"detail": "Invalid JSON body"}), 400
    logging.info(f"Update request for Area {areaId}. Data: {data}")

    db = get_db_connection(); cur = db.cursor()
    try:
        # Check if area exists
        cur.execute("SELECT areaId FROM areas WHERE areaId = %s", (areaId,))
        if not cur.fetchone():
            return jsonify({"detail": "Area not found"}), 404

        updates = []
        params = []

        if 'name' in data:
            # Check duplicate name exclusion (ignoring self)
            cur.execute("SELECT areaId FROM areas WHERE name = %s AND areaId != %s", (data['name'], areaId))
            if cur.fetchone():
                return jsonify({"detail": f"Area name '{data['name']}' already exists."}), 409
            updates.append("name = %s")
            params.append(data['name'])

        if 'description' in data:
            updates.append("description = %s")
            params.append(data['description'])

        if 'parent_area_id' in data:
            pid = data['parent_area_id']

            # Ensure proper integer type
            if pid is not None:
                try:
                    pid = int(pid)
                except ValueError:
                    return jsonify({"detail": "Parent Area ID must be a valid integer."}), 400

            # Treat 0 as NULL
            if pid == 0: pid = None

            # Prevent circular dependency (Area cannot be its own parent)
            if pid == areaId:
                return jsonify({"detail": "Area cannot be its own parent."}), 400

            if pid is not None:
                cur.execute("SELECT areaId FROM areas WHERE areaId = %s", (pid,))
                if not cur.fetchone():
                    return jsonify({"detail": f"Parent Area ID {pid} not found."}), 400
                cur.fetchall()

            updates.append("parent_area_id = %s")

            params.append(pid)

        if not updates:
            return jsonify({"detail": "No fields to update"}), 400

        params.append(areaId)
        sql = f"UPDATE areas SET {', '.join(updates)} WHERE areaId = %s"
        logging.info(f"Executing Update SQL: {sql} with params: {params}")
        cur.execute(sql, tuple(params))
        db.commit()

        # Return updated record
        cur.execute("""
            SELECT
                areaId, name, description, COALESCE(parent_area_Id, 0) as parent_area_id, created_at, updated_at
            FROM areas WHERE areaId = %s
        """, (areaId,))
        updated_area = cur.fetchone()

        return jsonify(updated_area)

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Failed to update area: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()

# ----------------------------------------------------------------------
# 5. DELETE /areas/{areaId} - DELETE AREA
# ----------------------------------------------------------------------
@area_bp.route("/areas/<int:areaId>", methods=["DELETE"])
@require_admin
@swag_from({
    "tags": ["Areas"],
    "summary": "Delete area",
    "parameters": [{"name": "areaId", "in": "path", "type": "integer", "required": True}],
    "responses": {
        204: {"description": "Area deleted"},
        404: {"description": "Area not found"}
    }
})
def delete_area(areaId):
    db = get_db_connection(); cur = db.cursor()
    try:
        cur.execute("SELECT areaId FROM areas WHERE areaId = %s", (areaId,))
        if not cur.fetchone():
            return jsonify({"detail": "Area not found"}), 404

        # Delete the area
        # Note: Foreign keys in Cameras and Child Areas should handle constraints
        # (e.g., ON DELETE SET NULL) based on your schema definition.
        cur.execute("DELETE FROM areas WHERE areaId = %s", (areaId,))
        db.commit()

        return "", 204

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Failed to delete area: {e}")
        return jsonify({"detail": f"Database error: {str(e)}"}), 500
    finally:
        cur.close(); db.close()