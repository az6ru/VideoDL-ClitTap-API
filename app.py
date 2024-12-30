import os
import logging
from flask import Flask, redirect, url_for, jsonify
from flask_swagger_ui import get_swaggerui_blueprint
from dotenv import load_dotenv
from extensions import db
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_cors import CORS
from config import Config
from utils.downloader import start_cleanup_thread

# Load environment variables
load_dotenv()

logging.basicConfig(level=logging.DEBUG)

app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

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
migrate = Migrate(app, db)

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

@app.route('/health')
def health_check():
    try:
        # Проверка подключения к базе данных
        db.session.execute('SELECT 1')
        return jsonify({'status': 'healthy', 'database': 'connected'}), 200
    except Exception as e:
        return jsonify({'status': 'unhealthy', 'database': str(e)}), 500

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

# Запускаем поток очистки с контекстом приложения
start_cleanup_thread(app)

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('FLASK_PORT', 5000)))