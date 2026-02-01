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

去重记录:
downloads/
├── .downloaded_videos.json     # 已下载视频 ID 记录
"""
import os
import re
import time
import yt_dlp
from typing import Optional, Dict, Any, Callable, List, Set
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


class UrlType(str, Enum):
    """URL 类型"""
    VIDEO = "video"           # 单个视频
    CHANNEL = "channel"       # 频道视频页面 (@用户名/videos)
    PLAYLIST = "playlist"     # 播放列表


def detect_url_type(url: str) -> UrlType:
    """检测 URL 类型"""
    # 频道视频页面: /@用户名/videos 或 /c/频道名/videos 或 /channel/xxx/videos
    if '/videos' in url and ('/@' in url or '/c/' in url or '/channel/' in url):
        return UrlType.CHANNEL
    # 播放列表
    if 'list=' in url or '/playlist' in url:
        return UrlType.PLAYLIST
    # 频道主页（没有 /videos）
    if '/@' in url or '/c/' in url or '/channel/' in url or '/user/' in url:
        return UrlType.CHANNEL
    # 默认单个视频
    return UrlType.VIDEO


class VideoDownloader:
    """视频下载器 - 基于 yt-dlp"""

    def __init__(self, download_dir: str = "./downloads"):
        self.download_dir = download_dir
        os.makedirs(download_dir, exist_ok=True)
        self.downloaded_record_file = os.path.join(download_dir, '.downloaded_videos.json')

    def _load_downloaded_ids(self) -> Set[str]:
        """加载已下载的视频 ID 列表"""
        if os.path.exists(self.downloaded_record_file):
            try:
                with open(self.downloaded_record_file, 'r') as f:
                    data = json.load(f)
                    return set(data.get('video_ids', []))
            except Exception as e:
                logger.warning(f"加载已下载记录失败: {e}")
        return set()

    def _save_downloaded_id(self, video_id: str):
        """保存已下载的视频 ID"""
        ids = self._load_downloaded_ids()
        ids.add(video_id)
        try:
            with open(self.downloaded_record_file, 'w') as f:
                json.dump({'video_ids': list(ids)}, f, indent=2)
        except Exception as e:
            logger.warning(f"保存已下载记录失败: {e}")

    def _is_video_downloaded(self, video_id: str) -> bool:
        """检查视频是否已下载"""
        return video_id in self._load_downloaded_ids()

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

    def _is_playlist_url(self, url: str) -> bool:
        """检测 URL 是否是播放列表/频道"""
        patterns = ['/videos', '/playlist', '/playlists', '/shorts', '/@', '/c/', '/channel/', '/user/', 'list=']
        return any(p in url for p in patterns)

    def _get_ydl_opts(self,
                      progress_callback: Optional[Callable] = None,
                      format_preference: str = "best",
                      download_playlist: bool = False,
                      sort_order: str = "newest") -> Dict[str, Any]:
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
            # 播放列表排序
            'playlist_items': None,  # 默认不限制
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

        # 播放列表排序配置
        # YouTube 频道 /videos 页面默认按最新排序
        # 如果需要按热门排序，需要修改 URL 或使用 playlistreverse
        if sort_order == 'oldest':
            opts['playlistreverse'] = True
        elif sort_order == 'popular':
            # 热门排序需要在 URL 中指定，这里记录日志提示
            logger.info("热门排序：YouTube 频道需要使用 /videos?view=0&sort=p 参数")

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
                 max_videos: Optional[int] = None,
                 sort_order: str = "newest") -> Dict[str, Any]:
        """下载视频或频道视频（支持去重）"""

        # 检测 URL 类型
        url_type = detect_url_type(url)
        logger.info(f"URL 类型: {url_type.value}")

        # 频道或播放列表自动启用多视频模式
        if url_type in (UrlType.CHANNEL, UrlType.PLAYLIST):
            download_playlist = True

        # 处理热门排序 - 修改 URL
        if sort_order == 'popular' and '/videos' in url:
            if '?' not in url:
                url = url + '?view=0&sort=p'
            elif 'sort=' not in url:
                url = url + '&view=0&sort=p'
            logger.info(f"热门排序，URL 已修改为: {url}")

        # 下载前延迟，防止请求过快
        delay = RATE_LIMIT_CONFIG['download_delay']
        logger.info(f"等待 {delay} 秒后开始下载...")
        time.sleep(delay)

        # 频道/播放列表模式：先获取列表，去重后逐个下载
        if url_type in (UrlType.CHANNEL, UrlType.PLAYLIST) and max_videos:
            return self._download_channel_with_dedup(
                url, url_type, max_videos, sort_order,
                progress_callback, format_preference
            )

        # 单个视频或不限数量的下载
        opts = self._get_ydl_opts(progress_callback, format_preference, download_playlist, sort_order)

        # 限制下载数量（不再要求必须勾选播放列表模式）
        if max_videos:
            opts['playlistend'] = max_videos
            logger.info(f"限制下载数量: {max_videos} 个视频")

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

                # 处理播放列表/频道
                if 'entries' in info:
                    results = []
                    for entry in info['entries']:
                        if entry:
                            video_id = entry.get('id')
                            # 记录已下载的视频 ID
                            if video_id:
                                self._save_downloaded_id(video_id)

                            uploader = sanitize_filename(
                                entry.get('uploader') or entry.get('channel') or 'Unknown'
                            )
                            title = sanitize_filename(entry.get('title') or 'unknown')
                            video_dir = os.path.join(self.download_dir, uploader, title)

                            results.append({
                                'id': video_id,
                                'title': entry.get('title'),
                                'uploader': uploader,
                                'video_dir': video_dir,
                            })

                    return {
                        'success': True,
                        'type': url_type.value,  # 使用检测到的类型
                        'title': info.get('title'),
                        'uploader': info.get('uploader') or info.get('channel'),
                        'total': len(results),
                        'videos': results,
                        'download_dir': self.download_dir,
                    }
                else:
                    # 单个视频
                    video_id = info.get('id')
                    # 记录已下载的视频 ID
                    if video_id:
                        self._save_downloaded_id(video_id)

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

    def _download_channel_with_dedup(
        self,
        url: str,
        url_type: UrlType,
        max_videos: int,
        sort_order: str,
        progress_callback: Optional[Callable],
        format_preference: str
    ) -> Dict[str, Any]:
        """频道/播放列表去重下载"""
        logger.info(f"开始去重下载，目标数量: {max_videos}")

        # 第一步：获取视频列表（不下载）
        list_opts = {
            'quiet': True,
            'no_warnings': True,
            'extract_flat': True,  # 只获取列表，不解析每个视频
            'ignoreerrors': True,
        }

        # 处理排序
        if sort_order == 'oldest':
            list_opts['playlistreverse'] = True

        try:
            with yt_dlp.YoutubeDL(list_opts) as ydl:
                logger.info("获取频道视频列表...")
                info = ydl.extract_info(url, download=False)

                if not info or 'entries' not in info:
                    return {
                        'success': False,
                        'error': '无法获取视频列表',
                        'url': url,
                    }

                entries = list(info.get('entries', []))
                logger.info(f"频道共有 {len(entries)} 个视频")

        except Exception as e:
            logger.error(f"获取视频列表失败: {e}")
            return {'success': False, 'error': str(e), 'url': url}

        # 第二步：过滤已下载的视频
        downloaded_ids = self._load_downloaded_ids()
        videos_to_download = []

        for entry in entries:
            if not entry:
                continue
            video_id = entry.get('id')
            if video_id and video_id not in downloaded_ids:
                videos_to_download.append(entry)
            if len(videos_to_download) >= max_videos:
                break

        skipped = len(entries) - len(videos_to_download)
        if skipped > 0:
            logger.info(f"跳过 {skipped} 个已下载的视频")

        if not videos_to_download:
            return {
                'success': True,
                'type': url_type.value,
                'title': info.get('title'),
                'uploader': info.get('uploader') or info.get('channel'),
                'total': 0,
                'skipped': skipped,
                'message': '所有视频都已下载过',
                'videos': [],
            }

        logger.info(f"将下载 {len(videos_to_download)} 个新视频")

        # 第三步：逐个下载
        results = []
        for i, entry in enumerate(videos_to_download):
            video_id = entry.get('id')
            video_url = entry.get('url') or f"https://www.youtube.com/watch?v={video_id}"
            logger.info(f"下载 [{i+1}/{len(videos_to_download)}]: {entry.get('title', video_id)}")

            # 下载单个视频
            result = self._download_single_video(
                video_url, progress_callback, format_preference
            )

            if result.get('success'):
                self._save_downloaded_id(video_id)
                results.append({
                    'id': video_id,
                    'title': result.get('title'),
                    'uploader': result.get('uploader'),
                    'video_dir': result.get('video_dir'),
                })

            # 下载间隔
            if i < len(videos_to_download) - 1:
                time.sleep(RATE_LIMIT_CONFIG['download_delay'])

        return {
            'success': True,
            'type': url_type.value,
            'title': info.get('title'),
            'uploader': info.get('uploader') or info.get('channel'),
            'total': len(results),
            'skipped': skipped,
            'videos': results,
            'download_dir': self.download_dir,
        }

    def _download_single_video(
        self,
        url: str,
        progress_callback: Optional[Callable],
        format_preference: str
    ) -> Dict[str, Any]:
        """下载单个视频"""
        opts = self._get_ydl_opts(progress_callback, format_preference, False, "newest")

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                info = ydl.extract_info(url, download=True)

                if not info:
                    return {'success': False, 'error': '下载失败'}

                uploader = sanitize_filename(
                    info.get('uploader') or info.get('channel') or 'Unknown'
                )
                title = sanitize_filename(info.get('title') or 'unknown')
                video_dir = os.path.join(self.download_dir, uploader, title)

                self._ensure_processing_dirs(video_dir)
                self._write_status_file(video_dir, info)

                return {
                    'success': True,
                    'id': info.get('id'),
                    'title': info.get('title'),
                    'uploader': uploader,
                    'video_dir': video_dir,
                }
        except Exception as e:
            logger.error(f"下载单个视频失败: {e}")
            return {'success': False, 'error': str(e)}

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
