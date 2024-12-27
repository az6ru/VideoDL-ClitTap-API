import os
import glob
import time
import logging
import threading
from datetime import datetime, timedelta
import yt_dlp
import shutil
from models import Download
from app import db

# Cache for video metadata
from functools import lru_cache
import hashlib

@lru_cache(maxsize=100)
def get_cached_video_info(url):
    """Cache video info results to avoid repeated API calls"""
    return get_video_info(url)

@lru_cache(maxsize=100)
def get_cached_formats(url, filtered=False):
    """Cache video formats to avoid repeated API calls"""
    cache_key = f"{url}_{filtered}"
    return get_video_formats(url, filtered)
logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)  # Устанавливаем уровень логирования

# Configure downloads directory
downloads_dir = os.path.abspath('downloads')
os.makedirs(downloads_dir, exist_ok=True)

def get_video_info(url):
    """Get basic video information without formats"""
    logger.info(f"Extracting basic info for URL: {url}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
            return {
                'title': info.get('title'),
                'author': info.get('uploader'),
                'description': info.get('description'),
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail'),
                'view_count': info.get('view_count'),
                'like_count': info.get('like_count'),
                'comment_count': info.get('comment_count')
            }
    except Exception as e:
        logger.error(f"Error extracting video info: {str(e)}")
        raise

def format_size(size):
    """Format size in bytes to human readable string"""
    if size is None or size <= 0:
        return None
    
    try:
        if size < 1024:
            return f"{size}B"
        elif size < 1024 * 1024:
            return f"{size / 1024:.2f}KiB"
        elif size < 1024 * 1024 * 1024:
            return f"{size / 1024 / 1024:.2f}MiB"
        else:
            return f"{size / 1024 / 1024 / 1024:.2f}GiB"
    except Exception as e:
        logger.error(f"Error formatting size {size}: {str(e)}")
        return "Unknown"

def get_filtered_formats(formats):
    """Filter and group formats into SD, HD, and FullHD bundles"""
    # Разделяем форматы на видео и аудио
    video_formats = [f for f in formats if f.get('vcodec') != 'none']
    audio_formats = [f for f in formats if f.get('acodec') in ('opus', 'mp4a.40.2') and f.get('vcodec') == 'none']
    
    # Сортируем аудио форматы по размеру и битрейту
    audio_formats.sort(key=lambda x: (
        x.get('filesize', float('inf')) if x.get('filesize') is not None else float('inf'),
        -(x.get('tbr', 0) or 0)
    ))
    
    # Выбираем лучший аудио формат
    best_audio = next((f for f in audio_formats if f.get('tbr', 0) >= 48), audio_formats[0] if audio_formats else None)
    
    # Функция для извлечения высоты из resolution
    def get_height(format_dict):
        resolution = format_dict.get('resolution', '')
        if 'x' in resolution:
            try:
                return int(resolution.split('x')[1])
            except (ValueError, IndexError):
                return 0
        return 0
    
    # Группируем видео форматы по качеству
    sd_formats = [f for f in video_formats if get_height(f) == 480]
    hd_formats = [f for f in video_formats if get_height(f) == 720]
    fullhd_formats = [f for f in video_formats if get_height(f) == 1080]
    
    # Если точные форматы не найдены, используем ближайшие
    if not sd_formats:
        sd_formats = [f for f in video_formats if get_height(f) in range(360, 481)]
    if not hd_formats:
        hd_formats = [f for f in video_formats if get_height(f) in range(481, 721)]
    if not fullhd_formats:
        fullhd_formats = [f for f in video_formats if get_height(f) >= 1080]
    
    # Сортируем форматы по битрейту (выбираем лучшее качество)
    for formats_list in (sd_formats, hd_formats, fullhd_formats):
        formats_list.sort(key=lambda x: (-(x.get('tbr', 0) or 0)))
    
    # Формируем результат
    result = {'formats': {}}
    
    if sd_formats:
        result['formats']['SD'] = {
            'video': sd_formats[0],
            'audio': best_audio
        }
    
    if hd_formats:
        result['formats']['HD'] = {
            'video': hd_formats[0],
            'audio': best_audio
        }
    
    if fullhd_formats:
        result['formats']['FullHD'] = {
            'video': fullhd_formats[0],
            'audio': best_audio
        }
    
    return result

def get_video_formats(url, filtered=False):
    """Get available video formats"""
    logger.info(f"Extracting formats for URL: {url}")
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
    }
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            raw_formats = info.get('formats', [])
            duration = info.get('duration', 0)
            logger.debug(f"Got {len(raw_formats)} formats from yt-dlp")

            formats_info = []
            for f in raw_formats:
                filesize = f.get('filesize')
                filesize_approx = f.get('filesize_approx')
                tbr = f.get('tbr')
                
                # Если размеры отсутствуют, вычисляем их на основе tbr и длительности
                if filesize is None and filesize_approx is None and tbr and duration:
                    filesize_approx = int(tbr * duration * 125)  # tbr в килобитах
                    logger.debug(f"Calculated approximate size from tbr: {filesize_approx}")
                
                logger.debug(f"Processing format {f.get('format_id')}: size={filesize}, approx={filesize_approx}, tbr={tbr}")
                
                formatted_size = format_size(filesize) if filesize else None
                formatted_size_approx = format_size(filesize_approx) if filesize_approx else None
                
                if formatted_size:
                    logger.debug(f"Exact size formatted: {formatted_size}")
                if formatted_size_approx:
                    formatted_size_approx = f"~{formatted_size_approx}"
                    logger.debug(f"Approx size formatted: {formatted_size_approx}")

                format_data = {
                    'format_id': f.get('format_id'),
                    'format': f.get('format'),
                    'ext': f.get('ext'),
                    'resolution': f.get('resolution'),
                    'filesize': filesize,
                    'filesize_approx': filesize_approx,
                    'formatted_filesize': formatted_size,
                    'formatted_filesize_approx': formatted_size_approx,
                    'vcodec': f.get('vcodec'),
                    'acodec': f.get('acodec'),
                    'tbr': tbr,
                    'fps': f.get('fps')
                }
                
                formats_info.append(format_data)
            
            if filtered:
                return get_filtered_formats(formats_info)
            return formats_info
            
    except Exception as e:
        logger.error(f"Error extracting video info: {str(e)}")
        raise

def verify_file_complete(file_path):
    """Verify that downloaded file is complete and ready with optimized checks"""
    logger.debug(f"Starting file verification for: {file_path}")
    if os.path.isfile(file_path):
        task_dir = os.path.dirname(file_path)
        task_id = os.path.basename(task_dir)
    else:
        task_id = os.path.basename(file_path)
        task_dir = os.path.join(downloads_dir, task_id)
    
    logger.info(f"Verifying - Task ID: {task_id}, Directory: {task_dir}")
    
    try:
        # Оптимизированный поиск файлов с использованием os.scandir
        def find_video_files(directory):
            video_extensions = {'.mp4', '.webm', '.mkv', '.m4a'}
            files = []
            with os.scandir(directory) as entries:
                for entry in entries:
                    if entry.is_file() and any(entry.name.endswith(ext) for ext in video_extensions):
                        files.append(entry.path)
            return files
        
        video_files = find_video_files(task_dir)
        if not video_files:
            logger.error(f"No video files found in {task_dir}")
            return False
        
        # Используем самый новый файл
        actual_file = max(video_files, key=os.path.getmtime)
        logger.info(f"Selected file for verification: {actual_file}")
        
        try:
            file_stat = os.stat(actual_file)
            if file_stat.st_size == 0:
                logger.error(f"File is empty: {actual_file}")
                return False
            
            # Оптимизированная проверка временных файлов
            temp_patterns = {'*.part', '*.ytdl', '*.temp'}
            has_temp_files = any(
                any(entry.name.endswith(pat[1:]) for pat in temp_patterns)
                for entry in os.scandir(task_dir)
                if entry.is_file()
            )
            
            if has_temp_files:
                logger.warning("Found temporary files")
                return False
            
            # Быстрая проверка стабильности файла
            initial_size = file_stat.st_size
            time.sleep(0.5)  # Уменьшенное время ожидания
            try:
                current_size = os.path.getsize(actual_file)
                if current_size != initial_size:
                    logger.warning(f"File size changing: {initial_size} -> {current_size}")
                    return False
            except OSError:
                logger.error("Error accessing file during size check")
                return False
            
            # Ensure file is readable
            if not os.access(actual_file, os.R_OK):
                logger.warning(f"Fixing permissions for {actual_file}")
                try:
                    os.chmod(actual_file, 0o644)
                except Exception as e:
                    logger.error(f"Failed to set file permissions: {e}")
                    return False
            
            from app import app
            with app.app_context():
                download = Download.query.filter_by(task_id=task_id).first()
                if download and actual_file != download.file_path:
                    logger.info(f"Updating file path in database: {actual_file}")
                    download.file_path = actual_file
                    db.session.add(download)
                    db.session.commit()
            
            logger.info(f"File verification successful: {actual_file} ({file_stat.st_size} bytes)")
            return True
            
        except OSError as e:
            logger.error(f"OS error accessing file: {str(e)}", exc_info=True)
            return False
            
    except Exception as e:
        logger.error(f"Error verifying file: {str(e)}", exc_info=True)
        return False

def create_progress_bar(progress, downloaded_bytes=None, total_bytes=None, speed=None, eta=None, width=50):
    """Создает ASCII прогресс-бар с дополнительной информацией
    Args:
        progress: значение прогресса от 0 до 100
        downloaded_bytes: скачанный объем в байтах
        total_bytes: общий размер в байтах
        speed: скорость загрузки в байтах/сек
        eta: оставшееся время в секундах
        width: ширина прогресс-бара
    Returns:
        str: отформатированный прогресс-бар
    """
    filled = int(width * progress / 100)
    bar = '█' * filled + '░' * (width - filled)
    
    # Форматируем размеры
    if downloaded_bytes and total_bytes:
        size_info = f"{format_size(downloaded_bytes)}/{format_size(total_bytes)}"
    else:
        size_info = ""
        
    # Форматируем скорость
    if speed:
        speed_info = f" @ {format_size(speed)}/s"
    else:
        speed_info = ""
        
    # Форматируем ETA
    if eta:
        eta_info = f" ETA {eta}"
    else:
        eta_info = ""
        
    stats = []
    if size_info:
        stats.append(size_info)
    if speed_info:
        stats.append(speed_info)
    if eta_info:
        stats.append(eta_info)
        
    stats_str = " ".join(stats)
    return f"\r[{bar}] {progress:.1f}% {stats_str}"

def download_progress_hook(d):
    """Progress hook для отслеживания процесса загрузки с визуальным прогресс-баром"""
    task_id = d['task_id']
    
    try:
        from app import app
        with app.app_context():
            if d['status'] == 'downloading':
                progress = 0
                if 'total_bytes_estimate' in d:
                    progress = (d.get('downloaded_bytes', 0) / d['total_bytes_estimate']) * 100
                elif 'total_bytes' in d:
                    progress = (d.get('downloaded_bytes', 0) / d['total_bytes']) * 100
                elif 'total_fragments' in d:
                    progress = (d.get('fragment_index', 0) / d['total_fragments']) * 100
                
                Download.query.filter_by(task_id=task_id).update({
                    'progress': min(95, progress),
                    'status': 'downloading'
                })
                db.session.commit()

                # Собираем информацию о прогрессе
                downloaded_bytes = d.get('downloaded_bytes', 0)
                total_bytes = d.get('total_bytes') or d.get('total_bytes_estimate')
                speed = d.get('speed')
                eta = d.get('eta')
                
                progress_bar = create_progress_bar(
                    progress=progress,
                    downloaded_bytes=downloaded_bytes,
                    total_bytes=total_bytes,
                    speed=speed,
                    eta=eta
                )
                if progress > 0:  # Показываем только если есть прогресс
                    print(f"\033[K{progress_bar}", end="", flush=True)  # \033[K очищает строку
                
            elif d['status'] == 'finished':
                logger.info(f"Download finished for task {task_id}")
                download = Download.query.filter_by(task_id=task_id).first()
                if not download:
                    logger.error(f"Download record not found for task {task_id}")
                    return
                
                downloaded_file = d.get('filename')
                if not downloaded_file:
                    logger.error(f"No filename provided for task {task_id}")
                    return
                
                logger.info(f"Download finished for task {task_id}, file: {downloaded_file}")
                
                filename = os.path.basename(downloaded_file)
                final_path = os.path.join(downloads_dir, task_id, filename)
                
                download.status = 'processing'
                download.progress = 95
                download.file_path = final_path
                db.session.add(download)
                db.session.commit()
                
                # Verify file with retries
                max_retries = 3
                retry_delay = 2
                
                for attempt in range(max_retries):
                    logger.debug(f"Verification attempt {attempt + 1}/{max_retries}")
                    time.sleep(retry_delay)
                    
                    if verify_file_complete(final_path):
                        logger.info(f"File verified on attempt {attempt + 1}")
                        download.progress = 100
                        download.status = 'completed'
                        download.completed_at = datetime.utcnow()
                        db.session.add(download)
                        db.session.commit()
                        return
                
                logger.error(f"File verification failed after {max_retries} attempts")
                download.status = 'error'
                download.error = 'File verification failed'
                db.session.add(download)
                db.session.commit()
                
            elif d['status'] == 'error':
                error_msg = str(d.get('error', 'Unknown error'))
                logger.error(f"Download error for task {task_id}: {error_msg}")
                Download.query.filter_by(task_id=task_id).update({
                    'status': 'error',
                    'error': error_msg
                })
                db.session.commit()
                
    except Exception as e:
        logger.error(f"Error in progress hook: {str(e)}", exc_info=True)

def download_video(app, task_id, url, video_format_id=None, audio_format_id=None, format_id=None):
    """Download video with specified format or separate video/audio formats"""
    with app.app_context():
        logger.info(f"Starting download for task {task_id}")
        if format_id:
            logger.info(f"Download parameters - URL: {url}, Format: {format_id}")
        else:
            logger.info(f"Download parameters - URL: {url}, Video Format: {video_format_id}, Audio Format: {audio_format_id}")
        
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                logger.info(f"Successfully extracted video info: {info.get('title')}")
                
                # Создаем директорию для задачи
                task_dir = os.path.join(downloads_dir, task_id)
                os.makedirs(task_dir, mode=0o755, exist_ok=True)
                
                # Чистим старые файлы в директории задачи
                for f in os.listdir(task_dir):
                    file_path = os.path.join(task_dir, f)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.debug(f"Removed existing file: {file_path}")
                
                output_template = os.path.join(task_dir, f"{task_id}.%(ext)s")
                format_spec = format_id if format_id else f"{video_format_id}+{audio_format_id}"
                
                ydl_opts = {
                    'format': format_spec,
                    'progress_hooks': [
                        lambda d: download_progress_hook({**d, 'task_id': task_id})
                    ],
                    'outtmpl': output_template,
                    'merge_output_format': 'mp4',
                    'postprocessors': [{
                        'key': 'FFmpegVideoRemuxer',
                        'preferedformat': 'mp4',
                    }],
                    'writethumbnail': False,
                    'writesubtitles': False,
                    'overwrites': True,
                    'keepvideo': False,
                    'verbose': True,
                    'quiet': False,
                    'no_warnings': False,
                    'ignoreerrors': False,
                    'retries': 5,
                    'fragment_retries': 5,
                    # Оптимизация параметров загрузки
                    'concurrent_fragments': 8,  # Параллельная загрузка фрагментов
                    'buffersize': 1024 * 16,   # Увеличенный размер буфера
                    'file_access_retries': 3,   # Уменьшено количество повторов доступа к файлу
                    'throttledratelimit': None, # Отключение ограничения скорости
                    'sleep_interval': 0,        # Отключение задержки между запросами
                    'max_sleep_interval': 0,    # Отключение максимальной задержки
                    'socket_timeout': 30,       # Таймаут сокета
                    'thread_count': 8           # Количество потоков для загрузки
                }
                
                logger.debug(f"YouTube-DL options: {ydl_opts}")
                
                download = Download.query.filter_by(task_id=task_id).first()
                if download:
                    download.title = info.get('title')
                    download.status = 'downloading'
                    db.session.add(download)
                    db.session.commit()
                    
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl_download:
                        ydl_download.download([url])
                else:
                    logger.error(f"Download record not found for task {task_id}")
                    
        except Exception as e:
            logger.error(f"Error downloading video: {str(e)}")
            download = Download.query.filter_by(task_id=task_id).first()
            if download:
                download.status = 'error'
                download.error = str(e)
                db.session.add(download)
                db.session.commit()

def cleanup_old_files(retention_minutes=5):
    """Очистка старых файлов по истечении времени хранения
    Args:
        retention_minutes: время хранения файлов в минутах (по умолчанию 5 минут)
    """
    while True:
        try:
            current_time = datetime.utcnow()
            cleanup_before = current_time - timedelta(minutes=retention_minutes)
            
            for task_dir in glob.glob(os.path.join(downloads_dir, '*')):
                if not os.path.isdir(task_dir):
                    continue
                
                task_id = os.path.basename(task_dir)
                from app import app
                with app.app_context():
                    download = Download.query.filter_by(task_id=task_id).first()
                    if not download:
                        continue
                    
                    if download.completed_at and download.completed_at < cleanup_before:
                        logger.info(f"Cleaning up task directory: {task_dir}")
                        try:
                            shutil.rmtree(task_dir)
                            download.file_path = None
                            db.session.add(download)
                            db.session.commit()
                        except Exception as e:
                            logger.error(f"Error cleaning up task {task_id}: {e}")
                            
        except Exception as e:
            logger.error(f"Error in cleanup thread: {e}")
            
        time.sleep(60)

# Запуск потока очистки с настраиваемым временем хранения
cleanup_thread = None

def start_cleanup_thread(retention_minutes=5):
    """Запускает поток очистки с указанным временем хранения файлов"""
    global cleanup_thread
    if cleanup_thread is not None:
        return
    
    cleanup_thread = threading.Thread(
        target=cleanup_old_files,
        args=(retention_minutes,),
        daemon=True
    )
    cleanup_thread.start()

# Запускаем поток очистки с дефолтным значением
start_cleanup_thread()

def start_download_task(task_id, url, video_format_id=None, audio_format_id=None, format_id=None, retention_minutes=5):
    """Запуск асинхронной задачи на скачивание
    Args:
        task_id: идентификатор задачи
        url: URL видео
        video_format_id: ID формата видео
        audio_format_id: ID формата аудио
        format_id: ID единого формата
        retention_minutes: время хранения файла в минутах
    """
    from app import app
    thread = threading.Thread(target=download_video,
                            args=(app, task_id, url),
                            kwargs={
                                'video_format_id': video_format_id,
                                'audio_format_id': audio_format_id,
                                'format_id': format_id
                            })
    thread.daemon = True
    thread.start()
