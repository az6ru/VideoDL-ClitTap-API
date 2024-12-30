import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    SECRET_KEY = os.environ.get('FLASK_SECRET_KEY', os.urandom(24))
    SQLALCHEMY_DATABASE_URI = os.environ.get('DATABASE_URL')
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        "pool_pre_ping": True,
        "pool_recycle": 300,
        "pool_timeout": 20,
        "pool_size": 5,
        "max_overflow": 10,
        "connect_args": {
            "connect_timeout": 10,
        },
    } 