import os
import pickle
import shutil
import re
import mimetypes
from flask import Blueprint, request, send_from_directory, jsonify, redirect, url_for, send_file
import cv2
import face_recognition
from datetime import datetime
from extension import db
from models import User  # Removed LoginLog from imports
from flask import current_app

admin_bp = Blueprint('admin', __name__, template_folder='templates/admin')

# Use absolute path for KNOWN_FACES_DIR based on the script's location
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
KNOWN_FACES_DIR = os.path.join(BASE_DIR, "known_faces")
ENCODINGS_FILE = os.path.join(BASE_DIR, "encodings.pkl")
os.makedirs(KNOWN_FACES_DIR, exist_ok=True)

def load_encodings():
    if os.path.exists(ENCODINGS_FILE):
        with open(ENCODINGS_FILE, "rb") as f:
            data = pickle.load(f)
            return {
                "classifiers": data.get("classifiers", []),
                "encodings": data.get("encodings", []),
                "timestamps": data.get("timestamps", []),
                "filenames": data.get("filenames", [])
            }
    return {"classifiers": [], "encodings": [], "timestamps": [], "filenames": []}

def save_encodings(data):
    with open(ENCODINGS_FILE, "wb") as f:
        pickle.dump(data, f)

def sanitize_filename(name):
    base, extension = os.path.splitext(name)
    base = re.sub(r'[<>:"/\\|?*.\s]+', '_', base.strip())
    return base + extension

admin_logged_in = False

@admin_bp.route('/login', methods=['GET', 'POST'])
def admin_login():
    global admin_logged_in
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if not username or not password:
            data = request.get_json()
            username = data.get('username') if data else None
            password = data.get('password') if data else None
        print(f"Received username: {username}, password: {password}")
        if not username or not password:
            return jsonify({"error": "Username and password are required"}), 400
        if username == "admin" and password == "admin123":
            admin_logged_in = True
            return jsonify({"message": "Login successful", "redirect": "/admin/dashboard"}), 200
        return jsonify({"error": "Invalid username or password"}), 401
    if admin_logged_in:
        return jsonify({"message": "Already logged in", "redirect": "/admin/dashboard"}), 200
    return send_from_directory('templates/admin', 'login.html')

@admin_bp.route('/dashboard', methods=['GET'])
def admin_dashboard():
    global admin_logged_in
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    return send_from_directory('templates/admin', 'dashboard.html')

@admin_bp.route('/dashboard', methods=['POST'])
def admin_dashboard_post():
    global admin_logged_in
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    
    if 'images' not in request.files or 'classify' not in request.form:
        return jsonify({"error": "Images and classifier are required"}), 400
    image_files = request.files.getlist('images')
    classifier = request.form['classify']
    if not image_files or not classifier:
        return jsonify({"error": "At least one image and a classifier are required"}), 400
    
    classifier = sanitize_filename(classifier)
    classifier_dir = os.path.join(KNOWN_FACES_DIR, classifier)
    if os.path.exists(classifier_dir):
        shutil.rmtree(classifier_dir)
    try:
        os.makedirs(classifier_dir, exist_ok=True)
        print(f"Created classifier directory: {classifier_dir}")
    except OSError as e:
        return jsonify({"error": f"Failed to create directory: {str(e)}"}), 500

    data = load_encodings()
    uploaded = []
    processed_filenames = set()

    print(f"Received {len(image_files)} image files for classifier: {classifier}")
    for image_file in image_files:
        if image_file.filename == '':
            continue
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        filename = f"{timestamp}_{sanitize_filename(image_file.filename)}"
        image_path = os.path.join(classifier_dir, filename)
        
        print(f"Attempting to process file: {filename}")
        if filename in processed_filenames:
            print(f"Skipping duplicate file: {filename}")
            uploaded.append({"filename": filename, "status": "Skipped (Duplicate)"})
            continue
        
        try:
            image_file.save(image_path)
            print(f"Saved image to: {image_path}")
            if not os.path.exists(image_path):
                print(f"Failed to save image to: {image_path}")
                uploaded.append({"filename": filename, "status": "Failed to save"})
                continue
            image = face_recognition.load_image_file(image_path)
            encodings = face_recognition.face_encodings(image)
            if len(encodings) == 0:
                uploaded.append({"filename": filename, "status": "No Face Detected (still saved)"})
                data["classifiers"].append(classifier)
                data["encodings"].append([])
                data["timestamps"].append(timestamp)
                data["filenames"].append(os.path.join(classifier, filename))
            else:
                data["classifiers"].append(classifier)
                data["encodings"].append(encodings[0])
                data["timestamps"].append(timestamp)
                data["filenames"].append(os.path.join(classifier, filename))
                uploaded.append({"filename": filename, "status": "Saved with Encoding"})
            processed_filenames.add(filename)
            print(f"Successfully processed file: {filename}")
        except Exception as e:
            os.remove(image_path) if os.path.exists(image_path) else None
            uploaded.append({"filename": filename, "status": f"Error: {str(e)}"})
            print(f"Error processing file {filename}: {str(e)}")
    save_encodings(data)
    print(f"Total uploaded: {len(uploaded)}, Unique processed: {len(processed_filenames)}")
    return jsonify({"message": f"Uploaded {len(uploaded)} images", "uploaded": uploaded}), 200

@admin_bp.route('/api/dashboard_data', methods=['GET'])
def dashboard_data():
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing dashboard_data with context: {current_app}")
        data = load_encodings()
        print(f"DB initialized: {db is not None}")
        total_users = User.query.count()  # Changed to count unique users
        total_photos = len(data["filenames"])
        classifiers = data["classifiers"][-5:] + [None] * (5 - len(data["classifiers"][-5:]))
        timestamps = data["timestamps"][-5:] + [None] * (5 - len(data["timestamps"][-5:]))
        filenames = data["filenames"][-5:] + [None] * (5 - len(data["filenames"][-5:]))
        recent_uploads = [
            {"classifier": cls, "timestamp": ts, "filename": fn, "status": "Saved"} 
            for cls, ts, fn in zip(classifiers, timestamps, filenames) 
            if fn and os.path.exists(os.path.join(KNOWN_FACES_DIR, fn))
        ][:5]
        return jsonify({
            "total_users": total_users,
            "total_photos": total_photos,
            "recent_uploads": recent_uploads
        })

@admin_bp.route('/users', methods=['GET'])
def admin_users():
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    return send_from_directory('templates/admin', 'users.html')

@admin_bp.route('/api/users', methods=['GET'])
def users_data():
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing users_data with context: {current_app}")
        users = User.query.all()
        return jsonify([{"id": u.id, "username": u.username, "email": u.email, "profile_pic": "No Pic", "registration_date": "N/A"} 
                        for u in users])

@admin_bp.route('/api/edit_user/<int:user_id>', methods=['POST'])
def edit_user(user_id):
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing edit_user with context: {current_app}")
        user = User.query.get_or_404(user_id)
        data = request.form
        new_username = data.get('username')
        new_email = data.get('email')
        if not new_username or not new_email:
            return jsonify({"error": "Username and email are required"}), 400
        if User.query.filter_by(username=new_username).first() and new_username != user.username:
            return jsonify({"error": "Username already exists"}), 400
        if User.query.filter_by(email=new_email).first() and new_email != user.email:
            return jsonify({"error": "Email already exists"}), 400
        user.username = new_username
        user.email = new_email
        db.session.commit()
        return jsonify({"message": f"User {user_id} updated successfully"}), 200

@admin_bp.route('/api/delete_user/<int:user_id>', methods=['POST'])
def delete_user(user_id):
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing delete_user with context: {current_app}")
        user = User.query.get_or_404(user_id)
        db.session.delete(user)
        db.session.commit()
        return jsonify({"message": f"User {user_id} deleted successfully"}), 200

@admin_bp.route('/content', methods=['GET'])
def admin_content():
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    return send_from_directory('templates/admin', 'content.html')

@admin_bp.route('/api/content', methods=['GET'])
def content_data():
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing content_data with context: {current_app}")
        data = load_encodings()
        filtered_content = []
        updated_data = {
            "classifiers": [],
            "encodings": [],
            "timestamps": [],
            "filenames": []
        }

        for cls, ts, fn, enc in zip(data["classifiers"], data["timestamps"], data["filenames"], data["encodings"]):
            file_path = os.path.join(KNOWN_FACES_DIR, fn)
            print(f"Checking file existence: {file_path}")
            exists = os.path.exists(file_path)
            print(f"File exists: {exists} for {file_path}")
            if exists:
                filtered_content.append({
                    "classifier": cls,
                    "timestamp": ts,
                    "filename": fn,
                    "url": f"known_faces/{fn}",
                    "status": "Saved"
                })
                updated_data["classifiers"].append(cls)
                updated_data["encodings"].append(enc)
                updated_data["timestamps"].append(ts)
                updated_data["filenames"].append(fn)
            else:
                print(f"Removing stale entry: {fn} (file not found)")

        if len(filtered_content) != len(data["filenames"]):
            print(f"Updating encodings.pkl: {len(data['filenames'])} entries reduced to {len(filtered_content)}")
            save_encodings(updated_data)

        return jsonify(filtered_content)

@admin_bp.route('/content/<classifier>', methods=['GET'])
def classifier_content(classifier):
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    return send_from_directory('templates/admin', 'classifier_content.html')

@admin_bp.route('/api/classifier_content/<classifier>', methods=['GET'])
def classifier_content_data(classifier):
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing classifier_content_data with context: {current_app}")
        data = load_encodings()
        classifier_content = [
            {"classifier": cls, "timestamp": ts, "filename": fn, "url": f"known_faces/{fn}", "status": "Saved"}
            for cls, ts, fn in zip(data["classifiers"], data["timestamps"], data["filenames"])
            if cls == classifier
        ]
        return jsonify(classifier_content)

@admin_bp.route('/known_faces/<path:filename>', methods=['GET'])
def serve_known_face(filename):
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    # Normalize the path to use OS-specific separators
    normalized_filename = filename.replace('/', os.sep)
    image_path = os.path.join(KNOWN_FACES_DIR, normalized_filename)
    print(f"Attempting to serve image from: {image_path}")
    if not os.path.exists(image_path):
        print(f"Image not found: {image_path}")
        return jsonify({"error": "Image not found"}), 404
    # Ensure the file is served with the correct MIME type
    mimetype, _ = mimetypes.guess_type(image_path)
    if mimetype is None:
        mimetype = 'image/jpeg'  # Default to JPEG if type cannot be guessed
    print(f"Serving image: {image_path} with MIME type: {mimetype}")
    return send_file(image_path, mimetype=mimetype, as_attachment=False)

@admin_bp.route('/api/delete_content/<path:filename>', methods=['POST'])
def delete_content(filename):
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing delete_content with context: {current_app}")
        data = load_encodings()
        normalized_filename = filename.replace('/', os.sep)
        image_path = os.path.join(KNOWN_FACES_DIR, normalized_filename)
        if not os.path.exists(image_path):
            print(f"File not found on disk: {image_path}")
            if filename in data["filenames"]:
                for i, fn in enumerate(data["filenames"]):
                    if fn == filename:
                        classifier = data["classifiers"][i]
                        data["classifiers"].pop(i)
                        data["encodings"].pop(i)
                        data["timestamps"].pop(i)
                        data["filenames"].pop(i)
                        save_encodings(data)
                        print(f"Removed stale entry from encodings.pkl: {filename}")
                        return jsonify({"message": f"Image {filename} metadata removed successfully"}), 200
            return jsonify({"error": "Image not found"}), 404
        
        for i, fn in enumerate(data["filenames"]):
            if fn == filename:
                classifier = data["classifiers"][i]
                data["classifiers"].pop(i)
                data["encodings"].pop(i)
                data["timestamps"].pop(i)
                data["filenames"].pop(i)
                os.remove(image_path)
                save_encodings(data)
                
                if not any(cls == classifier for cls in data["classifiers"]):
                    classifier_dir = os.path.join(KNOWN_FACES_DIR, classifier)
                    if os.path.exists(classifier_dir):
                        shutil.rmtree(classifier_dir)
                        print(f"Removed empty classifier directory: {classifier_dir}")
                print(f"Deleted image and updated encodings.pkl: {filename}")
                return jsonify({"message": f"Image {filename} deleted successfully"}), 200
        return jsonify({"error": "Image not found in database"}), 404

@admin_bp.route('/api/delete_classifier/<classifier>', methods=['POST'])
def delete_classifier(classifier):
    if not admin_logged_in:
        return jsonify({"error": "Please log in first", "redirect": "/admin/login"}), 403
    with current_app.app_context():
        print(f"Executing delete_classifier with context: {current_app}")
        data = load_encodings()
        classifier_dir = os.path.join(KNOWN_FACES_DIR, classifier)
        if not os.path.exists(classifier_dir):
            print(f"Classifier directory not found on disk: {classifier_dir}")
            indices_to_remove = [i for i, cls in enumerate(data["classifiers"]) if cls == classifier]
            if indices_to_remove:
                for i in sorted(indices_to_remove, reverse=True):
                    data["classifiers"].pop(i)
                    data["encodings"].pop(i)
                    data["timestamps"].pop(i)
                    data["filenames"].pop(i)
                save_encodings(data)
                print(f"Removed stale classifier entries from encodings.pkl: {classifier}")
                return jsonify({"message": f"Classifier {classifier} metadata removed successfully"}), 200
            return jsonify({"error": "Classifier not found"}), 404
        
        indices_to_remove = [i for i, cls in enumerate(data["classifiers"]) if cls == classifier]
        if not indices_to_remove:
            return jsonify({"error": "Classifier not found in database"}), 404
        
        for i in sorted(indices_to_remove, reverse=True):
            data["classifiers"].pop(i)
            data["encodings"].pop(i)
            data["timestamps"].pop(i)
            filename = data["filenames"].pop(i)
            image_path = os.path.join(KNOWN_FACES_DIR, filename)
            if os.path.exists(image_path):
                os.remove(image_path)
                print(f"Deleted image: {image_path}")
        
        shutil.rmtree(classifier_dir)
        save_encodings(data)
        print(f"Deleted classifier directory and updated encodings.pkl: {classifier}")
        return jsonify({"message": f"Classifier {classifier} and its photos deleted successfully"}), 200

@admin_bp.route('/logout', methods=['GET'])
def admin_logout():
    global admin_logged_in
    admin_logged_in = False
    return redirect(url_for('admin.admin_login'))