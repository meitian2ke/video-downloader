# Video Downloader

基于 yt-dlp 的视频下载服务，为 video-learning-manager 提供视频来源。

## 项目位置

```
/home/eric/Public/video-downloader/   # 独立项目，与 video-learning-manager 平行
```

## 技术栈

| 组件 | 技术 |
|-----|------|
| 下载引擎 | yt-dlp |
| 后端框架 | FastAPI |
| 运行时 | Python 3.11 |
| 部署 | Docker |

## 快速开始

### 本地开发

```bash
cd /home/eric/Public/video-downloader

# 创建虚拟环境
python -m venv .venv
source .venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 启动服务
python app.py
```

服务将在 http://localhost:8081 启动

### Docker 部署

```bash
# 构建并启动
docker-compose up -d

# 查看日志
docker-compose logs -f

# 停止
docker-compose down
```

## API 文档

启动后访问: http://localhost:8081/docs

### 主要端点

| 端点 | 方法 | 说明 |
|-----|------|-----|
| `/` | GET | 服务信息 |
| `/health` | GET | 健康检查 |
| `/api/info?url=` | GET | 获取视频信息 |
| `/api/download` | POST | 创建下载任务 |
| `/api/download/batch` | POST | 批量下载 |
| `/api/tasks` | GET | 任务列表 |
| `/api/tasks/{id}` | GET | 任务详情 |

### 使用示例

```bash
# 获取视频信息
curl "http://localhost:8081/api/info?url=https://www.youtube.com/watch?v=VIDEO_ID"

# 下载视频
curl -X POST "http://localhost:8081/api/download" \
  -H "Content-Type: application/json" \
  -d '{"url": "https://www.youtube.com/watch?v=VIDEO_ID"}'

# 批量下载
curl -X POST "http://localhost:8081/api/download/batch" \
  -H "Content-Type: application/json" \
  -d '{"urls": ["URL1", "URL2"]}'
```

## 功能清单

- [x] YouTube 视频下载
- [x] 获取视频信息
- [x] 下载进度追踪
- [x] 自动下载字幕
- [x] 批量下载
- [x] Docker 部署
- [ ] 抖音视频支持 (Phase 2)
- [ ] 微信视频支持 (Phase 2)
- [ ] 腾讯云 COS 集成 (生产环境)

## 目录结构

```
video-downloader/
├── app.py              # FastAPI 主应用
├── downloader.py       # yt-dlp 封装
├── models.py           # 数据模型
├── requirements.txt    # Python 依赖
├── Dockerfile          # Docker 构建
├── docker-compose.yml  # Docker 编排
└── downloads/          # 下载目录 (开发环境)
```

## 环境变量

| 变量 | 默认值 | 说明 |
|-----|-------|------|
| `DOWNLOAD_DIR` | `./downloads` | 下载目录 |
| `HOST` | `0.0.0.0` | 监听地址 |
| `PORT` | `8081` | 监听端口 |

---

**决策**: DEC-0001
**开发**: Claude Code
**审查**: Codex
