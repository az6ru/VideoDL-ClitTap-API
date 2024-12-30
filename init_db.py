import os
import logging
import secrets
from datetime import datetime, timedelta
from dotenv import load_dotenv
from app import db, app
from models import ApiKey
from sqlalchemy.exc import SQLAlchemyError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def generate_api_key():
    """Генерация случайного API ключа"""
    return secrets.token_hex(32)

def create_test_api_key():
    """Создание тестового API ключа"""
    try:
        # Проверяем, существует ли уже тестовый ключ
        test_key = ApiKey.query.filter_by(name='test_key').first()
        if test_key:
            logger.info("Test API key already exists")
            return test_key.key

        # Создаем новый тестовый ключ
        api_key = ApiKey(
            key=generate_api_key(),
            name='test_key',
            is_active=True,
            expires_at=datetime.utcnow() + timedelta(days=365),
            rate_limit=1000
        )
        db.session.add(api_key)
        db.session.commit()
        logger.info(f"Created test API key: {api_key.key}")
        return api_key.key
    except Exception as e:
        logger.error(f"Error creating test API key: {str(e)}")
        db.session.rollback()
        raise

def init_db():
    try:
        # Load environment variables
        load_dotenv()

        # Log database connection attempt
        logger.info("Attempting to initialize database...")

        with app.app_context():
            # Удаляем все существующие таблицы
            db.drop_all()
            logger.info("Dropped all existing tables")

            # Create all database tables
            db.create_all()
            logger.info("Database tables created successfully!")

            # Create test API key
            test_key = create_test_api_key()
            logger.info(f"Database initialization completed! Test API key: {test_key}")

    except SQLAlchemyError as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    init_db()