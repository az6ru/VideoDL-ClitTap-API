from functools import wraps
from flask import request, jsonify
from models import ApiKey
from datetime import datetime, timedelta
import logging
from extensions import db

logger = logging.getLogger(__name__)

def require_api_key(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        if not api_key:
            return jsonify({'error': 'API key is required'}), 401

        key = ApiKey.query.filter_by(key=api_key).first()
        if not key:
            return jsonify({'error': 'Invalid API key'}), 401

        if not key.is_valid():
            return jsonify({'error': 'API key is expired or inactive'}), 401

        # Обновляем статистику использования
        key.last_used_at = datetime.utcnow()
        key.downloads_count += 1
        db.session.add(key)
        db.session.commit()

        return f(*args, **kwargs)
    return decorated_function 