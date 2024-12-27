# Используем официальный Python 3.11 образ на основе slim
FROM python:3.11-slim

# Устанавливаем необходимые системные зависимости
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    libffi-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# Устанавливаем рабочую директорию
WORKDIR /app

# Копируем файл зависимостей
COPY requirements.txt .

# Устанавливаем зависимости
RUN pip install --upgrade pip
RUN pip install --no-cache-dir -r requirements.txt

# Копируем все файлы проекта
COPY . .

# Создаём директорию для загрузок и устанавливаем права
RUN mkdir -p downloads && chmod 755 downloads

# Инициализируем базу данных
RUN python init_db.py

# Устанавливаем переменные окружения
ENV FLASK_ENV=production
ENV FLASK_APP=app
ENV FLASK_PORT=8000
ENV SOURCE_DATE_EPOCH=315532800

# Открываем порт
EXPOSE 8000

# Команда запуска приложения через Gunicorn
CMD ["gunicorn", "main:app", "--bind", "0.0.0.0:8000", "--workers", "4", "--timeout", "120", "--keep-alive", "5", "--log-level", "info"]
