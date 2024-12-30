import os
import glob
import time
import logging
import threading
from datetime import datetime, timedelta
import yt_dlp
import shutil
from models import Download
from extensions import db
from flask import current_app

# Cache for video metadata
from functools import lru_cache
import hashlib

logger = logging.getLogger(__name__)
logger.setLevel(logging.INFO)

# Configure downloads directory
downloads_dir = os.path.abspath('downloads')
os.makedirs(downloads_dir, exist_ok=True)

# Global variables
cleanup_thread = None

@lru_cache(maxsize=100)
def get_cached_video_info(url):
    """Cache video info results to avoid repeated API calls"""
    return get_video_info(url)

@lru_cache(maxsize=100)
def get_cached_formats(url, filtered=False):
    """Cache video formats to avoid repeated API calls"""
    cache_key = f"{url}_{filtered}"
    return get_video_formats(url, filtered)

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
    """Filter and group formats into SD, HD, FullHD, 2K and 4K bundles"""
    video_formats = [f for f in formats if f.get('vcodec') != 'none']
    audio_formats = [f for f in formats if f.get('acodec') in ('opus', 'mp4a.40.2', 'mp3') and f.get('vcodec') == 'none']
    
    audio_formats.sort(key=lambda x: (
        x.get('filesize', float('inf')) if x.get('filesize') is not None else float('inf'),
        -(x.get('tbr', 0) or 0)
    ))
    
    best_audio = next((f for f in audio_formats if f.get('tbr', 0) >= 48), audio_formats[0] if audio_formats else None)
    
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
    uhd2k_formats = [f for f in video_formats if get_height(f) == 1440]  # 2K (1440p)
    uhd4k_formats = [f for f in video_formats if get_height(f) == 2160]  # 4K (2160p)
    
    # Если точные форматы не найдены, используем ближайшие
    if not sd_formats:
        sd_formats = [f for f in video_formats if get_height(f) in range(360, 481)]
    if not hd_formats:
        hd_formats = [f for f in video_formats if get_height(f) in range(481, 721)]
    if not fullhd_formats:
        fullhd_formats = [f for f in video_formats if get_height(f) in range(721, 1081)]
    if not uhd2k_formats:
        uhd2k_formats = [f for f in video_formats if get_height(f) in range(1081, 1441)]
    if not uhd4k_formats:
        uhd4k_formats = [f for f in video_formats if get_height(f) >= 1441]
    
    # Сортируем форматы по битрейту (выбираем лучшее качество)
    for formats_list in (sd_formats, hd_formats, fullhd_formats, uhd2k_formats, uhd4k_formats):
        formats_list.sort(key=lambda x: (-(x.get('tbr', 0) or 0)))
    
    # Группируем аудио форматы по качеству
    audio_qualities = {
        'low': {'min_bitrate': 48, 'max_bitrate': 96},
        'medium': {'min_bitrate': 96, 'max_bitrate': 160},
        'high': {'min_bitrate': 160, 'max_bitrate': float('inf')}
    }
    
    audio_by_quality = {}
    for quality, limits in audio_qualities.items():
        matching_formats = [f for f in audio_formats 
                          if limits['min_bitrate'] <= (f.get('tbr', 0) or 0) < limits['max_bitrate']]
        if matching_formats:
            audio_by_quality[quality] = matching_formats[0]
    
    # Формируем результат
    result = {
        'formats': {},
        'audio_only': {}
    }
    
    if sd_formats:
        result['formats']['SD'] = {
            'video': sd_formats[0],
            'audio': best_audio,
            'resolution': '480p'
        }
    
    if hd_formats:
        result['formats']['HD'] = {
            'video': hd_formats[0],
            'audio': best_audio,
            'resolution': '720p'
        }
    
    if fullhd_formats:
        result['formats']['FullHD'] = {
            'video': fullhd_formats[0],
            'audio': best_audio,
            'resolution': '1080p'
        }
    
    if uhd2k_formats:
        result['formats']['2K'] = {
            'video': uhd2k_formats[0],
            'audio': best_audio,
            'resolution': '1440p'
        }
    
    if uhd4k_formats:
        result['formats']['4K'] = {
            'video': uhd4k_formats[0],
            'audio': best_audio,
            'resolution': '2160p'
        }
    
    # Добавляем форматы только аудио
    for quality, format_data in audio_by_quality.items():
        result['audio_only'][quality] = {
            'format': format_data,
            'quality': quality,
            'bitrate': format_data.get('tbr', 0)
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
                
                if filesize is None and filesize_approx is None and tbr and duration:
                    filesize_approx = int(tbr * duration * 125)
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
        
        actual_file = max(video_files, key=os.path.getmtime)
        logger.info(f"Selected file for verification: {actual_file}")
        
        try:
            file_stat = os.stat(actual_file)
            if file_stat.st_size == 0:
                logger.error(f"File is empty: {actual_file}")
                return False
            
            temp_patterns = {'*.part', '*.ytdl', '*.temp'}
            has_temp_files = any(
                any(entry.name.endswith(pat[1:]) for pat in temp_patterns)
                for entry in os.scandir(task_dir)
                if entry.is_file()
            )
            
            if has_temp_files:
                logger.warning("Found temporary files")
                return False
            
            initial_size = file_stat.st_size
            time.sleep(0.5)
            try:
                current_size = os.path.getsize(actual_file)
                if current_size != initial_size:
                    logger.warning(f"File size changing: {initial_size} -> {current_size}")
                    return False
            except OSError:
                logger.error("Error accessing file during size check")
                return False
            
            if not os.access(actual_file, os.R_OK):
                logger.warning(f"Fixing permissions for {actual_file}")
                try:
                    os.chmod(actual_file, 0o644)
                except Exception as e:
                    logger.error(f"Failed to set file permissions: {e}")
                    return False
            
            with current_app.app_context():
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

def format_time(seconds):
    """Форматирует время в человекочитаемый вид"""
    if not seconds:
        return ""
    
    hours = int(seconds // 3600)
    minutes = int((seconds % 3600) // 60)
    seconds = int(seconds % 60)
    
    if hours > 0:
        return f"{hours}ч {minutes}м {seconds}с"
    elif minutes > 0:
        return f"{minutes}м {seconds}с"
    else:
        return f"{seconds}с"

def create_progress_bar(progress, downloaded_bytes=None, total_bytes=None, speed=None, eta=None, width=50):
    """Создает анимированный цветной прогресс-бар с дополнительной информацией"""
    # ANSI цвета и стили
    GREEN = '\033[38;5;82m'  # Яркий зеленый
    BLUE = '\033[38;5;39m'   # Яркий синий
    YELLOW = '\033[38;5;220m' # Яркий желтый
    GRAY = '\033[38;5;240m'   # Серый для фона
    BOLD = '\033[1m'
    RESET = '\033[0m'
    
    # Символы для анимации
    FILL_CHAR = '█'
    EMPTY_CHAR = '▒'
    
    # Вычисляем заполнение
    filled_width = int(width * progress / 100)
    remaining_width = width - filled_width
    
    # Создаем градиент для заполненной части
    if filled_width > 0:
        bar_fill = GREEN + FILL_CHAR * filled_width + RESET
    else:
        bar_fill = ""
    
    # Создаем фон для незаполненной части
    if remaining_width > 0:
        bar_empty = GRAY + EMPTY_CHAR * remaining_width + RESET
    else:
        bar_empty = ""
    
    # Собираем прогресс-бар
    bar = f"{bar_fill}{bar_empty}"
    
    # Форматируем основную информацию
    progress_text = f"{BOLD}{progress:.1f}%{RESET}"
    
    # Информация о размере
    if downloaded_bytes is not None and total_bytes is not None:
        size_text = f"{BLUE}{format_size(downloaded_bytes)}{RESET} из {BLUE}{format_size(total_bytes)}{RESET}"
    else:
        size_text = ""
    
    # Информация о скорости
    if speed is not None:
        speed_text = f"{YELLOW}{format_size(speed)}/с{RESET}"
    else:
        speed_text = ""
    
    # Оставшееся время
    if eta is not None:
        eta_text = f"осталось {format_time(eta)}"
    else:
        eta_text = ""
    
    # Собираем все компоненты статистики
    stats = []
    if size_text:
        stats.append(size_text)
    if speed_text:
        stats.append(speed_text)
    if eta_text:
        stats.append(eta_text)
    
    stats_str = " │ ".join(stats)  # Используем вертикальную черту для разделения
    
    # Очищаем текущую строку и выводим прогресс-бар
    return f"\r\033[K[{bar}] {progress_text} {stats_str}"

def download_progress_hook(d):
    """Progress hook для отслеживания процесса загрузки с визуальным прогресс-баром"""
    task_id = d['task_id']
    
    try:
        with current_app.app_context():
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
                if progress > 0:
                    print(f"\033[K{progress_bar}", end="", flush=True)
                
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

def download_video(task_id, url, video_format_id=None, audio_format_id=None, format_id=None, audio_only=False, convert_to_mp3=False):
    """Download video with specified format or separate video/audio formats"""
    from app import app  # Импортируем приложение здесь
    
    with app.app_context():  # Используем правильный контекст приложения
        logger.info(f"Starting download for task {task_id}")
        if format_id:
            logger.info(f"Download parameters - URL: {url}, Format: {format_id}")
        else:
            logger.info(f"Download parameters - URL: {url}, Video Format: {video_format_id}, Audio Format: {audio_format_id}")
        
        try:
            with yt_dlp.YoutubeDL({'quiet': True}) as ydl:
                info = ydl.extract_info(url, download=False)
                logger.info(f"Successfully extracted video info: {info.get('title')}")
                
                task_dir = os.path.join(downloads_dir, task_id)
                os.makedirs(task_dir, mode=0o755, exist_ok=True)
                
                for f in os.listdir(task_dir):
                    file_path = os.path.join(task_dir, f)
                    if os.path.isfile(file_path):
                        os.remove(file_path)
                        logger.debug(f"Removed existing file: {file_path}")
                
                output_template = os.path.join(task_dir, f"{task_id}.%(ext)s")
                
                if audio_only:
                    format_spec = audio_format_id
                    postprocessors = [{
                        'key': 'FFmpegExtractAudio',
                        'preferredcodec': 'mp3' if convert_to_mp3 else None,
                        'preferredquality': '192' if convert_to_mp3 else None,
                    }] if convert_to_mp3 else []
                else:
                    format_spec = format_id if format_id else f"{video_format_id}+{audio_format_id}"
                    postprocessors = [{
                        'key': 'FFmpegVideoRemuxer',
                        'preferedformat': 'mp4',
                    }]
                
                ydl_opts = {
                    'format': format_spec,
                    'progress_hooks': [
                        lambda d: download_progress_hook({**d, 'task_id': task_id})
                    ],
                    'outtmpl': output_template,
                    'merge_output_format': 'mp4' if not audio_only else None,
                    'postprocessors': postprocessors,
                    'writethumbnail': False,
                    'writesubtitles': False,
                    'overwrites': True,
                    'keepvideo': False,
                    'verbose': True,
                    'quiet': False,
                    'no_warnings': False,
                    'ignoreerrors': False,
                    'retries': 10,
                    'fragment_retries': 10,
                    'concurrent_fragments': 16,
                    'buffersize': 1024 * 32,
                    'file_access_retries': 5,
                    'throttledratelimit': None,
                    'sleep_interval': 0,
                    'max_sleep_interval': 0,
                    'socket_timeout': 60,
                    'http_chunk_size': 1024 * 1024,
                    'thread_count': 16,
                    'external_downloader': 'aria2c',
                    'external_downloader_args': [
                        '-j', '16',
                        '-x', '16',
                        '-s', '16',
                        '--min-split-size', '1M',
                        '--max-connection-per-server', '16',
                        '--optimize-concurrent-downloads',
                        '--file-allocation=none',
                        '--auto-file-renaming=false'
                    ]
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

def cleanup_old_files(app, retention_hours=24):
    """Очистка старых файлов по истечении времени хранения
    
    Args:
        app: Объект Flask приложения
        retention_hours (int): Время хранения файлов в часах
    """
    while True:
        try:
            current_time = datetime.utcnow()
            cleanup_before = current_time - timedelta(hours=retention_hours)
            
            with app.app_context():
                for task_dir in glob.glob(os.path.join(downloads_dir, '*')):
                    if not os.path.isdir(task_dir):
                        continue
                    
                    task_id = os.path.basename(task_dir)
                    download = Download.query.filter_by(task_id=task_id).first()
                    if not download:
                        continue
                    
                    if download.completed_at and download.completed_at < cleanup_before:
                        logger.info(f"Cleaning up task directory: {task_dir} (older than {retention_hours} hours)")
                        try:
                            shutil.rmtree(task_dir)
                            download.file_path = None
                            db.session.add(download)
                            db.session.commit()
                        except Exception as e:
                            logger.error(f"Error cleaning up task {task_id}: {e}")
                            
        except Exception as e:
            logger.error(f"Error in cleanup thread: {e}")
            
        # Проверяем каждый час
        time.sleep(3600)

def start_cleanup_thread(app, retention_hours=None):
    """Запускает поток очистки с указанным временем хранения файлов
    
    Args:
        app: Объект Flask приложения
        retention_hours (int, optional): Время хранения файлов в часах. 
            Если не указано, берется из переменной окружения CLEANUP_RETENTION_HOURS 
            или используется значение по умолчанию 24 часа.
    """
    global cleanup_thread
    if cleanup_thread is not None:
        return
    
    if retention_hours is None:
        retention_hours = int(os.environ.get('CLEANUP_RETENTION_HOURS', 24))
    
    logger.info(f"Starting cleanup thread with retention time: {retention_hours} hours")
    
    cleanup_thread = threading.Thread(
        target=cleanup_old_files,
        args=(app, retention_hours),
        daemon=True
    )
    cleanup_thread.start()

def start_download_task(task_id, url, video_format_id=None, audio_format_id=None, format_id=None, audio_only=False, convert_to_mp3=False):
    """Запуск асинхронной задачи на скачивание"""
    thread = threading.Thread(target=download_video,
                            args=(task_id, url),
                            kwargs={
                                'video_format_id': video_format_id,
                                'audio_format_id': audio_format_id,
                                'format_id': format_id,
                                'audio_only': audio_only,
                                'convert_to_mp3': convert_to_mp3
                            })
    thread.daemon = True
    thread.start()

def get_available_resolutions(url):
    """Получить список всех доступных разрешений для видео"""
    logger.info(f"Получение доступных разрешений для URL: {url}")
    
    try:
        formats = get_cached_formats(url, filtered=True)
        available_resolutions = []
        
        resolution_mapping = {
            'SD': '480p',
            'HD': '720p',
            'FullHD': '1080p',
            '2K': '1440p',
            '4K': '2160p'
        }
        
        for quality, data in formats.get('formats', {}).items():
            resolution = resolution_mapping.get(quality)
            if resolution:
                available_resolutions.append({
                    'quality': quality,
                    'resolution': resolution,
                    'filesize': data['video'].get('formatted_filesize') or data['video'].get('formatted_filesize_approx')
                })
        
        return available_resolutions
    except Exception as e:
        logger.error(f"Ошибка при получении доступных разрешений: {str(e)}")
        raise
