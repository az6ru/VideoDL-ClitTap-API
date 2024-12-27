#!/bin/sh

# Выход при ошибках
set -e

# Функция ожидания доступности базы данных
wait_for_db() {
    echo "Ожидание доступности базы данных..."
    until python -c "import psycopg2; psycopg2.connect('$DATABASE_URL')" >/dev/null 2>&1; do
        echo "База данных недоступна - ожидаем 1 секунду..."
        sleep 1
    done
    echo "База данных доступна."
}

# Ожидание базы данных
wait_for_db

# Инициализация базы данных
echo "Инициализация базы данных..."
python init_db.py

# Запуск приложения через Gunicorn
exec "$@"
