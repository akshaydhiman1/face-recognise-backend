import os
import pickle
import shutil
import base64
from flask import Blueprint, request, jsonify, send_from_directory
import face_recognition
import numpy as np
from datetime import datetime, timezone
from extension import db
from models import User, LoginLog, RecognizedPhoto

user_bp = Blueprint('user', __name__)

UPLOADS_DIR = "uploads"
USER_UPLOADS_DIR = "user_uploads"
KNOWN_FACES_DIR = "known_faces"
ENCODINGS_FILE = "encodings.pkl"
os.makedirs(UPLOADS_DIR, exist_ok=True)
os.makedirs(USER_UPLOADS_DIR, exist_ok=True)
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

user_id = None  # Simple global for now

def load_encodings():
    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)
            encodings = [np.array(enc, dtype=np.float64) if isinstance(enc, list) else enc for enc in data.get("encodings", [])]
            return {
                "classifiers": data.get("classifiers", []),
                "encodings": encodings,
                "timestamps": data.get("timestamps", []),
                "filenames": data.get("filenames", [])
            }
    return {"classifiers": [], "encodings": [], "timestamps": [], "filenames": []}

def save_encodings(data):
    with open(ENCODINGS_FILE, "wb") as f:
        data_to_save = {
            "classifiers": data["classifiers"],
            "encodings": [enc.tolist() if isinstance(enc, np.ndarray) else enc for enc in data["encodings"]],
            "timestamps": data["timestamps"],
            "filenames": data["filenames"]
        }
        pickle.dump(data_to_save, f)

@user_bp.route('/register', methods=['POST'])
def user_register():
    global user_id
    data = request.get_json()
    username = data.get('username')
    email = data.get('email')
    password = data.get('password')
    if not username or not email or not password:
        return jsonify({"error": "Please provide username, email, and password"}), 400
    if User.query.filter_by(username=username).first():
        return jsonify({"error": "This username is already taken"}), 400
    if User.query.filter_by(email=email).first():
        return jsonify({"error": "This email is already registered"}), 400
    new_user = User(username=username, email=email, password=password)
    db.session.add(new_user)
    db.session.commit()
    user_id = new_user.id
    return jsonify({"message": f"Welcome, {username}! Registration successful"}), 201

@user_bp.route('/login', methods=['POST', 'OPTIONS'])
def login():
    global user_id
    if request.method == "OPTIONS":
        return {"message": "CORS preflight"}, 200
    data = request.get_json() or request.form
    username = data.get("username")
    password = data.get("password")
    user = User.query.filter_by(username=username).first()
    if user and user.check_password(password):
        user_id = user.id
        login_log = LoginLog(user_id=user.id, timestamp=datetime.now(timezone.utc))
        db.session.add(login_log)
        db.session.commit()
        return jsonify({"message": "Logged in", "user_id": str(user.id)})
    return jsonify({"error": "Invalid credentials"}), 401

@user_bp.route('/dashboard', methods=['POST'])
def user_dashboard():
    global user_id
    if not user_id:
        return jsonify({"error": "Please log in to access your dashboard"}), 403

    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found. Please log in again"}), 403

    image_data = request.form.get('image_data')
    if not image_data:
        return jsonify({"error": "Please capture an image to recognize"}), 400

    header, encoded = image_data.split(',', 1)
    image_bytes = base64.b64decode(encoded)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    temp_path = os.path.join(UPLOADS_DIR, f"{user.username}_{timestamp}.jpg")

    try:
        with open(temp_path, 'wb') as f:
            f.write(image_bytes)
    except Exception as e:
        return jsonify({"error": f"Failed to process image: {str(e)}"}), 500

    unknown_image = face_recognition.load_image_file(temp_path)
    unknown_encodings = face_recognition.face_encodings(unknown_image)
    if not unknown_encodings:
        os.remove(temp_path)
        return jsonify({"error": "No face detected in the captured image"}), 400

    data = load_encodings()
    matches = []
    tolerance = 0.4
    for i, encoding in enumerate(data["encodings"]):
        if encoding.size > 0:
            for unknown_encoding in unknown_encodings:
                match = face_recognition.compare_faces([encoding], unknown_encoding, tolerance=tolerance)[0]
                if match:
                    matches.append({
                        "classifier": data["classifiers"][i],
                        "filename": data["filenames"][i],
                        "timestamp": data["timestamps"][i]
                    })
                    break

    if not matches:
        os.remove(temp_path)
        return jsonify({"error": "No matching faces found in our database"}), 404

    recognized_photos = []
    for match in matches:
        admin_filename = os.path.basename(match['filename'])
        existing_photo = RecognizedPhoto.query.filter(
            RecognizedPhoto.user_id == user_id,
            RecognizedPhoto.recognized_name == match['classifier'],
            RecognizedPhoto.filename.like(f'%{admin_filename}')
        ).first()
        if not existing_photo:
            user_filename = f"{user.username}_{timestamp}_{match['classifier']}_{admin_filename}"
            user_path = os.path.join(USER_UPLOADS_DIR, user_filename)
            admin_image_path = os.path.join(KNOWN_FACES_DIR, match['filename'])
            if os.path.exists(admin_image_path):
                shutil.copy2(admin_image_path, user_path)
                recognized_photo = RecognizedPhoto(
                    user_id=user_id,
                    filename=user_filename,
                    recognized_name=match['classifier'],
                    timestamp=datetime.now()
                )
                db.session.add(recognized_photo)
                recognized_photos.append({
                    "filename": user_filename,
                    "recognized_name": match['classifier'],
                    "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                    "url": f"/user/image/{user_filename}"
                })
        else:
            recognized_photos.append({
                "filename": existing_photo.filename,
                "recognized_name": existing_photo.recognized_name,
                "timestamp": existing_photo.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
                "url": f"/user/image/{existing_photo.filename}"
            })

    os.remove(temp_path)
    db.session.commit()
    return jsonify({"message": f"Found {len(matches)} matching photo(s)", "matches": recognized_photos}), 200

@user_bp.route('/gallery/<int:user_id>', methods=['GET'])
def user_gallery(user_id):
    # global user_id  # Remove global declaration to avoid conflict with parameter
    # if not user_id and not user_id:  # Original check
    if not user_id:  # Simplified check using the parameter
        return jsonify({"error": "Please log in to view your gallery"}), 403
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found. Please log in again"}), 403
    photos = RecognizedPhoto.query.filter_by(user_id=user_id).all()
    return jsonify({
        "photos": [{
            "id": photo.id,
            "filename": photo.filename,
            "recognized_name": photo.recognized_name,
            "timestamp": photo.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
            "url": f"/user/image/{photo.filename}"
        } for photo in photos]
    })

@user_bp.route('/image/<path:filename>', methods=['GET'])
def serve_image(filename):
    global user_id
    if not user_id:
        return jsonify({"error": "Please log in to view images"}), 403
    return send_from_directory(USER_UPLOADS_DIR, filename)

@user_bp.route('/delete_photo/<int:photo_id>', methods=['POST'])
def delete_user_photo(photo_id):
    global user_id
    if not user_id:
        return jsonify({"error": "Please log in to delete photos"}), 403
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found. Please log in again"}), 403
    
    photo = RecognizedPhoto.query.filter_by(id=photo_id, user_id=user_id).first()
    if not photo:
        return jsonify({"error": "Photo not found in your gallery"}), 404
    
    file_path = os.path.join(USER_UPLOADS_DIR, photo.filename)
    if os.path.exists(file_path):
        os.remove(file_path)
    
    db.session.delete(photo)
    db.session.commit()
    return jsonify({"message": f"Photo '{photo.filename}' deleted successfully"}), 200

@user_bp.route('/delete_all_photos', methods=['POST'])
def delete_all_photos():
    global user_id
    if not user_id:
        return jsonify({"error": "Please log in to delete photos"}), 403
    user = User.query.get(user_id)
    if not user:
        return jsonify({"error": "User not found. Please log in again"}), 403
    
    photos = RecognizedPhoto.query.filter_by(user_id=user_id).all()
    if not photos:
        return jsonify({"error": "No photos found in your gallery"}), 404
    
    for photo in photos:
        file_path = os.path.join(USER_UPLOADS_DIR, photo.filename)
        if os.path.exists(file_path):
            os.remove(file_path)
        db.session.delete(photo)
    
    db.session.commit()
    return jsonify({"message": "All photos deleted successfully"}), 200

@user_bp.route('/logout', methods=['POST'])
def user_logout():
    global user_id
    user_id = None
    return jsonify({"message": "You have been logged out successfully"}), 200

@user_bp.route('/api/user_data', methods=['GET', 'OPTIONS'])
def get_user_data():
    if request.method == "OPTIONS":
        return {"message": "CORS preflight"}, 200
    global user_id
    user_id_from_request = request.args.get('user_id')
    if not user_id and not user_id_from_request:
        return jsonify({"error": "Please log in to access user data"}), 403
    user = User.query.get(user_id or user_id_from_request)
    if user:
        return jsonify({"username": user.username})
    return jsonify({"error": "User not found"}), 404

@user_bp.route('/data', methods=['GET', 'OPTIONS'])
def get_user_data_alt():
    if request.method == "OPTIONS":
        return {"message": "CORS preflight"}, 200
    global user_id
    user_id_from_request = request.args.get('user_id')
    if not user_id and not user_id_from_request:
        return jsonify({"error": "Please log in to access user data"}), 403
    user = User.query.get(user_id or user_id_from_request)
    if user:
        return jsonify({"username": user.username})
    return jsonify({"error": "User not found"}), 404