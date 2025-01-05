import yt_dlp
import logging
from typing import Dict, List, Optional, Union

logger = logging.getLogger(__name__)

class YTDLPWrapper:
    def __init__(self):
        self.default_options = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': False
        }

    def extract_info(self, url: str) -> Dict:
        """
        Извлекает информацию о видео
        """
        try:
            with yt_dlp.YoutubeDL(self.default_options) as ydl:
                info = ydl.extract_info(url, download=False)
                return self._process_info(info)
        except Exception as e:
            logger.error(f"Error extracting info: {str(e)}")
            raise

    def _process_info(self, info: Dict) -> Dict:
        """
        Обрабатывает и форматирует информацию о видео
        """
        processed = {
            'id': info.get('id'),
            'title': info.get('title'),
            'description': info.get('description'),
            'thumbnail': info.get('thumbnail'),
            'duration': info.get('duration'),
            'view_count': info.get('view_count'),
            'like_count': info.get('like_count'),
            'comment_count': info.get('comment_count'),
            'upload_date': info.get('upload_date'),
            'uploader': info.get('uploader'),
            'channel_id': info.get('channel_id'),
            'channel_url': info.get('channel_url'),
            'webpage_url': info.get('webpage_url'),
            'formats': self._process_formats(info.get('formats', []))
        }
        return processed

    def _process_formats(self, formats: List[Dict]) -> Dict:
        """
        Обрабатывает и группирует форматы
        """
        video_formats = []
        audio_formats = []
        combined_formats = []

        for f in formats:
            format_info = {
                'format_id': f.get('format_id'),
                'ext': f.get('ext'),
                'filesize': f.get('filesize'),
                'filesize_approx': f.get('filesize_approx'),
                'tbr': f.get('tbr'),
                'format': f.get('format')
            }

            if f.get('vcodec') != 'none' and f.get('acodec') != 'none':
                format_info.update({
                    'width': f.get('width'),
                    'height': f.get('height'),
                    'fps': f.get('fps'),
                    'vcodec': f.get('vcodec'),
                    'acodec': f.get('acodec'),
                    'abr': f.get('abr'),
                    'type': 'combined'
                })
                combined_formats.append(format_info)
            elif f.get('vcodec') != 'none':
                format_info.update({
                    'width': f.get('width'),
                    'height': f.get('height'),
                    'fps': f.get('fps'),
                    'vcodec': f.get('vcodec'),
                    'type': 'video'
                })
                video_formats.append(format_info)
            elif f.get('acodec') != 'none':
                format_info.update({
                    'abr': f.get('abr'),
                    'asr': f.get('asr'),
                    'acodec': f.get('acodec'),
                    'type': 'audio'
                })
                audio_formats.append(format_info)

        return {
            'video': video_formats,
            'audio': audio_formats,
            'combined': combined_formats
        }

    def get_best_format(self, formats: List[Dict], type: str = 'combined', 
                       quality: str = 'best') -> Optional[Dict]:
        """
        Выбирает лучший формат заданного типа
        """
        if not formats:
            return None

        filtered = [f for f in formats if f.get('type') == type]
        if not filtered:
            return None

        if type == 'video':
            # Сортируем по высоте видео и битрейту
            filtered.sort(key=lambda x: (
                x.get('height', 0),
                x.get('tbr', 0) or 0
            ), reverse=True)
        elif type == 'audio':
            # Сортируем по битрейту аудио
            filtered.sort(key=lambda x: (
                x.get('abr', 0) or 0,
                x.get('asr', 0) or 0
            ), reverse=True)
        else:
            # Для combined форматов сортируем по высоте и общему битрейту
            filtered.sort(key=lambda x: (
                x.get('height', 0),
                x.get('tbr', 0) or 0
            ), reverse=True)

        if quality == 'best':
            return filtered[0]
        elif quality == 'worst':
            return filtered[-1]
        else:
            # Для конкретного качества (например, '720p')
            height = int(quality.rstrip('p'))
            matches = [f for f in filtered if f.get('height') == height]
            return max(matches, key=lambda x: x.get('tbr', 0)) if matches else None

    def download(self, url: str, format_id: str = None, output_template: str = None,
                audio_only: bool = False) -> str:
        """
        Скачивает видео в указанном формате
        """
        options = {
            **self.default_options,
            'format': format_id if format_id else 'best',
            'outtmpl': output_template if output_template else '%(title)s.%(ext)s'
        }

        if audio_only:
            options.update({
                'format': 'bestaudio/best',
                'postprocessors': [{
                    'key': 'FFmpegExtractAudio',
                    'preferredcodec': 'mp3',
                }]
            })

        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(url)
                return ydl.prepare_filename(info)
        except Exception as e:
            logger.error(f"Error downloading: {str(e)}")
            raise 