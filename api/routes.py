import os
import glob
import time
from uuid import UUID
import secrets
from datetime import datetime, timedelta
from flask import Blueprint, request, jsonify, send_file
from marshmallow import ValidationError
from extensions import db
from models import Download, ApiKey
from api.schemas import VideoInfoSchema, DownloadSchema
from utils.downloader import get_cached_video_info, get_cached_formats, start_download_task
from api.middleware import require_api_key
import logging
from functools import wraps

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

def generate_api_key():
    """Генерация случайного API ключа"""
    return secrets.token_hex(32)

def check_auth(username, password):
    """Проверяет учетные данные для базовой аутентификации"""
    return (username == os.environ.get('AUTH_USERNAME') and 
            password == os.environ.get('AUTH_PASSWORD'))

def authenticate():
    """Отправляет 401 ответ с запросом базовой аутентификации"""
    return jsonify({
        'error': 'Требуется аутентификация',
        'message': 'Для получения API токена необходимо предоставить учетные данные'
    }), 401, {'WWW-Authenticate': 'Basic realm="Получение API токена"'}

def requires_auth(f):
    """Декоратор для базовой аутентификации"""
    @wraps(f)
    def decorated(*args, **kwargs):
        auth = request.authorization
        if not auth or not check_auth(auth.username, auth.password):
            return authenticate()
        return f(*args, **kwargs)
    return decorated

@api_bp.route('/token', methods=['POST'])
@requires_auth
def create_token():
    """Создание нового API токена"""
    try:
        name = request.json.get('name', 'API Token')
        # Получаем настройки из переменных окружения
        expiry_days = int(os.environ.get('TOKEN_EXPIRY_DAYS', 30))
        rate_limit = int(os.environ.get('DEFAULT_RATE_LIMIT', 1000))
        
        api_key = ApiKey(
            key=secrets.token_hex(32),
            name=name,
            is_active=True,
            expires_at=datetime.utcnow() + timedelta(days=expiry_days),
            rate_limit=rate_limit
        )
        
        db.session.add(api_key)
        db.session.commit()
        
        return jsonify({
            'token': api_key.key,
            'name': api_key.name,
            'expires_at': api_key.expires_at.isoformat(),
            'rate_limit': api_key.rate_limit
        }), 201
        
    except Exception as e:
        logger.error(f"Error creating API token: {str(e)}")
        return jsonify({'error': 'Ошибка при создании токена'}), 500

@api_bp.route('/keys', methods=['POST'])
def create_api_key():
    """Создать новый API ключ"""
    try:
        data = request.get_json()
        if not data or 'name' not in data:
            return jsonify({'error': 'Name is required'}), 400

        name = data['name']
        expires_in_days = data.get('expires_in_days', 365)  # По умолчанию ключ действует 1 год
        rate_limit = data.get('rate_limit', 100)  # По умолчанию 100 запросов в минуту

        key = ApiKey(
            key=generate_api_key(),
            name=name,
            expires_at=datetime.utcnow() + timedelta(days=expires_in_days),
            rate_limit=rate_limit
        )

        db.session.add(key)
        db.session.commit()

        return jsonify({
            'key': key.key,
            'name': key.name,
            'expires_at': key.expires_at.isoformat() if key.expires_at else None,
            'rate_limit': key.rate_limit
        }), 201

    except Exception as e:
        logger.error(f"Error creating API key: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/keys/<key>', methods=['GET'])
def get_api_key_info(key):
    """Получить информацию об API ключе"""
    try:
        api_key = ApiKey.query.filter_by(key=key).first()
        if not api_key:
            return jsonify({'error': 'API key not found'}), 404

        return jsonify({
            'name': api_key.name,
            'is_active': api_key.is_active,
            'created_at': api_key.created_at.isoformat(),
            'last_used_at': api_key.last_used_at.isoformat() if api_key.last_used_at else None,
            'expires_at': api_key.expires_at.isoformat() if api_key.expires_at else None,
            'rate_limit': api_key.rate_limit,
            'downloads_count': api_key.downloads_count
        })

    except Exception as e:
        logger.error(f"Error getting API key info: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/keys/<key>', methods=['DELETE'])
def delete_api_key(key):
    """Удалить API ключ"""
    try:
        api_key = ApiKey.query.filter_by(key=key).first()
        if not api_key:
            return jsonify({'error': 'API key not found'}), 404

        db.session.delete(api_key)
        db.session.commit()

        return '', 204

    except Exception as e:
        logger.error(f"Error deleting API key: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/keys/<key>/deactivate', methods=['POST'])
def deactivate_api_key(key):
    """Деактивировать API ключ"""
    try:
        api_key = ApiKey.query.filter_by(key=key).first()
        if not api_key:
            return jsonify({'error': 'API key not found'}), 404

        api_key.is_active = False
        db.session.add(api_key)
        db.session.commit()

        return jsonify({'message': 'API key deactivated'})

    except Exception as e:
        logger.error(f"Error deactivating API key: {str(e)}")
        return jsonify({'error': str(e)}), 500

# Добавляем декоратор require_api_key ко всем эндпоинтам, требующим авторизации
@api_bp.route('/info', methods=['GET'])
@require_api_key
def get_info():
    """Get basic video metadata without formats"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    try:
        info = get_cached_video_info(url)
        return jsonify(info)
    except Exception as e:
        logger.error(f"Error getting video info: {str(e)}")
        return jsonify({'error': str(e)}), 400

@api_bp.route('/formats', methods=['GET'])
@require_api_key
def get_formats():
    """Get available video formats"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    try:
        filtered = request.args.get('filtered', 'false').lower() == 'true'
        logger.debug(f"Getting formats with filtered={filtered}")
        formats = get_cached_formats(url, filtered=filtered)
        return jsonify(formats)
    except Exception as e:
        logger.error(f"Error getting video formats: {str(e)}")
        return jsonify({'error': str(e)}), 400

@api_bp.route('/download', methods=['GET'])
@require_api_key
def create_download():
    """Create download task"""
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({'error': 'URL parameter is required'}), 400

        format_id = request.args.get('format')
        video_format_id = request.args.get('video_format_id')
        audio_format_id = request.args.get('audio_format_id')
        audio_only = request.args.get('audio_only', 'false').lower() == 'true'
        convert_to_mp3 = request.args.get('convert_to_mp3', 'false').lower() == 'true'
        
        if audio_only:
            if not audio_format_id and not format_id:
                return jsonify({'error': 'Either format or audio_format_id is required for audio download'}), 400
        elif not format_id and (not video_format_id or not audio_format_id):
            return jsonify({'error': 'Either format or both video_format_id and audio_format_id are required'}), 400
            
        # Get video info for format validation
        formats = get_cached_formats(url, filtered=True)
        video_info = get_cached_formats(url, filtered=False)
        
        if format_id:
            # Проверяем, является ли format_id качеством видео (SD, HD, FullHD, 2K, 4K) или аудио (low, medium, high)
            if format_id in ['SD', 'HD', 'FullHD', '2K', '4K']:
                if format_id not in formats.get('formats', {}):
                    return jsonify({'error': f'Quality {format_id} is not available for this video'}), 400
                    
                format_data = formats['formats'][format_id]
                video_format_id = format_data['video']['format_id']
                audio_format_id = format_data['audio']['format_id']
                
                # Получаем полную информацию о форматах для ответа
                video_format = next((f for f in video_info if f.get('format_id') == video_format_id), {})
                audio_format = next((f for f in video_info if f.get('format_id') == audio_format_id), {})
                
                task_id = UUID(bytes=os.urandom(16))
                download = Download(
                    task_id=task_id,
                    url=url,
                    video_format=video_format_id,
                    audio_format=audio_format_id
                )
            elif format_id in ['low', 'medium', 'high']:
                if format_id not in formats.get('audio_only', {}):
                    return jsonify({'error': f'Audio quality {format_id} is not available for this video'}), 400
                    
                format_data = formats['audio_only'][format_id]
                audio_format_id = format_data['format']['format_id']
                audio_format = format_data['format']
                
                task_id = UUID(bytes=os.urandom(16))
                download = Download(
                    task_id=task_id,
                    url=url,
                    audio_format=audio_format_id
                )
            else:
                # Проверяем существование одиночного формата по ID
                selected_format = None
                for f in video_info:
                    if f.get('format_id') == format_id:
                        selected_format = f
                        break
                
                if not selected_format:
                    return jsonify({'error': f'Invalid format ID: {format_id}'}), 400
                
                task_id = UUID(bytes=os.urandom(16))
                download = Download(
                    task_id=task_id,
                    url=url,
                    format=format_id
                )
        else:
            if audio_only:
                # Проверяем существование аудио формата
                audio_format = next((f for f in video_info if f.get('format_id') == audio_format_id and f.get('acodec') != 'none'), None)
                
                if not audio_format:
                    return jsonify({'error': f'Invalid audio format ID: {audio_format_id}'}), 400
                
                task_id = UUID(bytes=os.urandom(16))
                download = Download(
                    task_id=task_id,
                    url=url,
                    audio_format=audio_format_id
                )
            else:
                # Проверяем существование видео и аудио форматов
                video_format = None
                audio_format = None
                for f in video_info:
                    if f.get('format_id') == video_format_id and f.get('vcodec') != 'none':
                        video_format = f
                    elif f.get('format_id') == audio_format_id and f.get('acodec') != 'none':
                        audio_format = f
                
                if not video_format:
                    return jsonify({'error': f'Invalid video format ID: {video_format_id}'}), 400
                if not audio_format:
                    return jsonify({'error': f'Invalid audio format ID: {audio_format_id}'}), 400
                
                task_id = UUID(bytes=os.urandom(16))
                download = Download(
                    task_id=task_id,
                    url=url,
                    video_format=video_format_id,
                    audio_format=audio_format_id
                )
            
        db.session.add(download)
        db.session.commit()
        
        # Start async download
        if format_id and format_id not in ['SD', 'HD', 'FullHD', '2K', '4K', 'low', 'medium', 'high']:
            start_download_task(str(task_id), url, format_id=format_id)
        else:
            start_download_task(
                str(task_id), 
                url, 
                video_format_id=video_format_id, 
                audio_format_id=audio_format_id,
                audio_only=audio_only,
                convert_to_mp3=convert_to_mp3
            )
        
        # Prepare response
        response = {
            'task_id': str(download.task_id),
            'url': download.url,
            'created_at': download.created_at.isoformat(),
            'audio_only': audio_only,
            'convert_to_mp3': convert_to_mp3
        }

        # Add format specific information
        if format_id and format_id not in ['SD', 'HD', 'FullHD', '2K', '4K', 'low', 'medium', 'high']:
            response.update({
                'format': download.format,
                'format_info': {
                    'format': selected_format.get('format'),
                    'ext': selected_format.get('ext'),
                    'resolution': selected_format.get('resolution'),
                    'filesize': selected_format.get('filesize'),
                    'filesize_mb': round(selected_format.get('filesize', 0) / 1024 / 1024, 2) if selected_format.get('filesize') else None,
                    'filesize_approx': selected_format.get('filesize_approx'),
                    'filesize_approx_mb': round(selected_format.get('filesize_approx', 0) / 1024 / 1024, 2) if selected_format.get('filesize_approx') else None
                }
            })
        elif format_id in ['low', 'medium', 'high']:
            format_data = formats['audio_only'][format_id]
            response.update({
                'format': format_id,
                'format_info': {
                    'format': format_data['format'].get('format'),
                    'ext': format_data['format'].get('ext'),
                    'bitrate': format_data['bitrate'],
                    'filesize': format_data['format'].get('filesize'),
                    'filesize_mb': round(format_data['format'].get('filesize', 0) / 1024 / 1024, 2) if format_data['format'].get('filesize') else None,
                    'filesize_approx': format_data['format'].get('filesize_approx'),
                    'filesize_approx_mb': round(format_data['format'].get('filesize_approx', 0) / 1024 / 1024, 2) if format_data['format'].get('filesize_approx') else None
                }
            })
        else:
            response.update({
                'video_format': download.video_format,
                'audio_format': download.audio_format,
                'quality': format_id if format_id in ['SD', 'HD', 'FullHD', '2K', '4K'] else None,
                'format_info': {
                    'video': {
                        'format': video_format.get('format'),
                        'ext': video_format.get('ext'),
                        'resolution': video_format.get('resolution'),
                        'filesize': video_format.get('filesize'),
                        'filesize_mb': round(video_format.get('filesize', 0) / 1024 / 1024, 2) if video_format.get('filesize') else None,
                        'filesize_approx': video_format.get('filesize_approx'),
                        'filesize_approx_mb': round(video_format.get('filesize_approx', 0) / 1024 / 1024, 2) if video_format.get('filesize_approx') else None
                    },
                    'audio': {
                        'format': audio_format.get('format'),
                        'ext': audio_format.get('ext'),
                        'filesize': audio_format.get('filesize'),
                        'filesize_mb': round(audio_format.get('filesize', 0) / 1024 / 1024, 2) if audio_format.get('filesize') else None,
                        'filesize_approx': audio_format.get('filesize_approx'),
                        'filesize_approx_mb': round(audio_format.get('filesize_approx', 0) / 1024 / 1024, 2) if audio_format.get('filesize_approx') else None
                    }
                }
            })
            
        return jsonify(response), 202

    except ValidationError as err:
        return jsonify({'error': err.messages}), 400
    except Exception as e:
        logger.error(f"Error creating download: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/download/<task_id>', methods=['GET'])
def get_download_status(task_id):
    """Get download task status"""
    try:
        task_uuid = UUID(task_id)
        download = Download.query.filter_by(task_id=task_uuid).first()
        if not download:
            return jsonify({'error': 'Download task not found'}), 404

        result = DownloadSchema().dump(download)
        if result.get('file_path'):
            # Add full HTTPS download URLs if file exists
            host = request.host
            result['download_url'] = f"https://{host}/api/download/{task_id}/file"
            
            # Add direct file URL with extension if download is completed
            if download.status == 'completed':
                # Get file extension based on format
                ext = 'mp4'  # default extension
                if download.format:
                    # Get format info from video info
                    video_info = get_cached_formats(download.url)
                    for f in video_info:
                        if f.get('format_id') == download.format:
                            ext = f.get('ext', 'mp4')
                            break
                elif download.audio_format and not download.video_format:
                    # Если это только аудио
                    formats = get_cached_formats(download.url, filtered=True)
                    for quality, data in formats.get('audio_only', {}).items():
                        if data['format']['format_id'] == download.audio_format:
                            # Если включена конвертация в MP3, используем mp3
                            if 'mp3' in download.file_path.lower():
                                ext = 'mp3'
                            else:
                                ext = data['format'].get('ext', 'mp3')
                            break
                result['file_url'] = f"https://{host}/api/download/{task_id}.{ext}"
            
            # Remove file_path from response since it's internal
            result.pop('file_path', None)
        return jsonify(result)
    except ValueError as e:
        logger.error(f"Invalid UUID format: {task_id}")
        return jsonify({'error': 'Invalid task ID format'}), 400

@api_bp.route('/download/<task_id>/file', methods=['GET'])
@api_bp.route('/download/<task_id>.<ext>', methods=['GET'])
def download_file(task_id, ext=None):
    """Download the completed file
    Supports two URL formats:
    - /api/download/{task_id}/file
    - /api/download/{task_id}.{ext}
    """
    logger.info(f"Download request received - task_id: {task_id}, ext: {ext}")
    
    try:
        # Convert task_id to UUID
        task_uuid = UUID(task_id)
        logger.debug(f"Converted task_id to UUID: {task_uuid}")
        
        # Get download record
        download = Download.query.filter_by(task_id=task_uuid).first()
        if not download:
            logger.error(f"Download task not found: {task_uuid}")
            all_tasks = Download.query.all()
            logger.debug(f"Available tasks: {[str(t.task_id) for t in all_tasks]}")
            return jsonify({'error': 'Download task not found'}), 404
            
        logger.info(f"Found download task: {download.task_id}, status={download.status}")
        
        # Verify download status
        if download.status == 'error':
            logger.error(f"Download failed: {download.error}")
            return jsonify({'error': f'Download failed: {download.error}'}), 400
        elif download.status != 'completed':
            logger.warning(f"Download not ready: status={download.status}, progress={download.progress}")
            return jsonify({
                'error': 'Download not completed yet',
                'status': download.status,
                'progress': download.progress
            }), 400
        
        # Setup paths
        downloads_dir = os.path.abspath('downloads')
        task_dir = os.path.join(downloads_dir, str(task_uuid))
        logger.debug(f"Looking for files in: {task_dir}")
        
        if not os.path.exists(task_dir):
            logger.error(f"Task directory not found: {task_dir}")
            return jsonify({'error': 'Download directory not found'}), 404
        
        try:
            # Check database file path first
            if download.file_path and os.path.exists(download.file_path):
                actual_file = download.file_path
                logger.info(f"Using file from database: {actual_file}")
            else:
                # Search in task directory
                logger.info(f"Searching for files in: {task_dir}")
                media_files = []
                
                # Определяем список расширений для поиска
                if download.audio_format and not download.video_format:
                    # Если это только аудио
                    extensions = ['.mp3', '.m4a', '.opus', '.webm', '.aac']
                else:
                    # Если это видео или комбинированный формат
                    extensions = ['.mp4', '.mkv', '.webm', '.m4a']
                
                for ext in extensions:
                    pattern = os.path.join(task_dir, f'*{ext}')
                    found = glob.glob(pattern)
                    if found:
                        logger.debug(f"Found files matching {pattern}: {found}")
                        media_files.extend(found)
                
                if not media_files:
                    logger.error(f"No media files found in {task_dir}")
                    return jsonify({'error': 'Media file not found'}), 404
                
                # Get most recent file
                media_files.sort(key=lambda x: os.path.getmtime(x), reverse=True)
                actual_file = media_files[0]
                logger.info(f"Selected most recent file: {actual_file}")
                
                # Update database
                download.file_path = actual_file
                db.session.add(download)
                db.session.commit()
            
            # Verify file
            file_stat = os.stat(actual_file)
            if file_stat.st_size == 0:
                logger.error(f"File is empty: {actual_file}")
                return jsonify({'error': 'File is empty'}), 500
            
            # Check for temporary files
            temp_files = []
            for pattern in ['*.part', '*.ytdl', '*.temp']:
                temp_files.extend(glob.glob(os.path.join(task_dir, pattern)))
            
            if temp_files:
                logger.warning(f"Found temporary files: {temp_files}")
                return jsonify({
                    'error': 'Download still in progress',
                    'status': 'downloading'
                }), 400
            
            # Check file stability
            initial_size = file_stat.st_size
            time.sleep(1)
            current_size = os.path.getsize(actual_file)
            
            if current_size != initial_size:
                logger.warning(f"File size changing: {initial_size} -> {current_size}")
                return jsonify({
                    'error': 'File still being written',
                    'status': 'processing'
                }), 400
            
            # Ensure file is readable
            if not os.access(actual_file, os.R_OK):
                logger.warning(f"Fixing permissions for {actual_file}")
                try:
                    os.chmod(actual_file, 0o644)
                except Exception as e:
                    logger.error(f"Failed to set file permissions: {e}")
                    return jsonify({'error': 'File not accessible'}), 403
            
            # Serve the file
            logger.info(f"Serving file: {actual_file} ({file_stat.st_size} bytes)")
            return send_file(
                actual_file,
                as_attachment=True,
                download_name=os.path.basename(actual_file)
            )
            
        except OSError as e:
            logger.error(f"OS error accessing file: {str(e)}", exc_info=True)
            return jsonify({'error': 'Error accessing file'}), 500
            
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}", exc_info=True)
            return jsonify({'error': 'Internal server error'}), 500
            
    except ValueError as e:
        logger.error(f"Invalid UUID format: {task_id}")
        return jsonify({'error': 'Invalid task ID format'}), 400

@api_bp.route('/audio/formats', methods=['GET'])
@require_api_key
def get_audio_formats():
    """
    Получение доступных аудио форматов
    ---
    tags:
      - audio
    parameters:
      - name: url
        in: query
        type: string
        required: true
        description: URL видео для получения форматов
    responses:
      200:
        description: Список доступных аудио форматов
        schema:
          type: array
          items:
            type: object
            properties:
              format_id:
                type: string
                description: ID формата
              format:
                type: string
                description: Описание формата
              ext:
                type: string
                description: Расширение файла
              filesize:
                type: integer
                description: Размер файла в байтах
              filesize_approx:
                type: integer
                description: Приблизительный размер файла в байтах
              acodec:
                type: string
                description: Аудио кодек
              abr:
                type: number
                description: Битрейт аудио (kbps)
              asr:
                type: integer
                description: Частота дискретизации (Hz)
              quality:
                type: string
                enum: [low, medium, high]
                description: Качество аудио
      400:
        description: Ошибка в параметрах запроса
      401:
        description: Отсутствует или неверный API ключ
      500:
        description: Внутренняя ошибка сервера
    """
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    try:
        formats = get_cached_formats(url, filtered=False)
        
        # Filter audio-only formats
        audio_formats = []
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                audio_formats.append({
                    'format_id': f.get('format_id'),
                    'format': f.get('format'),
                    'ext': f.get('ext'),
                    'filesize': f.get('filesize'),
                    'filesize_approx': f.get('filesize_approx'),
                    'acodec': f.get('acodec'),
                    'abr': f.get('abr'),
                    'asr': f.get('asr'),
                    'quality': 'low' if f.get('abr', 0) < 128 else ('high' if f.get('abr', 0) > 192 else 'medium')
                })
        
        return jsonify(audio_formats)
        
    except Exception as e:
        logger.error(f"Error getting audio formats: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/audio/download', methods=['GET'])
@require_api_key
def create_audio_download():
    """
    Создание задачи на скачивание аудио
    ---
    tags:
      - audio
    parameters:
      - name: url
        in: query
        type: string
        required: true
        description: URL видео для скачивания
      - name: format
        in: query
        type: string
        required: true
        description: Качество аудио (low, medium, high) или ID конкретного формата
      - name: convert_to_mp3
        in: query
        type: boolean
        default: false
        description: Конвертировать ли аудио в MP3 формат
    responses:
      202:
        description: Задача на скачивание создана успешно
        schema:
          type: object
          properties:
            task_id:
              type: string
              description: Уникальный идентификатор задачи
            url:
              type: string
              description: URL видео
            created_at:
              type: string
              format: date-time
              description: Время создания задачи
            audio_only:
              type: boolean
              description: Всегда true для аудио скачивания
            convert_to_mp3:
              type: boolean
              description: Выбрана ли конвертация в MP3
            format:
              type: string
              description: Выбранное качество или ID формата
            format_info:
              type: object
              description: Информация о выбранном формате
      400:
        description: Ошибка в параметрах запроса
      401:
        description: Отсутствует или неверный API ключ
      500:
        description: Внутренняя ошибка сервера
    """
    try:
        url = request.args.get('url')
        if not url:
            return jsonify({'error': 'URL parameter is required'}), 400

        format_id = request.args.get('format')
        convert_to_mp3 = request.args.get('convert_to_mp3', 'false').lower() == 'true'
        
        # Get available formats
        formats = get_cached_formats(url, filtered=True)
        video_info = get_cached_formats(url, filtered=False)
        
        # Determine audio format ID based on quality
        if format_id in ['low', 'medium', 'high']:
            if format_id not in formats.get('audio_only', {}):
                return jsonify({'error': f'Audio quality {format_id} is not available for this video'}), 400
                
            format_data = formats['audio_only'][format_id]
            audio_format_id = format_data['format']['format_id']
            audio_format = format_data['format']
        else:
            # Use provided format ID directly
            audio_format_id = format_id
            
            # Verify format exists and is audio
            audio_format = next((f for f in video_info if f.get('format_id') == audio_format_id and f.get('acodec') != 'none'), None)
            if not audio_format:
                return jsonify({'error': f'Invalid audio format ID: {audio_format_id}'}), 400
        
        # Create download task
        task_id = UUID(bytes=os.urandom(16))
        download = Download(
            task_id=task_id,
            url=url,
            audio_format=audio_format_id
        )
        
        db.session.add(download)
        db.session.commit()
        
        # Start async download
        start_download_task(
            str(task_id),
            url,
            audio_format_id=audio_format_id,
            audio_only=True,
            convert_to_mp3=convert_to_mp3
        )
        
        # Prepare response
        response = {
            'task_id': str(download.task_id),
            'url': download.url,
            'created_at': download.created_at.isoformat(),
            'audio_only': True,
            'convert_to_mp3': convert_to_mp3,
            'format': format_id,
            'format_info': {
                'format': audio_format.get('format'),
                'ext': audio_format.get('ext'),
                'filesize': audio_format.get('filesize'),
                'filesize_mb': round(audio_format.get('filesize', 0) / 1024 / 1024, 2) if audio_format.get('filesize') else None,
                'filesize_approx': audio_format.get('filesize_approx'),
                'filesize_approx_mb': round(audio_format.get('filesize_approx', 0) / 1024 / 1024, 2) if audio_format.get('filesize_approx') else None
            }
        }
        
        return jsonify(response), 202
        
    except Exception as e:
        logger.error(f"Error creating audio download: {str(e)}")
        return jsonify({'error': str(e)}), 500
