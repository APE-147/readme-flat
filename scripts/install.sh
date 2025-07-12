#!/bin/bash
# README Sync Manager 安装脚本
# 支持 macOS, Linux, Windows (WSL)

set -euo pipefail

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 应用配置
APP_NAME="readme-sync-manager"
DATA_DIR="$HOME/Developer/Code/Script_data/readme-sync"
INSTALL_DIR="$HOME/.local/bin"
REPO_URL="https://github.com/yourusername/readme-sync-manager.git"

# 打印带颜色的消息
print_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

print_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# 检测操作系统
detect_os() {
    if [[ "$OSTYPE" == "darwin"* ]]; then
        OS="macos"
    elif [[ "$OSTYPE" == "linux-gnu"* ]]; then
        OS="linux"
    elif [[ "$OSTYPE" == "msys" || "$OSTYPE" == "cygwin" ]]; then
        OS="windows"
    else
        print_error "不支持的操作系统: $OSTYPE"
        exit 1
    fi
    print_info "检测到操作系统: $OS"
}

# 检查依赖
check_dependencies() {
    print_info "检查系统依赖..."
    
    # 检查 Python
    if ! command -v python3 &> /dev/null; then
        print_error "Python 3 未安装。请先安装 Python 3.8+"
        exit 1
    fi
    
    local python_version=$(python3 -c 'import sys; print(".".join(map(str, sys.version_info[:2])))')
    print_info "Python 版本: $python_version"
    
    # 检查 pip
    if ! command -v pip3 &> /dev/null; then
        print_error "pip3 未安装。请先安装 pip"
        exit 1
    fi
    
    # 检查 git
    if ! command -v git &> /dev/null; then
        print_error "Git 未安装。请先安装 Git"
        exit 1
    fi
    
    print_success "所有依赖检查通过"
}

# 创建数据目录
create_data_directory() {
    print_info "创建数据目录: $DATA_DIR"
    mkdir -p "$DATA_DIR"
    print_success "数据目录创建完成"
}

# 安装应用
install_app() {
    print_info "开始安装 $APP_NAME..."
    
    # 创建临时目录
    local temp_dir=$(mktemp -d)
    cd "$temp_dir"
    
    # 克隆仓库
    print_info "下载源代码..."
    git clone "$REPO_URL" .
    
    # 安装依赖并安装应用
    print_info "安装 Python 依赖..."
    pip3 install --user -e .
    
    # 确保 ~/.local/bin 在 PATH 中
    ensure_local_bin_in_path
    
    # 清理临时目录
    cd /
    rm -rf "$temp_dir"
    
    print_success "$APP_NAME 安装完成"
}

# 确保 ~/.local/bin 在 PATH 中
ensure_local_bin_in_path() {
    local shell_config=""
    
    if [[ -n "${BASH_VERSION:-}" ]]; then
        shell_config="$HOME/.bashrc"
    elif [[ -n "${ZSH_VERSION:-}" ]]; then
        shell_config="$HOME/.zshrc"
    else
        shell_config="$HOME/.profile"
    fi
    
    if [[ ! ":$PATH:" == *":$HOME/.local/bin:"* ]]; then
        print_info "添加 ~/.local/bin 到 PATH"
        echo 'export PATH="$HOME/.local/bin:$PATH"' >> "$shell_config"
        print_warning "请重新加载 shell 配置: source $shell_config"
    fi
}

# 初始化配置
init_config() {
    print_info "初始化应用配置..."
    
    # 检查是否已有配置
    if [[ -f "$DATA_DIR/config.yaml" ]]; then
        print_warning "配置文件已存在，跳过初始化"
        return
    fi
    
    # 运行初始化
    if command -v readme-sync &> /dev/null; then
        print_info "运行配置初始化..."
        readme-sync init
    else
        print_warning "命令未找到，请手动运行: readme-sync init"
    fi
}

# 安装系统服务（可选）
install_system_service() {
    print_info "是否要安装系统开机自启动服务？"
    read -p "输入 y/n: " -n 1 -r
    echo
    
    if [[ $REPLY =~ ^[Yy]$ ]]; then
        if command -v readme-sync &> /dev/null; then
            print_info "安装开机自启动..."
            readme-sync autostart
        else
            print_warning "请先确保 readme-sync 命令可用，然后运行: readme-sync autostart"
        fi
    fi
}

# 显示安装后信息
show_post_install_info() {
    print_success "🎉 安装完成！"
    echo
    print_info "📋 接下来的步骤:"
    echo "  1. 重新加载 shell 配置或重启终端"
    echo "  2. 运行 'readme-sync init' 初始化配置"
    echo "  3. 运行 'readme-sync add-source <项目目录>' 添加源文件夹"
    echo "  4. 运行 'readme-sync set-target <目标目录>' 设置目标文件夹"
    echo "  5. 运行 'readme-sync sync' 执行首次同步"
    echo "  6. 运行 'readme-sync daemon start' 启动后台守护进程"
    echo
    print_info "📚 更多帮助:"
    echo "  - 运行 'readme-sync --help' 查看所有命令"
    echo "  - 数据目录: $DATA_DIR"
    echo "  - 配置文件: $DATA_DIR/config.yaml"
    echo
    print_info "🚀 开始使用吧！"
}

# 主函数
main() {
    echo "🚀 README Sync Manager 安装脚本"
    echo "================================="
    echo
    
    detect_os
    check_dependencies
    create_data_directory
    install_app
    init_config
    install_system_service
    show_post_install_info
}

# 如果直接运行脚本
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi