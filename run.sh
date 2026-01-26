#!/bin/bash

# Video Downloader - 服务管理脚本
# 在 Debian 服务器上运行

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m'

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }
print_header() { echo -e "${CYAN}$1${NC}"; }

# 检测 Docker Compose 命令
detect_docker_compose() {
    if command -v "docker compose" &> /dev/null; then
        DOCKER_COMPOSE="docker compose"
    elif command -v docker-compose &> /dev/null; then
        DOCKER_COMPOSE="docker-compose"
    else
        print_error "Docker Compose 未安装！"
        exit 1
    fi
}

# 检查系统要求
check_requirements() {
    print_status "检查系统要求..."

    if ! command -v docker &> /dev/null; then
        print_error "Docker 未安装！"
        exit 1
    fi

    detect_docker_compose
    print_success "系统要求检查通过"
}

# 启动服务
start_service() {
    print_header "🚀 启动 Video Downloader"
    check_requirements

    print_status "启动 Docker 容器..."
    $DOCKER_COMPOSE up -d

    print_status "等待服务启动..."
    sleep 5

    # 健康检查
    max_attempts=20
    attempt=1
    while [ $attempt -le $max_attempts ]; do
        if curl -s http://localhost:8081/health > /dev/null 2>&1; then
            print_success "✅ 服务已启动"
            show_status
            return 0
        fi
        echo -n "."
        sleep 2
        ((attempt++))
    done

    print_error "❌ 服务启动超时"
    show_logs_tail
    exit 1
}

# 停止服务
stop_service() {
    print_header "🛑 停止 Video Downloader"
    check_requirements

    print_status "停止容器..."
    $DOCKER_COMPOSE down
    print_success "服务已停止"
}

# 重启服务
restart_service() {
    print_header "🔄 重启 Video Downloader"
    stop_service
    start_service
}

# 构建并重启
build_service() {
    print_header "📦 构建并重启服务"
    check_requirements

    print_status "停止现有服务..."
    $DOCKER_COMPOSE down

    print_status "重新构建镜像..."
    $DOCKER_COMPOSE build

    start_service
    print_success "构建完成！"
}

# 完全重构（无缓存）
rebuild_service() {
    print_header "🔧 完全重构（无缓存）"
    check_requirements

    print_warning "将清除缓存并重新构建..."
    read -p "确认继续? (y/N): " -n 1 -r
    echo

    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        print_status "操作已取消"
        return 0
    fi

    print_status "停止服务..."
    $DOCKER_COMPOSE down

    print_status "清理 Docker 资源..."
    docker system prune -f

    print_status "无缓存重新构建..."
    $DOCKER_COMPOSE build --no-cache

    start_service
    print_success "重构完成！"
}

# 查看日志
show_logs() {
    print_header "📋 服务日志"
    check_requirements
    $DOCKER_COMPOSE logs -f
}

# 查看最近日志
show_logs_tail() {
    print_header "📋 最近日志"
    check_requirements
    $DOCKER_COMPOSE logs --tail=50
}

# 查看状态
show_status() {
    print_header "📊 服务状态"
    check_requirements

    echo ""
    echo "📦 容器状态:"
    $DOCKER_COMPOSE ps

    echo ""
    echo "🌐 服务地址:"
    local ip=$(hostname -I | awk '{print $1}')
    echo "  Web UI:   http://$ip:8081/ui"
    echo "  API文档:  http://$ip:8081/docs"
    echo "  健康检查: http://$ip:8081/health"

    echo ""
    echo "💾 下载目录:"
    if [ -d "./downloads" ]; then
        local count=$(find ./downloads -maxdepth 3 -type d 2>/dev/null | wc -l)
        local size=$(du -sh ./downloads 2>/dev/null | cut -f1 || echo "0")
        echo "  目录: ./downloads"
        echo "  大小: $size"
        echo "  子目录数: $count"
    else
        echo "  目录不存在"
    fi

    echo ""
    echo "📊 健康检查:"
    if curl -s http://localhost:8081/health > /dev/null 2>&1; then
        echo "  ✅ 服务运行正常"
    else
        echo "  ❌ 服务未响应"
    fi
}

# 清理下载文件
clean_downloads() {
    print_header "🧹 清理下载文件"

    if [ ! -d "./downloads" ]; then
        print_warning "下载目录不存在"
        return 0
    fi

    local size=$(du -sh ./downloads 2>/dev/null | cut -f1 || echo "0")
    print_warning "下载目录大小: $size"
    print_warning "这将删除所有下载的视频！"
    read -p "确认删除? (y/N): " -n 1 -r
    echo

    if [[ $REPLY =~ ^[Yy]$ ]]; then
        rm -rf ./downloads/*
        print_success "下载文件已清理"
    else
        print_status "操作已取消"
    fi
}

# 帮助信息
show_help() {
    print_header "📥 Video Downloader - 服务管理脚本"
    echo ""
    echo "用法: ./run.sh [命令]"
    echo ""
    echo "命令:"
    echo "  start       启动服务"
    echo "  stop        停止服务"
    echo "  restart     重启服务"
    echo "  build       构建并重启（使用缓存）"
    echo "  rebuild     完全重构（无缓存）"
    echo "  logs        查看日志（实时）"
    echo "  status      查看状态"
    echo "  clean       清理下载文件"
    echo "  help        显示帮助"
    echo ""
}

# 主函数
main() {
    case "${1:-}" in
        start)
            start_service
            ;;
        stop)
            stop_service
            ;;
        restart)
            restart_service
            ;;
        build|update)
            build_service
            ;;
        rebuild)
            rebuild_service
            ;;
        logs)
            show_logs
            ;;
        status)
            show_status
            ;;
        clean)
            clean_downloads
            ;;
        help|--help|-h|"")
            show_help
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
