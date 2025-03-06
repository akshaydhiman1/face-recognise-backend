from extension import db
from werkzeug.security import generate_password_hash, check_password_hash
from datetime import datetime, timezone
class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password = db.Column(db.String(120), nullable=False)  # In production, this should be password_hash

    def check_password(self, password):
        # Since passwords are stored in plain text in your current setup
        return self.password == password
        # In production, use hashing:
        # return check_password_hash(self.password, password)

    def set_password(self, password):
        # For future use with hashing
        self.password = password  # In production: generate_password_hash(password)

class LoginLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)

class RecognizedPhoto(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    filename = db.Column(db.String(200), nullable=False)
    recognized_name = db.Column(db.String(100))
    timestamp = db.Column(db.DateTime, nullable=False, default=datetime.utcnow)