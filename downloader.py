"""
yt-dlp 下载器封装

文件结构设计:
downloads/
├── {作者名}/
│   ├── {视频标题}/
│   │   ├── video.mp4           # 原始视频
│   │   ├── video.info.json     # 元数据
│   │   ├── video.description   # 描述
│   │   ├── video.jpg           # 缩略图
│   │   ├── subtitles/
│   │   │   ├── original.en.srt     # 原始英文字幕
│   │   │   ├── original.zh.srt     # 原始中文字幕(如有)
│   │   │   ├── translated.zh.srt   # 翻译后字幕 (后续处理)
│   │   │   └── translated.ja.srt   # 其他语言 (后续处理)
│   │   ├── audio/
│   │   │   ├── original.mp3        # 原始音频 (后续处理)
│   │   │   └── tts.zh.mp3          # TTS配音 (后续处理)
│   │   └── output/
│   │       └── final.zh.mp4        # 最终母语视频 (后续处理)
"""
import os
import re
import time
import yt_dlp
from typing import Optional, Dict, Any, Callable, List
from dataclasses import dataclass, field
from enum import Enum
import logging
import json

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# 限流保护配置
RATE_LIMIT_CONFIG = {
    'download_delay': 3,          # 每次下载前等待秒数
    'retry_delay': 30,            # 被限流后等待秒数
    'max_retries': 10,            # 最大重试次数（增加到10次）
    'fragment_retries': 10,       # 片段重试次数
    'rate_limit': 0,              # 不限速，让代理决定速度
}


class DownloadStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class DownloadTask:
    """下载任务"""
    id: str
    url: str
    status: DownloadStatus = DownloadStatus.PENDING
    progress: float = 0.0
    filename: Optional[str] = None
    title: Optional[str] = None
    error: Optional[str] = None
    metadata: Dict[str, Any] = field(default_factory=dict)


def sanitize_filename(name: str, max_length: int = 100) -> str:
    """清理文件名，移除非法字符"""
    if not name:
        return "unknown"
    # 移除非法字符
    name = re.sub(r'[<>:"/\\|?*]', '', name)
    # 移除前后空格和点
    name = name.strip(' .')
    # 替换多个空格为单个
    name = re.sub(r'\s+', ' ', name)
    # 限制长度
    if len(name) > max_length:
        name = name[:max_length].strip()
    return name or "unknown"


class VideoDownloader:
    """视频下载器 - 基于 yt-dlp"""

    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)

    def _get_output_template(self) -> str:
        """
        获取输出路径模板
        结构: downloads/{作者}/{视频标题}/video.{ext}
        """
        return os.path.join(
            self.download_dir,
            '%(uploader|channel|Unknown)s',  # 作者名
            '%(title)s',                      # 视频标题作为文件夹
            'video.%(ext)s'                   # 统一命名为 video
        )

    def _get_subtitle_output_template(self) -> str:
        """字幕输出路径"""
        return os.path.join(
            self.download_dir,
            '%(uploader|channel|Unknown)s',
            '%(title)s',
            'subtitles',
            'original.%(ext)s'
        )

    def _get_ydl_opts(self,
                      progress_callback: Optional[Callable] = None,
                      format_preference: str = "best",
                      download_playlist: bool = False) -> Dict[str, Any]:
        """获取 yt-dlp 配置"""

        # 使用 yt-dlp 支持的模板语法
        # %(uploader,channel,Unknown)s 表示依次尝试 uploader, channel, 最后用 Unknown
        output_template = os.path.join(
            self.download_dir,
            '%(uploader,channel|Unknown)s',
            '%(title).100s',
            '%(title).100s.%(ext)s'
        )

        opts = {
            'format': format_preference,
            # 统一输出路径模板
            'outtmpl': output_template,
            'noplaylist': not download_playlist,
            'quiet': False,
            'no_warnings': False,
            'extract_flat': False,
            'ignoreerrors': True,
            # 字幕选项
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitleslangs': ['en', 'zh-Hans', 'zh-Hant', 'zh', 'ja', 'ko'],
            'subtitlesformat': 'srt/vtt/best',
            # 元数据
            'writethumbnail': True,
            'writedescription': True,
            'writeinfojson': True,
            # 网络设置 - 防限流
            'socket_timeout': 30,
            'retries': RATE_LIMIT_CONFIG['max_retries'],
            'fragment_retries': RATE_LIMIT_CONFIG['max_retries'],
            'skip_unavailable_fragments': True,
            'ratelimit': RATE_LIMIT_CONFIG['rate_limit'],  # 限速 5MB/s
            'sleep_interval': 2,                            # 片段间隔 2 秒
            'max_sleep_interval': 5,                        # 最大间隔 5 秒
            # 后处理 - 转换缩略图为 jpg
            'postprocessors': [{
                'key': 'FFmpegThumbnailsConvertor',
                'format': 'jpg',
            }],
            # 继续下载未完成的文件
            'continuedl': True,
        }

        if progress_callback:
            opts['progress_hooks'] = [progress_callback]

        return opts

    def get_video_info(self, url: str) -> Dict[str, Any]:
        """获取视频信息（不下载）"""
        opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': 'in_playlist',
            'ignoreerrors': True,
        }

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=False)

                is_playlist = info.get('_type') == 'playlist' or 'entries' in info

                if is_playlist:
                    entries = list(info.get('entries', []))
                    return {
                        'id': info.get('id'),
                        'title': info.get('title'),
                        'description': info.get('description'),
                        'uploader': info.get('uploader') or info.get('channel'),
                        'type': 'playlist',
                        'video_count': len(entries),
                        'videos': [
                            {'id': e.get('id'), 'title': e.get('title')}
                            for e in entries[:10] if e
                        ],
                    }
                else:
                    uploader = info.get('uploader') or info.get('channel') or 'Unknown'
                    return {
                        'id': info.get('id'),
                        'title': info.get('title'),
                        'description': info.get('description'),
                        'duration': info.get('duration'),
                        'uploader': uploader,
                        'upload_date': info.get('upload_date'),
                        'view_count': info.get('view_count'),
                        'thumbnail': info.get('thumbnail'),
                        'type': 'video',
                        'formats': len(info.get('formats', [])),
                        'subtitles': list(info.get('subtitles', {}).keys()),
                        'automatic_captions': list(info.get('automatic_captions', {}).keys()),
                        # 预计存储路径
                        'expected_path': f"{sanitize_filename(uploader)}/{sanitize_filename(info.get('title', 'unknown'))}",
                    }
        except Exception as e:
            logger.error(f"获取视频信息失败: {e}")
            raise

    def download(self,
                 url: str,
                 progress_callback: Optional[Callable] = None,
                 format_preference: str = "best",
                 download_playlist: bool = False,
                 max_videos: Optional[int] = None) -> Dict[str, Any]:
        """下载视频或播放列表"""

        # 下载前延迟，防止请求过快
        delay = RATE_LIMIT_CONFIG['download_delay']
        logger.info(f"等待 {delay} 秒后开始下载...")
        time.sleep(delay)

        opts = self._get_ydl_opts(progress_callback, format_preference, download_playlist)

        if max_videos and download_playlist:
            opts['playlistend'] = max_videos

        downloaded_files = []
        downloaded_dirs = []

        def custom_hook(d):
            if progress_callback:
                progress_callback(d)
            if d['status'] == 'finished':
                filepath = d.get('filename')
                if filepath:
                    downloaded_files.append(filepath)
                    # 记录视频所在目录
                    video_dir = os.path.dirname(filepath)
                    if video_dir not in downloaded_dirs:
                        downloaded_dirs.append(video_dir)

        opts['progress_hooks'] = [custom_hook]

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                logger.info(f"开始下载: {url}")
                info = ydl.extract_info(url, download=True)

                if info is None:
                    return {
                        'success': False,
                        'error': '无法获取视频信息',
                        'url': url,
                    }

                # 处理播放列表
                if 'entries' in info:
                    results = []
                    for entry in info['entries']:
                        if entry:
                            uploader = sanitize_filename(
                                entry.get('uploader') or entry.get('channel') or 'Unknown'
                            )
                            title = sanitize_filename(entry.get('title') or 'unknown')
                            video_dir = os.path.join(self.download_dir, uploader, title)

                            results.append({
                                'id': entry.get('id'),
                                'title': entry.get('title'),
                                'uploader': uploader,
                                'video_dir': video_dir,
                            })

                    return {
                        'success': True,
                        'type': 'playlist',
                        'title': info.get('title'),
                        'uploader': info.get('uploader') or info.get('channel'),
                        'total': len(results),
                        'videos': results,
                        'download_dir': self.download_dir,
                    }
                else:
                    # 单个视频
                    uploader = sanitize_filename(
                        info.get('uploader') or info.get('channel') or 'Unknown'
                    )
                    title = sanitize_filename(info.get('title') or 'unknown')
                    video_dir = os.path.join(self.download_dir, uploader, title)

                    # 创建处理目录结构
                    self._ensure_processing_dirs(video_dir)

                    # 写入处理状态文件
                    self._write_status_file(video_dir, info)

                    return {
                        'success': True,
                        'type': 'video',
                        'id': info.get('id'),
                        'title': info.get('title'),
                        'uploader': uploader,
                        'video_dir': video_dir,
                        'duration': info.get('duration'),
                        'filesize': info.get('filesize') or info.get('filesize_approx'),
                    }

        except yt_dlp.utils.DownloadError as e:
            error_msg = str(e)

            # 检测限流错误
            is_rate_limited = any(code in error_msg for code in ['403', '429', 'rate limit', 'too many requests'])

            if is_rate_limited:
                logger.warning(f"检测到限流，建议等待 {RATE_LIMIT_CONFIG['retry_delay']} 秒后重试")
                return {
                    'success': False,
                    'error': '被限流，请稍后重试',
                    'rate_limited': True,
                    'retry_after': RATE_LIMIT_CONFIG['retry_delay'],
                    'url': url,
                }

            # 字幕下载失败但视频成功的情况
            if 'subtitles' in error_msg.lower():
                if downloaded_files:
                    video_dir = os.path.dirname(downloaded_files[0]) if downloaded_files else None
                    return {
                        'success': True,
                        'type': 'video',
                        'title': 'Downloaded',
                        'video_dir': video_dir,
                        'warning': f'字幕下载失败: {error_msg}',
                    }

            logger.error(f"下载失败: {e}")
            return {
                'success': False,
                'error': error_msg,
                'url': url,
            }
        except Exception as e:
            logger.error(f"下载失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'url': url,
            }

    def _ensure_processing_dirs(self, video_dir: str):
        """确保处理目录结构存在"""
        dirs = [
            video_dir,
            os.path.join(video_dir, 'subtitles'),
            os.path.join(video_dir, 'audio'),
            os.path.join(video_dir, 'output'),
        ]
        for d in dirs:
            os.makedirs(d, exist_ok=True)

    def _write_status_file(self, video_dir: str, info: Dict[str, Any]):
        """写入处理状态文件，用于跟踪工作流进度"""
        status = {
            'video_id': info.get('id'),
            'title': info.get('title'),
            'uploader': info.get('uploader') or info.get('channel'),
            'duration': info.get('duration'),
            'upload_date': info.get('upload_date'),
            'original_url': info.get('webpage_url') or info.get('url'),
            'download_time': __import__('datetime').datetime.now().isoformat(),
            'processing_status': {
                'downloaded': True,
                'subtitles_extracted': False,
                'subtitles_translated': False,
                'tts_generated': False,
                'video_merged': False,
                'uploaded_to_cos': False,
            },
            'files': {
                'video': 'video.mp4' if os.path.exists(os.path.join(video_dir, 'video.mp4')) else None,
                'thumbnail': 'thumbnail.jpg' if os.path.exists(os.path.join(video_dir, 'thumbnail.jpg')) else None,
                'metadata': 'metadata.info.json',
            },
            'subtitles': {},
            'translations': {},
            'tts_audio': {},
        }

        # 检查字幕文件
        subtitles_dir = os.path.join(video_dir, 'subtitles')
        if os.path.exists(subtitles_dir):
            for f in os.listdir(subtitles_dir):
                if f.startswith('original.'):
                    lang = f.replace('original.', '').replace('.srt', '').replace('.vtt', '')
                    status['subtitles'][lang] = f
                    status['processing_status']['subtitles_extracted'] = True

        status_file = os.path.join(video_dir, 'status.json')
        with open(status_file, 'w', encoding='utf-8') as f:
            json.dump(status, f, ensure_ascii=False, indent=2)

    def download_channel(self,
                         url: str,
                         progress_callback: Optional[Callable] = None,
                         max_videos: int = 10) -> Dict[str, Any]:
        """下载频道视频"""
        return self.download(
            url,
            progress_callback=progress_callback,
            download_playlist=True,
            max_videos=max_videos
        )


# 测试
if __name__ == "__main__":
    downloader = VideoDownloader("./test_downloads")
    test_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    try:
        info = downloader.get_video_info(test_url)
        print("视频信息:", info)
        print("预计路径:", info.get('expected_path'))
    except Exception as e:
        print(f"测试失败: {e}")
