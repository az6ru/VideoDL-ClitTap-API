#!/bin/bash
if [ ! -d "/tmp/postgres_data" ]; then
    echo "Initializing PostgreSQL data directory..."
    initdb -D /tmp/postgres_data
fi
pg_ctl -D /tmp/postgres_data -l /tmp/postgres_log start
createdb -U postgres mydatabase || echo "Database already exists"
