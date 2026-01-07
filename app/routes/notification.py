from flask import Blueprint, request, jsonify, current_app
from flasgger import swag_from # type: ignore
import pymysql # type: ignore
import logging
import json
import os
from datetime import datetime
from pywebpush import webpush, WebPushException # type: ignore

# Import helpers
from app.decorators import require_auth
from app.database import get_db_connection

# Define the Blueprint
notification_bp = Blueprint('notifications', __name__)
logging.basicConfig(level=logging.INFO)

# ==============================================================================
# CONFIGURATION
# ==============================================================================
VAPID_PRIVATE_KEY = os.environ.get("VAPID_PRIVATE_KEY", "xzM-BZWCsjKBzPv-UUAs82jzRlixKg6Q1HUPhjOTadg")
VAPID_CLAIMS = {
    "sub": "mailto:admin@your-surveillance-system.com"
}

# ==============================================================================
# HELPER: Trigger Notification (With Preference Checks & Logging)
# ==============================================================================
def trigger_notification_for_role(role, title, body, icon_url=None, action_url="/", anomaly_id=None):
    """
    Sends push notifications to users based on their roles AND preferences.
    """
    db = get_db_connection(); cur = db.cursor()
    try:
        # 1. Fetch Users, their Subscriptions, AND their Preferences
        # We join pushsubscriptions (S) and notificationpreferences (P)
        sql = """
            SELECT
                U.id as user_id,
                S.endpoint, S.p256dh, S.auth,
                COALESCE(P.web_push_enabled, 1) as push_enabled, -- Default to True (1)
                COALESCE(P.anomaly_threshold, 'all') as threshold
            FROM users U
            JOIN pushsubscriptions S ON U.id = S.user_id
            LEFT JOIN notificationpreferences P ON U.id = P.user_id
            -- In real app, filter by Role here: WHERE U.role = %s
        """
        cur.execute(sql)
        targets = cur.fetchall()
    except Exception as e:
        logging.error(f"Failed to fetch targets: {e}")
        return False
    finally:
        cur.close(); db.close()

    if not targets:
        return False

    payload = json.dumps({
        "title": title,
        "body": body,
        "icon": icon_url if icon_url else "/static/icons/alert.png",
        "url": action_url
    })

    cnt = 0
    # Re-open DB for logging results
    db = get_db_connection(); cur = db.cursor()

    for target in targets:
        # CHECK PREFERENCES
        if not target['push_enabled']:
            continue # User disabled push notifications

        # SEND
        subscription_info = {
            "endpoint": target['endpoint'],
            "keys": {"p256dh": target['p256dh'], "auth": target['auth']}
        }

        status = 'failed'
        error_msg = None

        try:
            webpush(
                subscription_info=subscription_info,
                data=payload,
                vapid_private_key=VAPID_PRIVATE_KEY,
                vapid_claims=VAPID_CLAIMS
            )
            status = 'sent'
            cnt += 1
        except WebPushException as ex:
            error_msg = str(ex)
            logging.error(f"Push failed for user {target['user_id']}: {repr(ex)}")

        # LOG HISTORY
        try:
            cur.execute("""
                INSERT INTO notificationlogs
                (anomaly_id, user_id, channel, recipient, subject, body, status, sent_at, error_message)
                VALUES (%s, %s, 'web_push', 'browser', %s, %s, %s, NOW(), %s)
            """, (anomaly_id, target['user_id'], title, body, status, error_msg))
            db.commit()
        except Exception as log_ex:
            logging.error(f"Failed to log notification: {log_ex}")

    cur.close(); db.close()
    logging.info(f"Notification '{title}' sent to {cnt} devices.")
    return True

# ==============================================================================
# 1. POST /notifications/subscribe - SAVE BROWSER SUBSCRIPTION
# ==============================================================================
@notification_bp.route("/notifications/subscribe", methods=["POST"])
@require_auth
@swag_from({
    "tags": ["Notifications"],
    "summary": "Subscribe to push notifications",
    "security": [{"Bearer": []}],
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "required": ["endpoint", "keys"],
                "properties": {
                    "endpoint": {"type": "string"},
                    "keys": {
                        "type": "object",
                        "properties": {"p256dh": {"type": "string"}, "auth": {"type": "string"}}
                    },
                    "userAgent": {"type": "string"}
                }
            }
        }
    ],
    "responses": {
        201: {"description": "Subscribed successfully"},
        400: {"description": "Invalid data"}
    }
})
def subscribe():
    user = request.user # type: ignore
    data = request.get_json()

    if not data or 'endpoint' not in data or 'keys' not in data:
        return jsonify({"detail": "Invalid subscription format"}), 400

    endpoint = data['endpoint']
    p256dh = data['keys'].get('p256dh')
    auth = data['keys'].get('auth')
    user_agent = data.get('userAgent', request.headers.get('User-Agent'))

    db = get_db_connection(); cur = db.cursor()
    try:
        # Resolve User ID
        if 'id' not in user:
            cur.execute("SELECT id FROM users WHERE username = %s", (user['username'],))
            row = cur.fetchone()
            if not row: return jsonify({"detail": "User not found"}), 404
            user_id = row['id']
        else:
            user_id = user['id']

        # Check existing
        cur.execute("SELECT id FROM pushsubscriptions WHERE endpoint = %s", (endpoint,))
        if cur.fetchone():
             return jsonify({"detail": "Already subscribed"}), 200

        cur.execute("""
            INSERT INTO pushsubscriptions (user_id, endpoint, p256dh, auth, user_agent)
            VALUES (%s, %s, %s, %s, %s)
        """, (user_id, endpoint, p256dh, auth, user_agent))

        db.commit()
        return jsonify({"status": "subscribed"}), 201

    except pymysql.MySQLError as e:
        db.rollback()
        logging.error(f"Subscription failed: {e}")
        return jsonify({"detail": "Database error"}), 500
    finally:
        cur.close(); db.close()

# ==============================================================================
# 2. GET /notifications/preferences - GET USER PREFERENCES
# ==============================================================================
@notification_bp.route("/notifications/preferences", methods=["GET"])
@require_auth
@swag_from({
    "tags": ["Notifications"],
    "summary": "Get notification preferences",
    "responses": {
        200: {
            "description": "User notification preferences",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer"},
                            "user_id": {"type": "integer"},
                            "email_enabled": {"type": "boolean"},
                            "web_push_enabled": {"type": "boolean"},
                            "push_subscription": {"type": "object"},
                            "anomaly_threshold": {
                                "type": "string",
                                "enum": ["all", "medium_and_above", "high_only"]
                            },
                            "digest_frequency": {
                                "type": "string",
                                "enum": ["realtime", "hourly", "daily", "never"]
                            },
                            "updated_at": {"type": "string", "format": "date-time"}
                        }
                    }
                }
            }
        }
    }
})
def get_preferences():
    user = request.user # type: ignore

    db = get_db_connection(); cur = db.cursor()
    try:
        # Resolve User ID
        if 'id' not in user:
            cur.execute("SELECT id FROM users WHERE username = %s", (user['username'],))
            row = cur.fetchone()
            user_id = row['id'] if row else 0
        else:
            user_id = user['id']

        # 1. Fetch Preferences
        cur.execute("""
            SELECT id, user_id, email_enabled, web_push_enabled, anomaly_threshold, digest_frequency, updated_at
            FROM notificationpreferences
            WHERE user_id = %s
        """, (user_id,))
        pref = cur.fetchone()

        # 2. Fetch Latest Push Subscription (as 'push_subscription' object for UI)
        cur.execute("""
            SELECT id, endpoint, created_at
            FROM pushsubscriptions
            WHERE user_id = %s
            ORDER BY created_at DESC LIMIT 1
        """, (user_id,))
        sub_row = cur.fetchone()

        # Construct Response
        if not pref:
            # Return Defaults if no record exists
            response = {
                "id": 0,
                "user_id": user_id,
                "email_enabled": True,
                "web_push_enabled": True,
                "anomaly_threshold": "all",
                "digest_frequency": "realtime",
                "push_subscription": sub_row or {},
                "updated_at": datetime.now().isoformat()
            }
        else:
            response = {
                "id": pref['id'],
                "user_id": pref['user_id'],
                "email_enabled": bool(pref['email_enabled']),
                "web_push_enabled": bool(pref['web_push_enabled']),
                "anomaly_threshold": pref['anomaly_threshold'],
                "digest_frequency": pref['digest_frequency'],
                "push_subscription": sub_row or {},
                "updated_at": pref['updated_at'].isoformat() if pref['updated_at'] else None
            }

        return jsonify(response)

    except Exception as e:
        logging.error(f"Get preferences failed: {e}")
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()

# ==============================================================================
# 3. PUT /notifications/preferences - UPDATE PREFERENCES
# ==============================================================================
@notification_bp.route("/notifications/preferences", methods=["PUT"])
@require_auth
@swag_from({
    "tags": ["Notifications"],
    "summary": "Update notification preferences",
    "parameters": [
        {
            "name": "body",
            "in": "body",
            "required": True,
            "schema": {
                "type": "object",
                "properties": {
                    "email_enabled": {"type": "boolean", "example": True},
                    "web_push_enabled": {"type": "boolean", "example": True},
                    "anomaly_threshold": {
                        "type": "string",
                        "enum": ["all", "medium_and_above", "high_only"],
                        "example": "all"
                    },
                    "digest_frequency": {
                        "type": "string",
                        "enum": ["realtime", "hourly", "daily", "never"],
                        "example": "realtime"
                    }
                }
            }
        }
    ],
    "responses": {
        200: {
            "description": "Preferences updated",
            "content": {
                "application/json": {
                    "schema": {
                        "type": "object",
                        "properties": {
                            "id": {"type": "integer", "example": 0},
                            "user_id": {"type": "integer", "example": 0},
                            "email_enabled": {"type": "boolean", "example": True},
                            "web_push_enabled": {"type": "boolean", "example": True},
                            "push_subscription": {"type": "object", "example": {}},
                            "anomaly_threshold": {
                                "type": "string",
                                "enum": ["all", "medium_and_above", "high_only"],
                                "example": "all"
                            },
                            "digest_frequency": {
                                "type": "string",
                                "enum": ["realtime", "hourly", "daily", "never"],
                                "example": "realtime"
                            },
                            "updated_at": {"type": "string", "format": "date-time", "example": "2025-12-10T08:17:33.404Z"}
                        }
                    }
                }
            }
        }
    }
})
def update_preferences():
    user = request.user # type: ignore
    data = request.get_json()
    if not data: return jsonify({"detail": "Invalid JSON"}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        # Resolve User ID
        if 'id' not in user:
            cur.execute("SELECT id FROM users WHERE username = %s", (user['username'],))
            row = cur.fetchone()
            if not row:
                return jsonify({"detail": "User not found"}), 404
            user_id = row['id']
        else:
            user_id = user['id']

        # Prepare values
        email_enabled = data.get('email_enabled', True)
        web_push_enabled = data.get('web_push_enabled', True)
        anomaly_threshold = data.get('anomaly_threshold', 'all')
        digest_frequency = data.get('digest_frequency', 'realtime')

        # Upsert (Insert or Update)
        # Note: We use explicitly repeated parameters in UPDATE to avoid
        # MySQL 8.0.20+ deprecation warnings/errors with VALUES() function.
        sql = """
            INSERT INTO notificationpreferences
            (user_id, email_enabled, web_push_enabled, anomaly_threshold, digest_frequency)
            VALUES (%s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
            email_enabled = %s,
            web_push_enabled = %s,
            anomaly_threshold = %s,
            digest_frequency = %s
        """
        # Pass parameters for INSERT (5) + UPDATE (4)
        params = (
            user_id, email_enabled, web_push_enabled, anomaly_threshold, digest_frequency,
            email_enabled, web_push_enabled, anomaly_threshold, digest_frequency
        )

        cur.execute(sql, params)
        db.commit()

        # Fetch and return updated
        return get_preferences()

    except Exception as e:
        db.rollback()
        # Log the full error to help debugging
        logging.error(f"Update preferences failed: {e}", exc_info=True)
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()

# ==============================================================================
# 4. GET /notifications - GET NOTIFICATION HISTORY (LOGS)
# ==============================================================================
@notification_bp.route("/notifications", methods=["GET"])
@require_auth
@swag_from({
    "tags": ["Notifications"],
    "summary": "Get notification history",
    "parameters": [
        {"name": "page", "in": "query", "type": "integer", "default": 1},
        {"name": "limit", "in": "query", "type": "integer", "default": 20}
    ],
    "responses": {
        200: {
            "description": "Notification history",
            "content": {
                "application/json": {
                    "schema": {"$ref": "#/components/schemas/PaginatedNotifications"}
                }
            }
        }
    }
})
def get_history():
    user = request.user # type: ignore
    page = request.args.get('page', 1, type=int)
    limit = request.args.get('limit', 20, type=int)
    offset = (page - 1) * limit

    db = get_db_connection(); cur = db.cursor()
    try:
        if 'id' not in user:
            cur.execute("SELECT id FROM users WHERE username = %s", (user['username'],))
            row = cur.fetchone()
            user_id = row['id'] # type: ignore
        else:
            user_id = user['id']

        # Get Total
        cur.execute("SELECT COUNT(*) as total FROM notificationlogs WHERE user_id = %s", (user_id,))
        total = cur.fetchone()['total'] # type: ignore

        # Get Data
        cur.execute("""
            SELECT id, anomaly_id, channel, recipient, subject, body, status, sent_at, error_message, created_at
            FROM notificationlogs
            WHERE user_id = %s
            ORDER BY created_at DESC
            LIMIT %s OFFSET %s
        """, (user_id, limit, offset))
        rows = cur.fetchall()

        # Format dates
        for row in rows:
            if row['sent_at']: row['sent_at'] = row['sent_at'].isoformat()
            if row['created_at']: row['created_at'] = row['created_at'].isoformat()

        total_pages = (total + limit - 1) // limit if total > 0 else 0

        return jsonify({
            "page": page,
            "limit": limit,
            "total": total,
            "total_pages": total_pages,
            "data": rows
        })

    except Exception as e:
        logging.error(f"Get history failed: {e}")
        return jsonify({"detail": str(e)}), 500
    finally:
        cur.close(); db.close()

# ==============================================================================
# 5. POST /notifications/test - SEND TEST ALERT
# ==============================================================================
@notification_bp.route("/notifications/test", methods=["POST"])
@require_auth
@swag_from({
    "tags": ["Notifications"],
    "summary": "Send test push notification",
    "responses": {200: {"description": "Notifications sent"}}
})
def send_test_notification():
    success = trigger_notification_for_role(
        role="Admin",
        title="Test Alert",
        body="This is a manual test from the Dashboard.",
        action_url="/dashboard"
    )
    if success:
        return jsonify({"status": "sent"}), 200
    else:
        return jsonify({"status": "no subscribers or error"}), 404