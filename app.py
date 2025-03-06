from flask import Flask, g, request, current_app
from flask_cors import CORS
from datetime import datetime
from extension import db  # Import db from extension.py

def create_app():
    app = Flask(__name__)
    print(f"Creating Flask app: {app}")  # Debug: Confirm app creation
    CORS(app, resources={r"/*": {"origins": ["https://face-recognition-app-sepia.vercel.app", "http://localhost:3000"], "supports_credentials": True}})  # Allow requests from React frontend with credentials

    # Configure the database
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///face_recognition.db'
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.secret_key = 'simple-key'  # Basic secret key for sessions

    # Initialize SQLAlchemy with the app
    db.init_app(app)
    print(f"SQLAlchemy initialized with app: {db}")  # Debug: Confirm SQLAlchemy init

    # Import blueprints and models before registration
    from admin import admin_bp
    from user import user_bp
    from models import User, LoginLog, RecognizedPhoto  # Import models
    print(f"Imported blueprints: admin_bp={admin_bp}, user_bp={user_bp}")  # Debug: Confirm imports

    # Register blueprints
    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(user_bp, url_prefix='/user')
    print(f"Blueprints registered: {app.blueprints}")  # Debug: Confirm registration

    # Add before_request to debug context
    @app.before_request
    def before_request():
        g.request_start_time = datetime.now()
        print(f"Before request: {request.path if 'path' in request.__dict__ else 'No path available'}, Context: {current_app._get_current_object()}")  # Debug with safe access

    # Create database tables (requires app context)
    with app.app_context():
        print(f"Creating database tables in context: {app}")  # Debug: Confirm context
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    print(f"Running app: {app}")  # Debug: Confirm app run
    app.run(debug=True, host='0.0.0.0', port=5000)