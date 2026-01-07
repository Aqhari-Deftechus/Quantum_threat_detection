# __init__.py

import logging
from flask import Flask, jsonify
from flask_cors import CORS # type: ignore
from flasgger import Swagger # type: ignore
import mediapipe as mp

from app.config import Config
from app.database import connect_db_simple # Use simple connection for initial test

# ======================================================
# SWAGGER CONFIG (Swagger 2.0)
# ======================================================
swagger_template = {
    "swagger": "2.0",
    "info": {
        "title": "Auth & Face API (Flask) - Modular",
        "description": "Modular Flask application using Blueprints.",
        "version": "1.0.0"
    },
    "securityDefinitions": {
        "Bearer": {
            "type": "apiKey",
            "name": "Authorization",
            "in": "header",
            "description": "JWT Authorization header. Example: 'Bearer <token>'"
        }
    },
    "security": [{"Bearer": []}],
    "tags": [
        {"name": "Admin", "description": "Check database connectivity and health"},
        {"name": "Authentication", "description": "Login, logout, token management"},
        {"name": "Users", "description":"Admin user management"},
        {"name": "Employees", "description": "Employee registration and face enrollment"},
        {"name": "Cameras", "description": "Camera configuration and streaming"},
        {"name": "Areas", "description": "Area/zone management"},
        {"name": "Attendance", "description": "Attendance records and tracking"},
        {"name": "Notifications", "description": "Notification preferences and history"},
        {"name": "Reports", "description": "Attendance reports and analytics"},
        {"name": "Application", "description": "Detection end Point"}
        # {"name": "face", "description": "Face data endpoints"}
    ]
}
swagger_config = {
    "headers": [],
    "specs": [
        {"endpoint": "apispec_1", "route": "/apispec_1.json", "rule_filter": lambda rule: True, "model_filter": lambda tag: True}
    ],
    "static_url_path": "/flasgger_static",
    "swagger_ui": True,
    "specs_route": "/docs/"
}

def create_app(config_class=Config):
    """Flask Application Factory function."""
    app = Flask(__name__)
    app.config.from_object(config_class)
    CORS(app)

    # Initialize Swagger
    Swagger(app, template=swagger_template, config=swagger_config)

    # Configure logging
    logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

    # ==================== REGISTER BLUEPRINTS ====================
    from app.routes.auth import auth_bp
    from app.routes.users import user_bp
    from app.routes.areas import area_bp
    from app.routes.cameras import camera_bp
    from app.routes.employees import employee_bp
    from app.routes.attendance import attendance_bp
    from app.routes.report import report_bp
    from app.routes.notification import notification_bp
    from app.routes.admin import admin_bp
    #from app.routes.application import application
    from app.routes.application import application_bp
    from app.routes.anomalies_api import bp as anomalies_bp

    app.register_blueprint(auth_bp)
    app.register_blueprint(user_bp, url_prefix="/users")
    app.register_blueprint(employee_bp)
    app.register_blueprint(area_bp)
    app.register_blueprint(camera_bp)
    app.register_blueprint(attendance_bp)
    app.register_blueprint(report_bp)
    app.register_blueprint(notification_bp)
    app.register_blueprint(admin_bp)
    app.register_blueprint(application_bp)
    app.register_blueprint(anomalies_bp)

    # =============================================================

    # Register simple health check route (can be done here or in a blueprint)
    @app.route("/", methods=["GET"])
    def health():
        """Health check"""
        return jsonify({"status": "Auth service running"})

    return app

# ======================================================
# DB CONNECTION TEST (Re-purposed from original file)
# ======================================================
def test_db_connection():
    logging.info("Attempting database connection test...")
    db = None
    try:
        # Use connect_db_simple since app context is not running yet
        db = connect_db_simple(Config)
        cur = db.cursor()
        cur.execute("SELECT 1")
        result = cur.fetchone()
        if result and list(result.values())[0] == 1:
            logging.info("✅ Database connection successful and basic query executed.")
        else:
            logging.error("❌ Database test query failed.")
        cur.close()
    except Exception as e:
        logging.error(f"❌ Database connection failed: {e}. Check host, user, and password in config.py.")
    finally:
        if db:
            db.close()