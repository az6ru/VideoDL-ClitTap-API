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

logger = logging.getLogger(__name__)

# Initialize database
init_db()

if __name__ == "__main__":
    # Use environment variables for configuration
    port = int(os.environ.get('FLASK_PORT', '8000'))
    debug = os.environ.get('FLASK_ENV') != 'production'

    if debug:
        logger.info("Starting Flask development server")
        app.run(host="0.0.0.0", port=port, debug=True)
    else:
        logger.info("Starting Gunicorn production server")
        try:
            import gunicorn.app.base

            class StandaloneApplication(gunicorn.app.base.BaseApplication):
                def __init__(self, app, options=None):
                    self.options = options or {}
                    self.application = app
                    super().__init__()

                def load_config(self):
                    config = {key: value for key, value in self.options.items()
                             if key in self.cfg.settings and value is not None}
                    for key, value in config.items():
                        self.cfg.set(key.lower(), value)

                def load(self):
                    return self.application

            options = {
                'bind': f'0.0.0.0:{port}',
                'workers': int(os.environ.get('WORKERS', '4')),
                'worker_class': 'sync',
                'worker_tmp_dir': '/dev/shm',
                'timeout': 120,
                'keepalive': 5,
                'max_requests': 1000,
                'max_requests_jitter': 50,
                'accesslog': '-',
                'errorlog': '-',
                'loglevel': 'info'
            }

            logger.info(f"Starting Gunicorn with options: {options}")
            StandaloneApplication(app, options).run()

        except ImportError as e:
            logger.error(f"Failed to import Gunicorn: {e}")
            raise
        except Exception as e:
            logger.error(f"Failed to start Gunicorn: {e}")
            raise