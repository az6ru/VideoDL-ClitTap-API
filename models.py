from datetime import datetime
from app import db

class Download(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    task_id = db.Column(db.UUID, unique=True, nullable=False)
    url = db.Column(db.String(512), nullable=False)
    status = db.Column(db.String(20), nullable=False, default='pending')
    progress = db.Column(db.Float, default=0.0)
    title = db.Column(db.String(256))
    format = db.Column(db.String(20))
    video_format = db.Column(db.String(20))
    audio_format = db.Column(db.String(20))
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    completed_at = db.Column(db.DateTime)
    error = db.Column(db.String(512))
    file_path = db.Column(db.String(512))
