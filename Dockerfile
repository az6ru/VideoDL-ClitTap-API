# Этап сборки
FROM python:3.11-slim as builder

# Установка необходимых системных зависимостей для сборки
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libffi-dev \
    && rm -rf /var/lib/apt/lists/*

# Создание и активация виртуального окружения
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Установка зависимостей Python
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Основной этап
FROM python:3.11-slim

# Копирование виртуального окружения из этапа сборки
COPY --from=builder /opt/venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"

# Установка только необходимых runtime зависимостей
RUN apt-get update && apt-get install -y \
    libpq5 \
    ffmpeg \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Создание non-root пользователя
RUN useradd -m -u 1000 app

# Установка рабочей директории и прав
WORKDIR /app
RUN chown app:app /app

# Копирование файлов проекта
COPY --chown=app:app . .

# Создание и настройка прав для директории загрузок
RUN mkdir -p downloads && chown -R app:app downloads && chmod 755 downloads

# Переключение на non-root пользователя
USER app

# Установка переменных окружения
ENV FLASK_ENV=production \
    FLASK_APP=app \
    FLASK_PORT=8000 \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    WORKERS=4

# Health check
HEALTHCHECK --interval=30s --timeout=5s --start-period=5s --retries=3 \
    CMD curl --fail http://localhost:8000/api/docs || exit 1

# Открываем порт
EXPOSE 8000

# Инициализация базы данных и запуск приложения
CMD ["sh", "-c", "python init_db.py && gunicorn main:app --bind 0.0.0.0:8000 --workers 4 --worker-class sync --worker-tmp-dir /dev/shm --timeout 120 --keep-alive 5 --max-requests 1000 --max-requests-jitter 50 --log-level info --access-logfile - --error-logfile -"]