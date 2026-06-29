#!/bin/bash
# 蓝牙歌词音箱 - 安装脚本
# 用于将应用安装到 Linux 开发板上

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

# 检查是否为 root 用户
if [ "$EUID" -ne 0 ]; then
    echo -e "${RED}请使用 sudo 运行此脚本${NC}"
    exit 1
fi

echo -e "${GREEN}开始安装蓝牙歌词音箱...${NC}"

# 创建目录
echo "创建安装目录..."
mkdir -p "$INSTALL_DIR"
mkdir -p "$CONFIG_DIR"

# 复制可执行文件
echo "复制可执行文件..."
if [ -f "lyric_app" ]; then
    cp lyric_app "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/lyric_app"
else
    echo -e "${YELLOW}警告: 未找到 lyric_app 可执行文件，请先运行打包脚本${NC}"
fi

# 复制配置文件
echo "复制配置文件..."
if [ -f "config/config.json" ]; then
    cp config/config.json "$CONFIG_DIR/"
else
    echo -e "${YELLOW}警告: 未找到 config.json 配置文件${NC}"
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
