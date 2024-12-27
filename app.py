import os
import logging
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_swagger_ui import get_swaggerui_blueprint
from sqlalchemy.orm import DeclarativeBase
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY", os.urandom(24))
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_pre_ping": True,
    "pool_recycle": 300,
    "pool_timeout": 20,
    "pool_size": 5,
    "max_overflow": 10,
    "connect_args": {
        "connect_timeout": 10,
    },
}

# Initialize extensions
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

# Initialize database tables
with app.app_context():
    import models
    try:
        db.create_all()
        logging.info("Database tables created successfully")
    except Exception as e:
        logging.error(f"Error creating database tables: {e}")