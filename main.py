import logging
from app import app

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)

if __name__ == "__main__":
    # Use production settings for deployment
    app.run(
        host="0.0.0.0",
        port=5000,
        debug=False
    )
