"""
数据模型
"""
from pydantic import BaseModel
from typing import Optional, List, Any, Dict
from enum import Enum
from datetime import datetime


class TaskStatus(str, Enum):
    PENDING = "pending"
    DOWNLOADING = "downloading"
    COMPLETED = "completed"
    FAILED = "failed"


class DownloadRequest(BaseModel):
    """下载请求"""
    url: str
    format: str = "best"  # best, 1080p, 720p, audio
    download_subtitles: bool = True
    download_thumbnail: bool = True
    download_playlist: bool = False  # 是否下载整个播放列表/频道
    max_videos: Optional[int] = None  # 最多下载几个视频


class BatchDownloadRequest(BaseModel):
    """批量下载请求"""
    urls: List[str]
    format: str = "best"
    download_subtitles: bool = True


class VideoInfoBase(BaseModel):
    """视频/播放列表信息基类"""
    id: Optional[str] = None
    title: Optional[str] = None
    description: Optional[str] = None
    uploader: Optional[str] = None
    type: str = "video"  # video 或 playlist


class VideoInfo(VideoInfoBase):
    """单个视频信息"""
    duration: Optional[int] = None
    upload_date: Optional[str] = None
    view_count: Optional[int] = None
    thumbnail: Optional[str] = None
    subtitles: List[str] = []
    automatic_captions: List[str] = []
    formats: Optional[int] = None


class PlaylistInfo(VideoInfoBase):
    """播放列表信息"""
    video_count: Optional[int] = None
    videos: List[Dict[str, Any]] = []


class DownloadTask(BaseModel):
    """下载任务"""
    id: str
    url: str
    status: TaskStatus = TaskStatus.PENDING
    progress: float = 0.0
    title: Optional[str] = None
    filename: Optional[str] = None
    error: Optional[str] = None
    warning: Optional[str] = None  # 部分成功的警告
    type: str = "video"  # video 或 playlist
    video_count: Optional[int] = None  # 播放列表视频数
    created_at: datetime = datetime.now()
    completed_at: Optional[datetime] = None


class DownloadResponse(BaseModel):
    """下载响应"""
    task_id: str
    status: TaskStatus
    message: str


class TaskListResponse(BaseModel):
    """任务列表响应"""
    total: int
    tasks: List[DownloadTask]
