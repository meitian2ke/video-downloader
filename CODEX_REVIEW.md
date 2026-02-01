# Codex 审阅（给 Claude Code 的同步说明）

## 范围与上下文
- 仓库: video-downloader（FastAPI + yt-dlp，静态前端，COS/Redis 集成）
- 阅读文件: README.md, app.py, downloader.py, models.py, cos_uploader.py, cache.py, Dockerfile, docker-compose.yml, static/*
- 目标: 给出架构速览、已知风险与修复建议，便于 Claude Code 直接落地改进

## 架构速览
- API: FastAPI (`app.py`)，后台下载任务用 `BackgroundTasks` + 同步 yt-dlp（线程池执行）
- 下载: `downloader.py` 封装 yt-dlp，输出到 `./downloads/{uploader}/{title}/`，去重记录 `.downloaded_videos.json`
- 前端: `static/` 挂载为 `/ui`，下载目录直接挂 `/files`
- 云存储: `cos_uploader.py` 直连腾讯云 COS，Redis 缓存文件列表（`cache.py`）
- 部署: Docker + docker-compose（host 网络，暴露 8081），环境变量注入代理/COS/下载路径

## 主要风险（按严重度）
- 高: 无鉴权 + CORS 全开 → 任意人可滥用下载接口
- 高: `/api/cos/*` 全开放 → 任何人可列举/删除/上传/获取预签名 URL，等同于完全控制 COS 桶
- 高: `/files` 直接暴露下载目录 → 视频、字幕、`.downloaded_videos.json` 等元数据泄露
- 高: SSRF/内网探测 → yt-dlp 接收任意 URL，可请求内网/元数据服务
- 中: 任务存储仅内存字典，无并发/数量/大小上限 → 可被 DoS，重启即丢任务
- 中: Redis 默认无鉴权，若对外或多租户可被任意读写/flush
- 低: host 网络 + root 运行 + 默认代理 env，增加暴露面与误配置风险

## 立即行动清单（优先给 Claude 实施）
1) 接口保护: 为下载与 COS 管理接口加 token/JWT；收紧 CORS（限定域名）
2) URL 防护: 对 `url` 做域名白名单（仅允许 YouTube 域），并设置请求超时/重试/并发与数量限制
3) 存储暴露: `/files` 仅内网或加鉴权；隐藏敏感文件（如去重记录、info.json）
4) COS 最小权限: 删除/上传接口加鉴权和前缀约束；增加操作审计
5) 资源控制: 设置批量/单请求的最大任务数、文件大小、并发下载数；后台任务持久化到 Redis/队列
6) 基础安全: Redis 配置密码和网络隔离；容器避免 host 网络，使用非 root 运行

## 中期改进
- 任务系统: 引入队列（Celery/RQ）+ 持久存储，支持任务恢复与并发限流
- 配置管理: 将代理/COS/Redis/安全配置集中成配置文件或环境开关，便于部署差异化
- 审计与监控: 记录关键操作日志（下载、COS 删除/上传）并暴露健康/指标
- 下载策略: 对格式/大小做白名单或上限，避免超大文件；为热门/排序参数做输入校验

## 给 Claude Code 的执行指引
- 先实现“立即行动清单”的 1–3 步（鉴权、CORS、URL 白名单、限制 `/files`），再处理 COS 权限与并发限制
- 所有改动保持默认安全（不开启即最小暴露），通过环境变量控制开关
- 改动完成后补充 README/前端提示，确保用户知道需要 token/白名单

