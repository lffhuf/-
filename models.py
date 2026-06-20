from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from datetime import datetime

db = SQLAlchemy()

class User(UserMixin, db.Model):
    __tablename__ = 'users'
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    is_admin = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    # 找回密码
    security_question = db.Column(db.String(200), default='')
    security_answer = db.Column(db.String(200), default='')
    reset_token = db.Column(db.String(100), default='')
    reset_token_expiry = db.Column(db.DateTime, nullable=True)
    
    files = db.relationship('File', backref='owner', lazy=True)

class File(db.Model):
    __tablename__ = 'files'
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(200), nullable=False)  # 显示名称
    filename = db.Column(db.String(200), nullable=False)  # 实际文件名
    display_name = db.Column(db.String(200), nullable=False)  # 展示名称
    file_type = db.Column(db.String(50), nullable=False)
    size = db.Column(db.Integer, nullable=False)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_shared = db.Column(db.Boolean, default=False)
    share_code = db.Column(db.String(20), unique=True)
    share_password = db.Column(db.String(50), nullable=True)
    views = db.Column(db.Integer, default=0)
