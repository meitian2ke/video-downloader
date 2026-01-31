# Claude Code 项目记忆文件

## 对话规则
- **语言**: 使用中文对话
- **Context 管理**: 当对话压缩接近 5% 时，更新本文件

---

## 项目目标
YouTube 视频下载器，支持频道批量下载、字幕提取、自动上传到腾讯云 COS

## 技术栈
- **Backend**: Python / FastAPI
- **Frontend**: 静态 HTML
- **存储**: 腾讯云 COS
- **缓存**: Redis
- **下载引擎**: yt-dlp
- **部署**: Docker + GitHub Actions CI/CD
- **代理**: Clash（服务器访问 YouTube）

---

## 部署流程 (GitHub Actions)

**自动部署**: 推送到 main 分支后自动触发
```bash
git add . && git commit -m "feat: xxx" && git push origin main
```

**CI/CD 配置**: `.github/workflows/deploy.yml`
1. SSH 连接腾讯云服务器
2. `git pull origin main` 拉取最新代码
3. `./run.sh build` 执行构建和部署

**构建方案**: 服务器端 Docker build
```
git pull → docker-compose down → docker-compose build → docker-compose up
```

**服务器部署目录**: 由 `secrets.DEPLOY_PATH` 配置

---

## 关键文件
- `app.py` - FastAPI 主应用
- `downloader.py` - yt-dlp 下载器封装
- `models.py` - Pydantic 数据模型
- `cos_uploader.py` - 腾讯云 COS 上传
- `cache.py` - Redis 缓存
- `static/index.html` - 前端页面

---

## 已完成功能
- [x] 单视频下载
- [x] 频道/播放列表批量下载
- [x] 排序选项（最新/最热门/最早）
- [x] 下载数量限制
- [x] 自动上传到 COS
- [x] Redis 缓存 COS 文件列表
- [x] 视频管理页面

## TODO
- [ ] 字幕翻译
- [ ] TTS 配音
- [ ] 视频合成

---

## 踩过的坑
- 服务器在国内，访问 YouTube 需要 Clash 代理
- COS 文件列表 API 慢，必须用 Redis 缓存
- YouTube 热门排序需要 URL 参数 `?view=0&sort=p`
