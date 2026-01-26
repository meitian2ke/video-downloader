#!/bin/bash

# Video Downloader - 一键部署脚本
# 使用 rsync 增量同步到 Debian 服务器

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

# 配置
SERVER_USER="eric"
SERVER_HOST="192.168.0.106"
DEPLOY_PATH="/home/eric/deploy/video-downloader"
SSH_TARGET="${SERVER_USER}@${SERVER_HOST}"

print_status() { echo -e "${BLUE}[INFO]${NC} $1"; }
print_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
print_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
print_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# 检查 SSH 连接
check_ssh() {
    print_status "检查 SSH 连接..."
    if ! ssh -o ConnectTimeout=5 "${SSH_TARGET}" "echo ok" > /dev/null 2>&1; then
        print_error "无法连接到服务器 ${SERVER_HOST}"
        print_warning "请确保:"
        print_warning "1. 服务器已启动"
        print_warning "2. SSH 密钥已配置"
        exit 1
    fi
    print_success "SSH 连接正常"
}

# 同步代码
sync_code() {
    print_status "同步代码到服务器..."

    # 确保远程目录存在
    ssh "${SSH_TARGET}" "mkdir -p ${DEPLOY_PATH}"

    # 使用 rsync 增量同步
    rsync -avz --delete \
        --exclude='.git' \
        --exclude='.venv' \
        --exclude='__pycache__' \
        --exclude='*.pyc' \
        --exclude='.DS_Store' \
        --exclude='downloads/*' \
        --exclude='*.log' \
        -e ssh \
        ./ "${SSH_TARGET}:${DEPLOY_PATH}/"

    print_success "代码同步完成"
}

# 重启服务
restart_service() {
    print_status "重启服务..."
    ssh "${SSH_TARGET}" "cd ${DEPLOY_PATH} && chmod +x run.sh && ./run.sh restart"
    print_success "服务重启完成"
}

# 快速部署（不重启）
quick_sync() {
    print_status "快速同步（不重启服务）..."
    check_ssh
    sync_code
    print_success "快速同步完成"
}

# 完整部署
full_deploy() {
    print_status "开始完整部署..."
    check_ssh
    sync_code
    restart_service

    echo ""
    print_success "部署完成！"
    echo ""
    echo "访问地址: http://${SERVER_HOST}:8081/ui"
    echo "API文档:  http://${SERVER_HOST}:8081/docs"
}

# 查看远程状态
show_status() {
    print_status "查看远程服务状态..."
    ssh "${SSH_TARGET}" "cd ${DEPLOY_PATH} && ./run.sh status"
}

# 查看远程日志
show_logs() {
    print_status "查看远程服务日志..."
    ssh "${SSH_TARGET}" "cd ${DEPLOY_PATH} && ./run.sh logs"
}

# 帮助信息
show_help() {
    echo "Video Downloader 部署脚本"
    echo ""
    echo "用法: ./deploy.sh [命令]"
    echo ""
    echo "命令:"
    echo "  (无参数)    完整部署（同步 + 重启）"
    echo "  sync        仅同步代码，不重启"
    echo "  restart     仅重启远程服务"
    echo "  status      查看远程服务状态"
    echo "  logs        查看远程服务日志"
    echo "  help        显示此帮助信息"
    echo ""
}

# 主函数
main() {
    case "${1:-}" in
        sync)
            quick_sync
            ;;
        restart)
            check_ssh
            restart_service
            ;;
        status)
            check_ssh
            show_status
            ;;
        logs)
            check_ssh
            show_logs
            ;;
        help|--help|-h)
            show_help
            ;;
        "")
            full_deploy
            ;;
        *)
            print_error "未知命令: $1"
            show_help
            exit 1
            ;;
    esac
}

main "$@"
