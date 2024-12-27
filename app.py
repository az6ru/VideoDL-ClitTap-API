import os
import logging
from flask import Flask, redirect, url_for
from flask_sqlalchemy import SQLAlchemy
from flask_swagger_ui import get_swaggerui_blueprint
from sqlalchemy.orm import DeclarativeBase

logging.basicConfig(level=logging.DEBUG)

class Base(DeclarativeBase):
    pass

db = SQLAlchemy(model_class=Base)
app = Flask(__name__)

# Configuration
app.secret_key = os.environ.get("FLASK_SECRET_KEY") or "a secret key"
app.config["SQLALCHEMY_DATABASE_URI"] = os.environ.get("DATABASE_URL")
app.config["SQLALCHEMY_ENGINE_OPTIONS"] = {
    "pool_recycle": 300,
    "pool_pre_ping": True,
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

with app.app_context():
    import models
    db.create_all()
