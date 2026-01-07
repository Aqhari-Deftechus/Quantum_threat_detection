from flask import Blueprint, jsonify
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging
import time

# Import database helper
from app.database import get_db_connection

# Define the Blueprint
admin_bp = Blueprint('admin', __name__)
logging.basicConfig(level=logging.INFO)

# ==============================================================================
# GET /health/db - CHECK DATABASE CONNECTION
# ==============================================================================
@admin_bp.route("/health/db", methods=["GET"])
@swag_from({
    "tags": ["Admin"],
    "summary": "Check Database Connection",
    "description": "Pings the database to ensure connectivity and returns latency.",
    "responses": {
        "200": {
            "description": "Database is connected",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "example": "connected"},
                            "latency_ms": {"type": "number", "example": 12.5},
                            "timestamp": {"type": "string"}
                        }
                    }
                }
            }
        },
        "500": {
            "description": "Database connection failed",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "status": {"type": "string", "example": "disconnected"},
                            "error": {"type": "string"}
                        }
                    }
                }
            }
        }
    }
})
def check_db_connection():
    start_time = time.time()
    try:
        # Attempt connection
        db = get_db_connection()
        cur = db.cursor()

        # Run simple query
        cur.execute("SELECT 1")
        cur.fetchone()

        # Cleanup
        cur.close()
        db.close()

        # Calculate latency
        latency = (time.time() - start_time) * 1000

        return jsonify({
            "status": "connected",
            "latency_ms": round(latency, 2),
            "timestamp": time.strftime('%Y-%m-%d %H:%M:%S')
        }), 200

    except Exception as e:
        logging.error(f"DB Health Check Failed: {e}")
        return jsonify({
            "status": "disconnected",
            "error": str(e)
        }), 500