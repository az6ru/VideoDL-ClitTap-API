import os
import logging
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_swagger_ui import get_swaggerui_blueprint
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv
import time
from sqlalchemy import exc

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(level=logging.DEBUG)
logger = logging.getLogger(__name__)

# Initialize Flask app first
app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))

# Initialize SQLAlchemy with Base class
class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)

# Check if DATABASE_URL is provided and log its presence
database_url = os.environ.get("DATABASE_URL")
if not database_url:
    raise RuntimeError("DATABASE_URL environment variable is not set")
logger.info(f"Database URL is configured: {database_url[:8]}...{database_url[-8:]}")

# Database Configuration
app.config["SQLALCHEMY_DATABASE_URI"] = database_url
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_timeout": 30,
    "pool_size": 5,
    "max_overflow": 10,
    "connect_args": {
        "connect_timeout": 30,
        "keepalives": 1,
        "keepalives_idle": 30,
        "keepalives_interval": 10,
        "keepalives_count": 5,
        "application_name": "videodl-api"
    },
}

# Initialize the database
db.init_app(app)

# Swagger UI configuration
SWAGGER_URL = '/api/docs'
API_URL = '/static/swagger.json'

swaggerui_blueprint = get_swaggerui_blueprint(
    SWAGGER_URL,
    API_URL,
    config={
        'app_name': "Video Metadata Service",
        'dom_id': '#swagger-ui',
        'deepLinking': True,
        'layout': 'BaseLayout',
        'defaultModelsExpandDepth': 1,
        'defaultModelExpandDepth': 1,
    }
)

app.register_blueprint(swaggerui_blueprint)

@app.route('/')
def index():
    return redirect(url_for('swagger_ui.show'))

# Register API routes
from api.routes import api_bp
app.register_blueprint(api_bp, url_prefix='/api')

def init_db_with_retry(max_retries=5, retry_delay=5):
    """Initialize database with retry mechanism"""
    logger.info(f"Attempting to initialize database with DATABASE_URL: {database_url[:8]}...{database_url[-8:]}")

    for attempt in range(max_retries):
        try:
            with app.app_context():
                import models
                db.create_all()
                logger.info("Database tables created successfully")
                return True
        except exc.OperationalError as e:
            if attempt < max_retries - 1:
                logger.warning(f"Database connection attempt {attempt + 1} failed: {str(e)}")
                logger.info(f"Retrying in {retry_delay} seconds...")
                time.sleep(retry_delay)
            else:
                logger.error(f"Failed to initialize database after {max_retries} attempts: {str(e)}")
                raise
        except Exception as e:
            logger.error(f"Unexpected error creating database tables: {str(e)}")
            raise

# Initialize database tables with retry mechanism only in production
if os.environ.get("FLASK_ENV") != "development":
    init_db_with_retry()