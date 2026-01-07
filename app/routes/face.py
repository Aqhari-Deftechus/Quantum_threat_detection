from flask import Blueprint, request, jsonify
from flasgger import swag_from # type: ignore
import logging
import os

# Import helpers and decorators
from app.decorators import require_admin
from app.database import get_db_connection
from app.utils import resolve_person_folder, touch_pkltimestamp_debounced

# Define the Blueprint
face_bp = Blueprint('face', __name__)

# ---------- FACE UPLOAD ----------
@face_bp.route("/face/upload_images", methods=["POST"])
@swag_from({
    "tags": ["face"],
    "summary": "Upload multiple face images for user (Admin only)",
    "parameters": [
        {"name": "badgeID", "in": "formData", "type": "string", "required": True},
        {"name": "files", "in": "formData", "type": "file", "required": True, "collectionFormat": "multi"}
    ],
    "security": [{"Bearer": []}]
})
@require_admin
def upload_images():
    badgeID = request.form.get("badgeID")
    if not badgeID:
        return jsonify({"detail": "badgeID required"}), 400

    db = get_db_connection(); cur = db.cursor()
    try:
        # Get PersonName associated with the BadgeID to resolve the folder path
        cur.execute("""
            SELECT PersonName FROM workeridentity WHERE BadgeID = %s
        """, (badgeID,))
        row = cur.fetchone()
        if not row:
            return jsonify({"detail": "BadgeID not found in workeridentity"}), 400
        person_name = row["PersonName"]
    finally:
        cur.close(); db.close()

    folder_path = resolve_person_folder(person_name)
    folder_path.mkdir(parents=True, exist_ok=True) # Ensure directory exists

    saved_files = []
    file_list = request.files.getlist('files')

    for f in file_list:
        if not f or not f.filename:
            continue

        # Sanitize filename before saving
        filename = os.path.basename(f.filename)
        dest = folder_path / filename
        f.save(dest)
        saved_files.append(filename)

    if not saved_files:
        return jsonify({"msg": "No valid files received or saved."}), 400

    # Notify the face recognition service to reload the updated data
    touch_pkltimestamp_debounced()

    return jsonify({"msg": f"{len(saved_files)} images uploaded", "badgeID": badgeID, "files": saved_files})