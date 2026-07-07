#!/bin/bash
# 蓝牙歌词音箱 - 安装脚本
#
# 用法：
#   sudo ./install.sh               # 全新安装
#   sudo ./install.sh --upgrade     # 升级（保留配置文件，重启服务）
#   sudo ./install.sh --uninstall   # 完全卸载
#   sudo ./install.sh --help        # 显示帮助

set -e

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# 安装目录
INSTALL_DIR="/opt/lyric-app"
CONFIG_DIR="/etc/lyric-app"
SERVICE_DIR="/etc/systemd/system"

# 参数解析
MODE="install"
for arg in "$@"; do
    case "$arg" in
        --upgrade)   MODE="upgrade" ;;
        --uninstall) MODE="uninstall" ;;
        --help|-h)
            echo "用法："
            echo "  sudo ./install.sh               全新安装"
            echo "  sudo ./install.sh --upgrade     升级（保留配置文件，重启服务）"
            echo "  sudo ./install.sh --uninstall   完全卸载"
            exit 0
            ;;
        *)
            echo -e "${RED}未知参数: $arg${NC}"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
done

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 sudo 运行此脚本${NC}"
    exit 1
fi

# ====================
# 卸载模式
# ====================
if [ "$MODE" = "uninstall" ]; then
    echo -e "${YELLOW}正在卸载蓝牙歌词音箱...${NC}"

    echo "停止服务..."
    systemctl stop lyric-ble.service 2>/dev/null || true
    systemctl stop lyric-ui.service 2>/dev/null || true

    echo "禁用开机自启..."
    systemctl disable lyric-ble.service 2>/dev/null || true
    systemctl disable lyric-ui.service 2>/dev/null || true

    echo "删除服务文件..."
    rm -f "$SERVICE_DIR/lyric-ble.service"
    rm -f "$SERVICE_DIR/lyric-ui.service"
    systemctl daemon-reload

    echo "删除程序文件..."
    rm -rf "$INSTALL_DIR"

    echo "删除配置文件..."
    rm -rf "$CONFIG_DIR"

    echo "删除日志目录..."
    rm -rf /var/log/lyric-app

    echo "清理 IPC Socket..."
    rm -f /tmp/lyric.sock

    echo -e "${GREEN}卸载完成！${NC}"
    exit 0
fi

# ====================
# 安装 / 升级模式
# ====================

if [ "$MODE" = "upgrade" ]; then
    echo -e "${GREEN}开始升级蓝牙歌词音箱...${NC}"
else
    echo -e "${GREEN}开始安装蓝牙歌词音箱...${NC}"
fi

# 创建目录
echo "创建安装目录..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"

# 复制可执行文件
echo "复制可执行文件..."
if [ -f "lyric_app" ]; then
    cp lyric_app "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/lyric_app"
elif [ -f "dist/lyric_app" ]; then
    cp dist/lyric_app "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/lyric_app"
else
    echo -e "${RED}错误: 未找到 lyric_app 可执行文件，请先运行打包脚本或下载预编译包${NC}"
    exit 1
fi

# 复制配置文件（升级模式下保留已有配置）
if [ "$MODE" = "upgrade" ] && [ -f "$CONFIG_DIR/config.json" ]; then
    # 升级模式：备份旧配置，复制新配置为 .default 供参考
    BACKUP="$CONFIG_DIR/config.json.bak.$(date +%Y%m%d%H%M%S)"
    cp "$CONFIG_DIR/config.json" "$BACKUP"
    echo -e "${YELLOW}已备份当前配置: $BACKUP${NC}"
    echo "配置文件保持不变，新版本默认配置已保存为 config.json.default"
    if [ -f "config/config.json" ]; then
        cp config/config.json "$CONFIG_DIR/config.json.default"
    fi
else
    echo "复制配置文件..."
    if [ -f "config/config.json" ]; then
        cp config/config.json "$CONFIG_DIR/"
    else
        echo -e "${YELLOW}警告: 未找到 config.json 配置文件${NC}"
    fi
fi

# 安装 systemd 服务
echo "安装 systemd 服务..."
if [ -f "systemd/lyric-ble.service" ]; then
    cp systemd/lyric-ble.service "$SERVICE_DIR/"
fi

if [ -f "systemd/lyric-ui.service" ]; then
    cp systemd/lyric-ui.service "$SERVICE_DIR/"
fi

# 重新加载 systemd
echo "重新加载 systemd..."
systemctl daemon-reload

# 启用服务
echo "启用服务..."
systemctl enable lyric-ble.service
systemctl enable lyric-ui.service

# 创建日志目录
echo "创建日志目录..."
mkdir -p /var/log/lyric-app

# 设置权限
echo "设置权限..."
chmod 755 "$INSTALL_DIR"
chmod 644 "$CONFIG_DIR/config.json"

# 升级模式：自动重启服务
if [ "$MODE" = "upgrade" ]; then
    echo ""
    echo "重启服务..."
    systemctl restart lyric-ble.service
    systemctl restart lyric-ui.service
    echo -e "${GREEN}升级完成！服务已自动重启。${NC}"
    echo ""
    echo "如需查看新版本默认配置:"
    echo "  diff $CONFIG_DIR/config.json $CONFIG_DIR/config.json.default"
    echo ""
    echo "日志:"
    echo "  journalctl -u lyric-ble -f"
    echo "  journalctl -u lyric-ui -f"
else
    echo -e "${GREEN}安装完成！${NC}"
    echo ""
    echo "使用方法："
    echo "  启动 BLE 服务:  sudo systemctl start lyric-ble"
    echo "  启动 UI 服务:   sudo systemctl start lyric-ui"
    echo "  查看日志:       journalctl -u lyric-ble -f"
    echo "                  journalctl -u lyric-ui -f"
    echo ""
    echo "配置文件位置: $CONFIG_DIR/config.json"
    echo ""
    echo -e "${YELLOW}注意: 请确保当前用户在 bluetooth 和 pulse-access 组中${NC}"
    echo "  sudo usermod -a -G bluetooth \$USER"
    echo "  sudo usermod -a -G pulse-access \$USER"
    echo ""
    echo -e "${YELLOW}建议重启系统: sudo reboot${NC}"
fi
