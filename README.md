# Video Metadata API

API сервис для получения метаданных видео, информации о форматах и управления загрузками.

## Возможности

- Получение полной информации о видео (метаданные + форматы)
- Получение базовой информации о видео
- Получение списка доступных форматов видео
- Получение списка аудио форматов
- Скачивание видео в различных форматах
- Скачивание только аудио
- Конвертация аудио в MP3
- Управление API ключами

## Требования

- Python 3.8+
- PostgreSQL
- FFmpeg (для обработки видео и аудио)

## Установка

1. Клонируйте репозиторий:
```bash
git clone [url-репозитория]
cd newvideoapi
```

2. Создайте виртуальное окружение и установите зависимости:
```bash
python -m venv .venv
source .venv/bin/activate  # для Linux/macOS
# или
.venv\Scripts\activate  # для Windows
pip install -r requirements.txt
```

3. Скопируйте `.env.example` в `.env` и настройте переменные окружения:
```bash
cp .env.example .env
```

4. Инициализируйте базу данных:
```bash
python init_db.py
```

## Запуск

### Локально
```bash
python app.py
```

### Docker
```bash
docker-compose up -d
```

## API Endpoints

### Получение полной информации о видео
```http
GET /api/combined-info?url={video_url}
```

### Получение базовой информации
```http
GET /api/info?url={video_url}
```

### Получение форматов видео
```http
GET /api/formats?url={video_url}&filtered=true
```

### Получение аудио форматов
```http
GET /api/audio/formats?url={video_url}
```

### Создание задачи на скачивание
```http
GET /api/download?url={video_url}&format={format_id}
```

### Скачивание аудио
```http
GET /api/audio/download?url={video_url}&format={quality}&convert_to_mp3=true
```

## Аутентификация

API использует аутентификацию по ключу. Все запросы должны содержать заголовок:
```
X-API-Key: your-api-key
```

### Получение API ключа
```http
POST /api/token
```

## Docker

Проект включает Dockerfile и docker-compose.yml для простого развертывания:

```bash
# Сборка и запуск
docker-compose up -d

# Остановка
docker-compose down
```

## Переменные окружения

- `FLASK_ENV` - окружение Flask (development/production)
- `FLASK_PORT` - порт для запуска сервера
- `POSTGRES_*` - настройки PostgreSQL
- `AUTH_USERNAME` - имя пользователя для получения API токена
- `AUTH_PASSWORD` - пароль для получения API токена
- `TOKEN_EXPIRY_DAYS` - срок действия токена в днях
- `DEFAULT_RATE_LIMIT` - лимит запросов по умолчанию

## Документация API

Полная документация API доступна по адресу `/api/docs` после запуска сервера.

## Лицензия

MIT 