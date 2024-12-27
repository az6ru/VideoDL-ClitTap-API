import logging
import os
from dotenv import load_dotenv
from app import app, init_db

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO if os.environ.get('FLASK_ENV') == 'production' else logging.DEBUG,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

# Initialize database
init_db()

if __name__ == "__main__":
    # Use environment variables for configuration
    port = int(os.environ.get('FLASK_PORT', '8000'))
    debug = os.environ.get('FLASK_ENV') != 'production'
    workers = int(os.environ.get('WORKERS', '4'))

    if debug:
        app.run(host="0.0.0.0", port=port, debug=True)
    else:
        from gunicorn.app.base import BaseApplication

        class StandaloneApplication(BaseApplication):
            def __init__(self, app, options=None):
                self.options = options or {}
                self.application = app
                super().__init__()

            def load_config(self):
                for key, value in self.options.items():
                    self.cfg.set(key, value)

            def load(self):
                return self.application

        options = {
            'bind': f'0.0.0.0:{port}',
            'workers': workers,
            'worker_class': 'sync',
            'worker_tmp_dir': '/dev/shm',
            'timeout': 120,
            'keep_alive': 5,
            'max_requests': 1000,
            'max_requests_jitter': 50,
            'log_level': 'info',
        }

        StandaloneApplication(app, options).run()