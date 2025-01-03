# VideoDL API Postman Collection

Эта коллекция содержит готовые запросы для работы с VideoDL API.

## Установка

1. Установите [Postman](https://www.postman.com/downloads/)
2. Импортируйте коллекцию `VideoDL-API.postman_collection.json`
3. Импортируйте окружение `VideoDL-API.postman_environment.json`

## Настройка окружения

1. Откройте настройки окружения в Postman
2. Установите следующие переменные:
   - `base_url`: URL вашего API (по умолчанию http://localhost:5001)
   - `api_key`: Ваш API ключ
   - `auth_username`: Имя пользователя для получения API ключа
   - `auth_password`: Пароль для получения API ключа
   - `video_url`: URL видео для тестирования
   - `task_id`: ID задачи скачивания (заполняется автоматически)

## Использование

### Получение API ключа

1. Откройте запрос "Создать API токен" в папке "Авторизация"
2. Убедитесь, что установлены правильные `auth_username` и `auth_password`
3. Отправьте запрос
4. Скопируйте полученный токен в переменную окружения `api_key`

### Работа с видео

1. Установите `video_url` в окружении
2. Используйте запросы из папки "Видео информация" для получения данных
3. Для скачивания используйте запросы из папки "Скачивание"

### Работа с аудио

1. Установите `video_url` в окружении
2. Используйте запросы из папки "Аудио" для работы с аудио форматами
3. Для скачивания аудио используйте запрос "Скачать аудио"

## Примеры запросов

### Получение полной информации о видео
```http
GET {{base_url}}/api/combined-info?url={{video_url}}
X-API-Key: {{api_key}}
```

### Скачивание видео в HD качестве
```http
GET {{base_url}}/api/download?url={{video_url}}&format=HD
X-API-Key: {{api_key}}
```

### Скачивание аудио в MP3
```http
GET {{base_url}}/api/audio/download?url={{video_url}}&format=high&convert_to_mp3=true
X-API-Key: {{api_key}}
``` 