# Video API Postman Collection

Эта коллекция содержит все эндпоинты Video API для удобного тестирования и разработки.

## Установка

1. Установите [Postman](https://www.postman.com/downloads/)
2. Импортируйте коллекцию `VideoAPI.postman_collection.json`
3. Импортируйте окружение `VideoAPI.postman_environment.json`

## Настройка окружения

Перед использованием коллекции необходимо настроить переменные окружения:

1. Откройте окружение "Video API Environment" в Postman
2. Заполните следующие переменные:
   - `base_url`: URL вашего API (по умолчанию http://localhost:5001/api)
   - `api_key`: Ваш API ключ
   - `auth_username`: Имя пользователя для базовой аутентификации
   - `auth_password`: Пароль для базовой аутентификации
   - `video_url`: URL видео для тестирования
   - `task_id`: ID задачи скачивания (заполняется автоматически после создания задачи)

## Использование

Коллекция разделена на несколько категорий:

### Auth
- Create API Token: Создание нового API токена

### Video Info
- Get Combined Info: Получение полной информации о видео
- Get Basic Info: Получение базовой информации
- Get Formats: Получение списка форматов

### Downloads
- Create Download Task: Создание задачи на скачивание
- Get Download Status: Проверка статуса скачивания
- Download File: Скачивание готового файла

### Audio
- Get Audio Formats: Получение списка аудио форматов
- Create Audio Download: Создание задачи на скачивание аудио

## Примеры использования

1. Получение API токена:
   - Откройте запрос "Create API Token"
   - Убедитесь, что заполнены `auth_username` и `auth_password`
   - Отправьте запрос
   - Скопируйте полученный токен в переменную окружения `api_key`

2. Получение информации о видео:
   - Установите URL видео в переменную `video_url`
   - Выполните запрос "Get Combined Info"
   - В ответе вы получите полную информацию о видео и доступных форматах

3. Скачивание видео:
   - Выполните запрос "Create Download Task"
   - Скопируйте полученный `task_id` в переменную окружения
   - Используйте "Get Download Status" для проверки статуса
   - После завершения используйте "Download File" для скачивания 