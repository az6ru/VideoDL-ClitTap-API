import os
import logging
from dotenv import load_dotenv
from app import db, app
from sqlalchemy.exc import SQLAlchemyError

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    try:
        # Load environment variables
        load_dotenv()

        # Log database connection attempt
        logger.info(f"Attempting to initialize database...")

        with app.app_context():
            # Create all database tables
            db.create_all()
            logger.info("Database tables created successfully!")

    except SQLAlchemyError as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise
    except Exception as e:
        logger.error(f"An unexpected error occurred: {str(e)}")
        raise

if __name__ == "__main__":
    init_db()