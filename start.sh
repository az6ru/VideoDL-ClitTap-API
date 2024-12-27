#!/bin/bash
set -e

# Wait for PostgreSQL to be ready
echo "Waiting for PostgreSQL..."
while ! nc -z ${PGHOST:-localhost} ${PGPORT:-5432}; do
  sleep 1
done
echo "PostgreSQL is ready!"

# Initialize database if needed
python3 init_db.py

# Start the application
python3 main.py