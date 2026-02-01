"""
Video Downloader - FastAPI 应用
基于 yt-dlp 的视频下载服务
"""
import os
import uuid
import asyncio
from datetime import datetime
from typing import Dict, Optional, Any
from contextlib import asynccontextmanager

# 版本信息 - 每次更新代码时修改这里
APP_VERSION = "1.1.0"
BUILD_TIME = "2026-02-01 12:00"

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles

from models import (
    DownloadRequest, BatchDownloadRequest, DownloadResponse,
    TaskStatus, DownloadTask, TaskListResponse, SortOrder
)
from downloader import VideoDownloader, detect_url_type, UrlType
from cos_uploader import (
    upload_video_folder, get_cos_client, list_videos,
    delete_folder, delete_file, get_file_url
)

# 配置
DOWNLOAD_DIR = os.getenv("DOWNLOAD_DIR", "./downloads")
HOST = os.getenv("HOST", "0.0.0.0")
PORT = int(os.getenv("PORT", "8081"))

# 全局任务存储 (生产环境应使用 Redis)
tasks: Dict[str, DownloadTask] = {}

# 下载器实例
downloader = VideoDownloader(DOWNLOAD_DIR)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """应用生命周期"""
    os.makedirs(DOWNLOAD_DIR, exist_ok=True)
    print(f"📁 下载目录: {os.path.abspath(DOWNLOAD_DIR)}")
    print(f"🚀 Video Downloader 启动在 http://{HOST}:{PORT}")
    print(f"🌐 Web UI: http://localhost:{PORT}/ui")
    yield
    print("👋 Video Downloader 关闭")


app = FastAPI(
    title="Video Downloader",
    description="基于 yt-dlp 的视频下载服务",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 静态文件服务 - 下载目录
os.makedirs(DOWNLOAD_DIR, exist_ok=True)
app.mount("/files", StaticFiles(directory=DOWNLOAD_DIR), name="files")

# 静态文件服务 - 前端 UI
STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")
if os.path.exists(STATIC_DIR):
    app.mount("/ui", StaticFiles(directory=STATIC_DIR, html=True), name="static")


def create_progress_callback(task_id: str):
    """创建进度回调"""
    def callback(d):
        if task_id in tasks:
            if d['status'] == 'downloading':
                total = d.get('total_bytes') or d.get('total_bytes_estimate') or 0
                downloaded = d.get('downloaded_bytes') or 0
                # 确保是数字类型
                try:
                    total = float(total) if total else 0
                    downloaded = float(downloaded) if downloaded else 0
                except (ValueError, TypeError):
                    total = 0
                    downloaded = 0
                if total > 0:
                    progress = (downloaded / total) * 100
                    # 只有视频文件才更新进度（排除字幕、缩略图等小文件）
                    if total > 1024 * 1024:  # 大于 1MB 才认为是视频
                        tasks[task_id].progress = min(progress, 99)
                tasks[task_id].status = TaskStatus.DOWNLOADING
            elif d['status'] == 'finished':
                filename = d.get('filename', '')
                if filename and filename.endswith(('.mp4', '.webm', '.mkv')):
                    tasks[task_id].filename = filename
    return callback


async def download_video_task(
    task_id: str,
    url: str,
    format_pref: str,
    download_playlist: bool = False,
    max_videos: Optional[int] = None,
    sort_order: str = "newest"
):
    """后台下载任务"""
    try:
        tasks[task_id].status = TaskStatus.DOWNLOADING

        loop = asyncio.get_event_loop()
        result = await loop.run_in_executor(
            None,
            lambda: downloader.download(
                url,
                progress_callback=create_progress_callback(task_id),
                format_preference=format_pref,
                download_playlist=download_playlist,
                max_videos=max_videos,
                sort_order=sort_order
            )
        )

        if result.get('success'):
            tasks[task_id].status = TaskStatus.COMPLETED
            tasks[task_id].title = result.get('title')
            tasks[task_id].filename = result.get('filename')
            tasks[task_id].type = result.get('type', 'video')
            tasks[task_id].completed_at = datetime.now()

            # 播放列表额外信息
            if result.get('type') == 'playlist':
                tasks[task_id].video_count = result.get('total', 0)

            # 警告信息（如字幕下载失败）
            if result.get('warning'):
                tasks[task_id].warning = result.get('warning')

            # 自动上传到 COS
            video_dir = result.get('video_dir')
            if video_dir and get_cos_client():
                uploader = result.get('uploader', 'Unknown')
                title = result.get('title', 'unknown')
                try:
                    cos_result = upload_video_folder(video_dir, uploader, title)
                    if cos_result.get('success'):
                        tasks[task_id].cos_uploaded = True
                except Exception as e:
                    tasks[task_id].warning = f"COS上传失败: {e}"
        else:
            tasks[task_id].status = TaskStatus.FAILED
            tasks[task_id].error = result.get('error')

    except Exception as e:
        tasks[task_id].status = TaskStatus.FAILED
        tasks[task_id].error = str(e)


# ==================== API 端点 ====================

@app.get("/")
async def root():
    """首页"""
    return {
        "name": "Video Downloader",
        "version": APP_VERSION,
        "build_time": BUILD_TIME,
        "engine": "yt-dlp",
        "download_dir": os.path.abspath(DOWNLOAD_DIR),
        "ui": "/ui",
        "endpoints": {
            "info": "/api/info?url=VIDEO_URL",
            "download": "POST /api/download",
            "tasks": "/api/tasks",
            "task": "/api/tasks/{task_id}",
            "version": "/api/version",
        }
    }


@app.get("/api/version")
async def get_version():
    """获取版本信息 - 用于确认代码是否更新"""
    return {
        "version": APP_VERSION,
        "build_time": BUILD_TIME,
        "server_time": datetime.now().isoformat()
    }


@app.get("/health")
async def health():
    """健康检查"""
    return {"status": "ok"}


@app.get("/api/cos/status")
async def cos_status():
    """检查 COS 配置状态"""
    client = get_cos_client()
    return {
        "configured": client is not None,
        "bucket": os.getenv('COS_BUCKET', ''),
        "region": os.getenv('COS_REGION', '')
    }


@app.get("/api/cos/videos")
async def list_cos_videos(prefix: str = '', marker: str = '', max_keys: int = 100):
    """列出 COS 中的视频"""
    result = list_videos(prefix, marker, max_keys)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error'))
    return result


@app.delete("/api/cos/folder")
async def delete_cos_folder(prefix: str):
    """删除 COS 文件夹"""
    if not prefix:
        raise HTTPException(status_code=400, detail="prefix 不能为空")
    result = delete_folder(prefix)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error'))
    return result


@app.delete("/api/cos/file")
async def delete_cos_file(key: str):
    """删除 COS 单个文件"""
    if not key:
        raise HTTPException(status_code=400, detail="key 不能为空")
    result = delete_file(key)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error'))
    return result


@app.get("/api/cos/url")
async def get_cos_url(key: str, expires: int = 3600):
    """获取文件预签名 URL"""
    result = get_file_url(key, expires)
    if not result.get('success'):
        raise HTTPException(status_code=500, detail=result.get('error'))
    return result


@app.post("/api/cos/upload/{task_id}")
async def upload_to_cos(task_id: str):
    """上传已下载的视频到 COS"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")

    task = tasks[task_id]
    if task.status != TaskStatus.COMPLETED:
        raise HTTPException(status_code=400, detail="任务未完成")

    # 查找视频目录
    for root, dirs, files in os.walk(DOWNLOAD_DIR):
        for d in dirs:
            if task.title and task.title[:30] in d:
                video_dir = os.path.join(root, d)
                uploader = os.path.basename(root)
                result = upload_video_folder(video_dir, uploader, d)
                return result

    raise HTTPException(status_code=404, detail="视频目录不存在")


@app.get("/api/info")
async def get_video_info(url: str):
    """获取视频/播放列表信息"""
    try:
        loop = asyncio.get_event_loop()
        info = await loop.run_in_executor(
            None,
            lambda: downloader.get_video_info(url)
        )
        return info
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))


@app.post("/api/download", response_model=DownloadResponse)
async def create_download(request: DownloadRequest, background_tasks: BackgroundTasks):
    """创建下载任务（支持单个视频、播放列表、频道）"""
    task_id = str(uuid.uuid4())[:8]

    # 检测 URL 类型
    url_type = detect_url_type(request.url)

    task = DownloadTask(
        id=task_id,
        url=request.url,
        status=TaskStatus.PENDING,
        type=url_type.value,  # 使用检测到的类型：video/channel/playlist
        created_at=datetime.now()
    )
    tasks[task_id] = task

    background_tasks.add_task(
        download_video_task,
        task_id,
        request.url,
        request.format,
        request.download_playlist,
        request.max_videos,
        request.sort_order.value
    )

    type_msg = {
        'video': '',
        'channel': '（频道模式）',
        'playlist': '（播放列表模式）'
    }

    return DownloadResponse(
        task_id=task_id,
        status=TaskStatus.PENDING,
        message="下载任务已创建" + type_msg.get(url_type.value, '')
    )


@app.post("/api/download/batch")
async def create_batch_download(request: BatchDownloadRequest, background_tasks: BackgroundTasks):
    """批量下载"""
    task_ids = []

    for url in request.urls:
        task_id = str(uuid.uuid4())[:8]
        task = DownloadTask(
            id=task_id,
            url=url,
            status=TaskStatus.PENDING,
            created_at=datetime.now()
        )
        tasks[task_id] = task
        task_ids.append(task_id)

        background_tasks.add_task(
            download_video_task,
            task_id,
            url,
            request.format,
            False,
            None
        )

    return {
        "task_ids": task_ids,
        "total": len(task_ids),
        "message": f"已创建 {len(task_ids)} 个下载任务"
    }


@app.get("/api/tasks", response_model=TaskListResponse)
async def list_tasks(
    status: Optional[TaskStatus] = None,
    limit: int = 50,
    offset: int = 0
):
    """获取任务列表"""
    task_list = list(tasks.values())

    if status:
        task_list = [t for t in task_list if t.status == status]

    task_list.sort(key=lambda t: t.created_at, reverse=True)

    return TaskListResponse(
        total=len(task_list),
        tasks=task_list[offset:offset + limit]
    )


@app.get("/api/tasks/{task_id}", response_model=DownloadTask)
async def get_task(task_id: str):
    """获取任务详情"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    return tasks[task_id]


@app.delete("/api/tasks/{task_id}")
async def delete_task(task_id: str):
    """删除任务"""
    if task_id not in tasks:
        raise HTTPException(status_code=404, detail="任务不存在")
    del tasks[task_id]
    return {"message": "任务已删除"}


@app.delete("/api/tasks")
async def clear_completed_tasks():
    """清除已完成的任务"""
    to_delete = [
        tid for tid, task in tasks.items()
        if task.status in [TaskStatus.COMPLETED, TaskStatus.FAILED]
    ]
    for tid in to_delete:
        del tasks[tid]
    return {"message": f"已清除 {len(to_delete)} 个任务"}


# ==================== 启动 ====================

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host=HOST, port=PORT)
