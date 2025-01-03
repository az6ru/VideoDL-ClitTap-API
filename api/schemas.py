from marshmallow import Schema, fields

class VideoInfoSchema(Schema):
    title = fields.Str(required=True)
    author = fields.Str()
    description = fields.Str()
    duration = fields.Int()
    thumbnail = fields.Str()
    view_count = fields.Int()
    like_count = fields.Int()
    comment_count = fields.Int()
    formats = fields.List(fields.Dict())
    full_info = fields.Dict(required=False)

class DownloadSchema(Schema):
    task_id = fields.Str(required=True)
    url = fields.Str(required=True)
    status = fields.Str(required=True)
    progress = fields.Float()
    title = fields.Str()
    format = fields.Str()
    video_format = fields.Str()
    audio_format = fields.Str()
    created_at = fields.DateTime()
    updated_at = fields.DateTime()
    completed_at = fields.DateTime()
    error = fields.Str()
    file_path = fields.Str()

class CombinedVideoInfoSchema(Schema):
    # Основная информация о видео
    title = fields.Str(required=True)
    author = fields.Str()
    description = fields.Str()
    duration = fields.Int()
    thumbnail = fields.Str()
    view_count = fields.Int()
    like_count = fields.Int()
    comment_count = fields.Int()
    
    # Форматы видео и аудио
    video_formats = fields.List(fields.Dict(), required=True)
    audio_formats = fields.List(fields.Dict(), required=True)
    
    # Дополнительная информация
    upload_date = fields.Str()
    webpage_url = fields.Str()
    channel_url = fields.Str()
    channel_id = fields.Str()
