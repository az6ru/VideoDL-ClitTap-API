from datetime import datetime
from uuid import UUID
from extensions import db
import uuid
from sqlalchemy.dialects.postgresql import UUID as pgUUID

class Download(db.Model):
    __tablename__ = 'downloads'

    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(pgUUID(as_uuid=True), unique=True, nullable=False, default=uuid.uuid4)
    url = db.Column(db.String, nullable=False)
    format = db.Column(db.String)
    video_format = db.Column(db.String)
    audio_format = db.Column(db.String)
    status = db.Column(db.String, default='pending')
    progress = db.Column(db.Float, default=0.0)
    file_path = db.Column(db.String)
    error = db.Column(db.String)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    title = db.Column(db.String)
    convert_to_mp3 = db.Column(db.Boolean, default=False)

class ApiKey(db.Model):
    __tablename__ = 'api_keys'

    id = db.Column(db.Integer, primary_key=True)
    key = db.Column(db.String(64), unique=True, nullable=False)
    name = db.Column(db.String(255), nullable=False)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    last_used_at = db.Column(db.DateTime)
    expires_at = db.Column(db.DateTime)
    rate_limit = db.Column(db.Integer, default=100)  # Запросов в минуту
    downloads_count = db.Column(db.Integer, default=0)
    
    def is_valid(self):
        """Проверка валидности ключа"""
        if not self.is_active:
            return False
        if self.expires_at and self.expires_at < datetime.utcnow():
            return False
        return True
