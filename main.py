import logging
import os
from dotenv import load_dotenv
from app import app

# Load environment variables
load_dotenv()

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    # Use environment variables for configuration
    port = int(os.getenv('FLASK_PORT', 8000))
    debug = os.getenv('FLASK_ENV') == 'development'

    app.run(
        host="0.0.0.0",
        port=port,
        debug=debug
    )