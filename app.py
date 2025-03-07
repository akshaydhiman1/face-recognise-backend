from flask import Flask, g, request, current_app
from flask_cors import CORS
from datetime import datetime
from extension import db
import os
from dotenv import load_dotenv

load_dotenv()
print(f"Loaded FRONTEND_URL: {os.getenv('FRONTEND_URL', 'Not found')}")

def create_app():
    app = Flask(__name__)
    print(f"Creating Flask app: {app}")

    frontend_urls = os.getenv("FRONTEND_URL", "http://localhost:3000").split(",")
    CORS(app, resources={r"/*": {
        "origins": frontend_urls,
        "supports_credentials": True,
        "methods": ["GET", "POST", "OPTIONS", "PUT", "DELETE"],
        "allow_headers": ["Content-Type", "Authorization"],
        "max_age": 86400
    }})

    app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv("DATABASE_URI", "sqlite:///face_recognition.db")
    app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
    app.secret_key = os.getenv("SECRET_KEY", "simple-key")

    db.init_app(app)
    print(f"SQLAlchemy initialized with app: {db}")

    from admin import admin_bp
    from user import user_bp
    from models import User, LoginLog, RecognizedPhoto
    print(f"Imported blueprints: admin_bp={admin_bp}, user_bp={user_bp}")

    app.register_blueprint(admin_bp, url_prefix='/admin')
    app.register_blueprint(user_bp, url_prefix='/user')
    print(f"Blueprints registered: {app.blueprints}")

    @app.before_request
    def before_request():
        g.request_start_time = datetime.now()
        print(f"Before request: {request.path if 'path' in request.__dict__ else 'No path available'}, Context: {current_app._get_current_object()}")

    with app.app_context():
        print(f"Creating database tables in context: {app}")
        db.create_all()

    return app

if __name__ == '__main__':
    app = create_app()
    print(f"Running app: {app}")
    app.run(debug=True, host=os.getenv("FLASK_HOST", "0.0.0.0"), port=int(os.getenv("FLASK_PORT", 5000)))