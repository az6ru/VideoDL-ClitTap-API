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
from api.schemas import VideoInfoSchema, DownloadSchema, CombinedVideoInfoSchema
from utils.downloader import get_cached_video_info, get_cached_formats, start_download_task
from api.middleware import require_api_key
import logging
from functools import wraps
import re
from transliterate import translit
import json

logger = logging.getLogger(__name__)

api_bp = Blueprint('api', __name__)

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, datetime):
            return obj.isoformat()
        if isinstance(obj, UUID):
            return str(obj)
        return super().default(obj)

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
                    audio_format=audio_format_id,
                    audio_only=True,
                    convert_to_mp3=convert_to_mp3
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
                # Формируем имя файла для скачивания, но не для отображения
                safe_title = get_safe_filename(download.title or os.path.splitext(os.path.basename(download.file_path))[0])
                
                # Добавляем информацию о качестве для аудио
                if download.audio_format and not download.video_format:
                    quality = 'high' if download.audio_format.endswith('-high') else \
                             'medium' if download.audio_format.endswith('-medium') else 'low'
                    safe_title = f"{safe_title}_{quality}"
                
                # Определяем расширение
                if download.convert_to_mp3:
                    ext = 'mp3'
                elif download.file_path:
                    ext = os.path.splitext(download.file_path)[1].lstrip('.')
                else:
                    ext = 'mp3' if getattr(download, 'convert_to_mp3', False) else 'mp4'
                    if download.format:
                        # Get format info from video info
                        video_info = get_cached_formats(download.url)
                        for f in video_info:
                            if f.get('format_id') == download.format:
                                ext = f.get('ext', ext)
                                break
                    elif download.audio_format and not download.video_format:
                        # Если это только аудио
                        formats = get_cached_formats(download.url, filtered=True)
                        for quality, data in formats.get('audio_only', {}).items():
                            if data['format']['format_id'] == download.audio_format:
                                if getattr(download, 'convert_to_mp3', False):
                                    ext = 'mp3'
                                else:
                                    ext = data['format'].get('ext', ext)
                                break
                
                result['file_url'] = f"https://{host}/api/download/{task_id}/{safe_title}.{ext}"
            
            # Remove file_path from response since it's internal
            result.pop('file_path', None)

        response = jsonify(result)
        response.ensure_ascii = False
        return response
    except ValueError as e:
        logger.error(f"Invalid UUID format: {task_id}")
        return jsonify({'error': 'Invalid task ID format'}), 400

def get_safe_filename(s):
    """
    Преобразует строку в безопасное имя файла.
    Транслитерирует русские буквы в латиницу и заменяет недопустимые символы.
    """
    # Транслитерация русских букв в латиницу
    try:
        s = translit(s, language_code='ru', reversed=True, strict=False)
    except:
        # Если транслитерация не удалась, используем базовую замену
        replacements = {
            'а': 'a', 'б': 'b', 'в': 'v', 'г': 'g', 'д': 'd', 'е': 'e', 'ё': 'yo',
            'ж': 'zh', 'з': 'z', 'и': 'i', 'й': 'y', 'к': 'k', 'л': 'l', 'м': 'm',
            'н': 'n', 'о': 'o', 'п': 'p', 'р': 'r', 'с': 's', 'т': 't', 'у': 'u',
            'ф': 'f', 'х': 'h', 'ц': 'ts', 'ч': 'ch', 'ш': 'sh', 'щ': 'sch',
            'ъ': '', 'ы': 'y', 'ь': '', 'э': 'e', 'ю': 'yu', 'я': 'ya',
            'А': 'A', 'Б': 'B', 'В': 'V', 'Г': 'G', 'Д': 'D', 'Е': 'E', 'Ё': 'Yo',
            'Ж': 'Zh', 'З': 'Z', 'И': 'I', 'Й': 'Y', 'К': 'K', 'Л': 'L', 'М': 'M',
            'Н': 'N', 'О': 'O', 'П': 'P', 'Р': 'R', 'С': 'S', 'Т': 'T', 'У': 'U',
            'Ф': 'F', 'Х': 'H', 'Ц': 'Ts', 'Ч': 'Ch', 'Ш': 'Sh', 'Щ': 'Sch',
            'Ъ': '', 'Ы': 'Y', 'Ь': '', 'Э': 'E', 'Ю': 'Yu', 'Я': 'Ya'
        }
        for cyr, lat in replacements.items():
            s = s.replace(cyr, lat)
    
    # Заменяем пробелы на подчеркивания
    s = s.replace(' ', '_')
    
    # Заменяем специальные символы на подчеркивание
    s = re.sub(r'[^\w\-\.]', '_', s)
    
    # Убираем множественные подчеркивания
    s = re.sub(r'_+', '_', s)
    
    # Убираем подчеркивания в начале и конце
    s = s.strip('_')
    
    return s

@api_bp.route('/download/<task_id>/file', methods=['GET'])
@api_bp.route('/download/<task_id>.<ext>', methods=['GET'])
@api_bp.route('/download/<task_id>/<filename>', methods=['GET'])
def download_file(task_id, ext=None, filename=None):
    """Download the completed file
    Supports three URL formats:
    - /api/download/{task_id}/file
    - /api/download/{task_id}.{ext}
    - /api/download/{task_id}/{filename}
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
            
            # Формируем имя файла для скачивания
            title = download.title or os.path.splitext(os.path.basename(actual_file))[0]
            safe_title = get_safe_filename(title)
            
            # Добавляем информацию о качестве для аудио
            if download.audio_format and not download.video_format:
                quality = 'high' if download.audio_format.endswith('-high') else \
                         'medium' if download.audio_format.endswith('-medium') else 'low'
                safe_title = f"{safe_title}_{quality}"
            
            # Определяем расширение
            if download.convert_to_mp3:
                ext = 'mp3'
            else:
                ext = os.path.splitext(actual_file)[1].lstrip('.')
            
            download_name = f"{safe_title}.{ext}"
            
            # Serve the file
            logger.info(f"Serving file: {actual_file} ({file_stat.st_size} bytes) as {download_name}")
            return send_file(
                actual_file,
                as_attachment=True,
                download_name=download_name
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

def determine_audio_quality(format_info):
    """Определяет качество аудио на основе характеристик"""
    abr = format_info.get('abr', 0)
    asr = format_info.get('asr', 0)
    
    if abr >= 256 or asr >= 48000:
        return 'high'
    elif abr >= 128 or asr >= 44100:
        return 'medium'
    else:
        return 'low'

def format_size(size):
    """Форматирует размер файла в человекочитаемый вид"""
    if not size:
        return None
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024:
            return f"{size:.2f} {unit}"
        size /= 1024
    return f"{size:.2f} TB"

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
      - name: grouped
        in: query
        type: boolean
        required: false
        default: false
        description: Группировать форматы по качеству
    responses:
      200:
        description: Список доступных аудио форматов
        content:
          application/json:
            schema:
              oneOf:
                - type: array
                  items:
                    $ref: '#/components/schemas/AudioFormat'
                - type: object
                  properties:
                    low:
                      type: array
                      items:
                        $ref: '#/components/schemas/AudioFormat'
                    medium:
                      type: array
                      items:
                        $ref: '#/components/schemas/AudioFormat'
                    high:
                      type: array
                      items:
                        $ref: '#/components/schemas/AudioFormat'
    """
    url = request.args.get('url')
    grouped = request.args.get('grouped', 'false').lower() == 'true'
    
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    try:
        formats = get_cached_formats(url, filtered=False)
        
        # Filter audio-only formats
        audio_formats = []
        for f in formats:
            if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
                format_info = {
                    'format_id': f.get('format_id'),
                    'format': f.get('format'),
                    'ext': f.get('ext'),
                    'filesize': f.get('filesize'),
                    'filesize_approx': f.get('filesize_approx'),
                    'filesize_formatted': format_size(f.get('filesize')),
                    'filesize_approx_formatted': format_size(f.get('filesize_approx')),
                    'acodec': f.get('acodec'),
                    'abr': f.get('abr'),
                    'asr': f.get('asr')
                }
                format_info['quality'] = determine_audio_quality(f)
                audio_formats.append(format_info)
        
        if not grouped:
            return jsonify(audio_formats)
        
        # Group formats by quality
        grouped_formats = {
            'low': [],
            'medium': [],
            'high': []
        }
        
        for format_info in audio_formats:
            quality = format_info['quality']
            grouped_formats[quality].append(format_info)
        
        # Для каждого качества выбираем лучший формат
        best_formats = {}
        for quality in ['low', 'medium', 'high']:
            formats_group = grouped_formats[quality]
            if formats_group:
                # Сортируем по битрейту и размеру файла
                best_format = max(formats_group, 
                    key=lambda x: (x.get('abr', 0) or 0, x.get('filesize', 0) or 0))
                best_formats[quality] = best_format
        
        return jsonify(best_formats)
        
    except Exception as e:
        logger.error(f"Error getting audio formats: {str(e)}")
        return jsonify({'error': str(e)}), 500

def get_best_audio_format(formats, quality='medium', preferred_codec=None, max_filesize=None):
    """
    Определяет лучший аудио формат на основе параметров
    
    Args:
        formats: Список доступных форматов
        quality: Желаемое качество (low, medium, high)
        preferred_codec: Предпочтительный кодек (mp3, aac, opus)
        max_filesize: Максимальный размер файла в байтах
    """
    audio_formats = []
    
    # Фильтруем только аудио форматы
    for f in formats:
        if f.get('acodec') != 'none' and f.get('vcodec') == 'none':
            f['quality'] = determine_audio_quality(f)
            audio_formats.append(f)
    
    if not audio_formats:
        return None
        
    # Фильтруем по качеству
    quality_formats = [f for f in audio_formats if f['quality'] == quality]
    if not quality_formats:
        # Если нет форматов нужного качества, берем ближайшие
        if quality == 'high':
            quality_formats = [f for f in audio_formats if f['quality'] == 'medium']
        elif quality == 'low':
            quality_formats = [f for f in audio_formats if f['quality'] == 'medium']
        
        if not quality_formats:
            quality_formats = audio_formats
    
    # Фильтруем по размеру файла
    if max_filesize:
        size_formats = [f for f in quality_formats 
                       if f.get('filesize', float('inf')) <= max_filesize or 
                          f.get('filesize_approx', float('inf')) <= max_filesize]
        if size_formats:
            quality_formats = size_formats
    
    # Фильтруем по кодеку
    if preferred_codec:
        codec_formats = [f for f in quality_formats 
                        if f.get('acodec', '').lower().startswith(preferred_codec.lower())]
        if codec_formats:
            quality_formats = codec_formats
    
    # Выбираем лучший формат
    # Сортируем по: битрейту, частоте дискретизации и размеру файла
    best_format = max(quality_formats, 
        key=lambda x: (
            x.get('abr', 0) or 0,
            x.get('asr', 0) or 0,
            x.get('filesize', 0) or x.get('filesize_approx', 0) or 0
        )
    )
    
    return best_format

def get_optimal_audio_format(formats, quality_preference='medium', max_size_mb=None):
    """
    Определяет оптимальный аудио формат на основе параметров и эвристик
    
    Args:
        formats: Список доступных форматов
        quality_preference: Предпочтительное качество (low, medium, high)
        max_size_mb: Максимальный размер в МБ
    """
    # Фильтруем только аудио форматы
    audio_formats = []
    for f in formats:
        if f.get('acodec') != 'none' and f.get('vcodec') == 'none' and f.get('format_id'):
            # Определяем качество
            abr = f.get('abr', 0) or 0
            asr = f.get('asr', 0) or 0
            filesize = f.get('filesize', 0) or f.get('filesize_approx', 0) or 0
            
            # Оценка качества по битрейту
            if abr >= 256 or asr >= 48000:
                quality = 'high'
            elif abr >= 128 or asr >= 44100:
                quality = 'medium'
            else:
                quality = 'low'
                
            # Оценка формата
            score = 0
            
            # Базовая оценка по качеству
            if quality == quality_preference:
                score += 100
            elif (quality == 'medium' and quality_preference == 'high') or \
                 (quality == 'medium' and quality_preference == 'low'):
                score += 50
            elif quality == 'high' and quality_preference == 'low':
                score -= 50
            elif quality == 'low' and quality_preference == 'high':
                score -= 50
                
            # Бонус за популярные кодеки
            acodec = f.get('acodec', '')
            if acodec and isinstance(acodec, str):
                if acodec.startswith('mp4a'):  # AAC
                    score += 20
                elif acodec.startswith('opus'):
                    score += 15
                
            # Штраф за большой размер файла
            if max_size_mb and filesize > max_size_mb * 1024 * 1024:
                score -= 1000
            
            # Бонус за наличие точного размера файла
            if f.get('filesize'):
                score += 10
                
            # Бонус за более высокий битрейт (в пределах разумного)
            if abr > 0:
                score += min(abr / 32, 30)  # Максимум 30 баллов за битрейт
                
            # Бонус за более высокую частоту дискретизации
            if asr > 0:
                score += min(asr / 8000, 20)  # Максимум 20 баллов за частоту
            
            f['score'] = score
            audio_formats.append(f)
    
    if not audio_formats:
        return None
        
    # Выбираем формат с наивысшей оценкой
    best_format = max(audio_formats, key=lambda x: x['score'])
    return best_format['format_id']

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
        required: false
        description: ID формата или качество (low, medium, high)
      - name: convert_to_mp3
        in: query
        type: boolean
        required: false
        default: false
        description: Конвертировать в MP3
    responses:
      202:
        description: Задача создана
        content:
          application/json:
            schema:
              type: object
              properties:
                task_id:
                  type: string
                  format: uuid
                url:
                  type: string
                created_at:
                  type: string
                  format: date-time
                format:
                  type: string
                convert_to_mp3:
                  type: boolean
                format_info:
                  type: object
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
        
        # Получаем информацию о форматах
        formats = get_cached_formats(url, filtered=False)
        
        # Если формат не указан, используем medium качество
        if not format_id:
            format_id = 'medium'
            
        # Определяем формат
        if format_id in ['low', 'medium', 'high']:
            # Выбираем лучший формат для указанного качества
            audio_format_id = get_optimal_audio_format(formats, quality_preference=format_id)
            if not audio_format_id:
                return jsonify({'error': f'No audio formats available for quality {format_id}'}), 400
                
            # Получаем информацию о выбранном формате
            audio_format = next((f for f in formats if f.get('format_id') == audio_format_id), None)
            if not audio_format:
                return jsonify({'error': f'Format {audio_format_id} not found'}), 400
        else:
            # Используем указанный format_id
            audio_format = next((f for f in formats 
                               if f.get('format_id') == format_id 
                               and f.get('acodec') != 'none' 
                               and f.get('vcodec') == 'none'), None)
            if not audio_format:
                return jsonify({'error': f'Invalid audio format ID: {format_id}'}), 400
            audio_format_id = format_id
            
        # Создаем задачу
        task_id = UUID(bytes=os.urandom(16))
        download = Download(
            task_id=task_id,
            url=url,
            audio_format=audio_format_id,
            convert_to_mp3=convert_to_mp3
        )
        
        db.session.add(download)
        db.session.commit()
        
        # Запускаем скачивание
        start_download_task(
            str(task_id),
            url,
            audio_format_id=audio_format_id,
            audio_only=True,
            convert_to_mp3=convert_to_mp3
        )
        
        # Готовим ответ
        response = {
            'task_id': str(task_id),
            'url': url,
            'created_at': download.created_at.isoformat(),
            'format': audio_format_id,
            'convert_to_mp3': convert_to_mp3,
            'format_info': {
                'format': audio_format.get('format'),
                'ext': audio_format.get('ext'),
                'filesize': audio_format.get('filesize'),
                'filesize_mb': round(audio_format.get('filesize', 0) / 1024 / 1024, 2) if audio_format.get('filesize') else None,
                'filesize_approx': audio_format.get('filesize_approx'),
                'filesize_approx_mb': round(audio_format.get('filesize_approx', 0) / 1024 / 1024, 2) if audio_format.get('filesize_approx') else None,
                'quality': determine_audio_quality(audio_format),
                'acodec': audio_format.get('acodec'),
                'abr': audio_format.get('abr'),
                'asr': audio_format.get('asr')
            }
        }
        
        return jsonify(response), 202
        
    except Exception as e:
        logger.error(f"Error creating audio download: {str(e)}")
        return jsonify({'error': str(e)}), 500

@api_bp.route('/combined-info', methods=['GET'])
@require_api_key
def get_combined_info():
    """Get complete video information including video and audio formats"""
    url = request.args.get('url')
    if not url:
        return jsonify({'error': 'URL parameter is required'}), 400

    try:
        # Получаем базовую информацию о видео
        video_info = get_cached_video_info(url)
        
        # Получаем форматы
        formats = get_cached_formats(url, filtered=True)
        
        # Подготавливаем видео форматы
        video_formats = []
        for quality, format_data in formats.get('formats', {}).items():
            if 'video' in format_data:
                format_info = format_data['video']
                format_info['quality'] = quality
                video_formats.append(format_info)
        
        # Подготавливаем аудио форматы
        audio_formats = []
        for quality, format_data in formats.get('formats', {}).items():
            if 'audio' in format_data:
                format_info = format_data['audio']
                format_info['quality'] = quality
                audio_formats.append(format_info)
        
        # Формируем полный ответ
        combined_info = {
            **video_info,
            'video_formats': video_formats,
            'audio_formats': audio_formats
        }
        
        # Валидируем через схему
        schema = CombinedVideoInfoSchema()
        result = schema.dump(combined_info)
        
        return jsonify(result)
        
    except Exception as e:
        logger.error(f"Error getting combined video info: {str(e)}")
        return jsonify({'error': str(e)}), 400
