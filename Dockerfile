# Use Python 3.11 slim image
FROM python:3.11-slim

# Set working directory
WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    ffmpeg \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . .

# Create downloads directory
RUN mkdir -p downloads && chmod 777 downloads

# Expose port (will be overridden by docker-compose)
ARG FLASK_PORT=5000
EXPOSE ${FLASK_PORT}

# Set environment variables
ARG FLASK_ENV=production
ENV FLASK_APP=app.py
ENV FLASK_ENV=${FLASK_ENV}

# Run the application
CMD ["python", "main.py"]