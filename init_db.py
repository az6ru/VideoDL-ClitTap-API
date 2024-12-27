import os
import logging
import time
from dotenv import load_dotenv
from app import db, app
from sqlalchemy.exc import SQLAlchemyError, OperationalError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db(max_retries=5, retry_delay=5):
    """Initialize database with retry mechanism"""
    # Load environment variables
    load_dotenv()

    # Check if DATABASE_URL is provided
    if not os.environ.get("DATABASE_URL"):
        raise RuntimeError("DATABASE_URL environment variable is not set")

    logger.info(f"Initializing database with DATABASE_URL: {os.environ.get('DATABASE_URL', 'Not set')}")

    for attempt in range(max_retries):
        try:
            logger.info(f"Database initialization attempt {attempt + 1}/{max_retries}")

            with app.app_context():
                # Create all database tables
                db.create_all()
                logger.info("Database tables created successfully!")
                return True

        except OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to initialize database after {max_retries} attempts: {str(e)}")
                raise
        except SQLAlchemyError as e:
            logger.error(f"Database initialization failed: {str(e)}")
            raise
        except Exception as e:
            logger.error(f"An unexpected error occurred: {str(e)}")
            raise

if __name__ == "__main__":
    init_db()