FROM python:3.11-slim

WORKDIR /app

# 安装 ffmpeg (yt-dlp 依赖)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

# 安装 Python 依赖
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# 复制应用代码
COPY . .

# 创建下载目录
RUN mkdir -p /app/downloads

# 暴露端口
EXPOSE 8081

# 环境变量
ENV DOWNLOAD_DIR=/app/downloads
ENV HOST=0.0.0.0
ENV PORT=8081

# 启动命令
CMD ["python", "app.py"]
