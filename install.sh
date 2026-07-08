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
CACHE_DIR="/var/cache/lyric-app/lyrics"
LOG_DIR="/var/log/lyric-app"

# 参数解析
MODE="install"
while [ $# -gt 0 ]; do
    case "$1" in
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
            echo -e "${RED}未知参数: $1${NC}"
            echo "使用 --help 查看帮助"
            exit 1
            ;;
    esac
    shift
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
    systemctl stop lyric-web.service 2>/dev/null || true
    systemctl stop lyric-bt-agent.service 2>/dev/null || true

    echo "禁用开机自启..."
    systemctl disable lyric-web.service 2>/dev/null || true
    systemctl disable lyric-bt-agent.service 2>/dev/null || true

    echo "删除服务文件..."
    rm -f "$SERVICE_DIR/lyric-web.service" "$SERVICE_DIR/lyric-bt-agent.service"
    systemctl daemon-reload

    echo "删除程序文件..."
    rm -rf "$INSTALL_DIR"

    echo "删除配置文件..."
    rm -rf "$CONFIG_DIR"

    echo "删除缓存和日志目录..."
    rm -rf "$CACHE_DIR" "$LOG_DIR"

    echo -e "${GREEN}卸载完成！${NC}"
    echo "注意: /etc/bluetooth/main.conf 和 /etc/pulse/default.pa 的备份文件保留在 .bak 文件中"
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

# 安装系统依赖（仅全新安装时）
if [ "$MODE" = "install" ]; then
    echo "检查系统依赖..."
    DEPS=""
    command -v btmon &>/dev/null || DEPS="$DEPS bluez"
    command -v pactl &>/dev/null || DEPS="$DEPS pulseaudio"
    command -v chromium-browser &>/dev/null || command -v chromium &>/dev/null || DEPS="$DEPS chromium-browser"
    command -v curl &>/dev/null || DEPS="$DEPS curl"
    command -v bt-agent &>/dev/null || DEPS="$DEPS bluez-tools"

    # 检测 PipeWire（Pi Bookworm 默认）
    if [ -x /usr/bin/pipewire ] || [ -x /usr/bin/pipewire-pulse ]; then
        echo -e "${YELLOW}检测到 PipeWire 音频系统${NC}"
        command -v pipewire-pulse &>/dev/null || DEPS="$DEPS pipewire-audio"
        command -v wpctl &>/dev/null || DEPS="$DEPS wireplumber"
    else
        echo -e "${YELLOW}检测到 PulseAudio 音频系统${NC}"
    fi

    if [ -n "$DEPS" ]; then
        echo -e "${YELLOW}安装系统依赖: $DEPS${NC}"
        apt-get update -qq
        apt-get install -y --no-install-recommends $DEPS
    else
        echo "系统依赖已满足"
    fi
fi

# 创建目录
echo "创建安装目录..."
mkdir -p "$INSTALL_DIR" "$CONFIG_DIR" "$CACHE_DIR" "$LOG_DIR"

# 复制可执行文件
echo "复制可执行文件..."
if [ -f "lyric_app" ]; then
    cp lyric_app "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/lyric_app"
elif [ -f "dist/lyric_app" ]; then
    cp dist/lyric_app "$INSTALL_DIR/"
    chmod +x "$INSTALL_DIR/lyric_app"
elif [ -f "lyric_app_arm64" ]; then
    cp lyric_app_arm64 "$INSTALL_DIR/lyric_app"
    chmod +x "$INSTALL_DIR/lyric_app"
elif [ -f "lyric_app_armhf" ]; then
    cp lyric_app_armhf "$INSTALL_DIR/lyric_app"
    chmod +x "$INSTALL_DIR/lyric_app"
else
    echo -e "${RED}错误: 未找到 lyric_app 可执行文件，请先运行打包脚本或下载预编译包${NC}"
    exit 1
fi

# 复制配置文件（升级模式下保留已有配置）
if [ "$MODE" = "upgrade" ] && [ -f "$CONFIG_DIR/config.json" ]; then
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
        echo -e "${YELLOW}config/ 未找到，内联创建默认配置...${NC}"
        cat > "$CONFIG_DIR/config.json" << 'CONFIG_EOF'
{
  "bluetooth": {
    "adapter": "/org/bluez/hci0",
    "device_name": "LyricSpeaker"
  },
  "display": {
    "default_style": {
      "font_size": 48,
      "color": [0, 255, 0],
      "bg_color": [0, 0, 0],
      "line_spacing": 10,
      "padding": 40,
      "char_interval": 200
    }
  },
  "audio": {
    "presets": {
      "rock": { "module": "module-ladspa-sink", "label": "rock" },
      "pop": { "module": "module-ladspa-sink", "label": "pop" },
      "classical": { "module": "module-ladspa-sink", "label": "classical" },
      "flat": { "module": null, "label": null }
    },
    "default_volume": 70
  },
  "lyrics": {
    "api_base": "https://music.163.com",
    "cache_dir": "/var/cache/lyric-app/lyrics",
    "cache_ttl": 2592000,
    "request_timeout": 10
  },
  "web": {
    "host": "127.0.0.1",
    "port": 8080,
    "kiosk": {
      "enabled": true,
      "browser": "chromium-browser",
      "flags": ["--kiosk", "--noerrdialogs", "--disable-infobars", "--disable-gpu", "--no-sandbox"]
    }
  },
  "logging": {
    "web_file": "/var/log/lyric-app/lyric-web.log",
    "level": "INFO"
  }
}
CONFIG_EOF
        echo "已内联创建默认配置: $CONFIG_DIR/config.json"
    fi
fi

# 复制脚本文件
echo "复制脚本文件..."
mkdir -p "$INSTALL_DIR/scripts"
if [ -d "scripts" ]; then
    cp scripts/* "$INSTALL_DIR/scripts/" 2>/dev/null || true
    chmod +x "$INSTALL_DIR/scripts/"*.sh 2>/dev/null || true
fi

# 如果 scripts/ 目录不存在（如 PyInstaller 打包发布），内联创建脚本
if [ ! -f "$INSTALL_DIR/scripts/start-kiosk.sh" ]; then
    echo "scripts/ 目录未找到，内联创建启动脚本..."
    cat > "$INSTALL_DIR/scripts/start-kiosk.sh" << 'KIOSK_EOF'
#!/bin/bash
# chromium kiosk 启动脚本（自动检测 Wayland / X11）
set -e
BROWSER="${BROWSER:-chromium-browser}"
URL="${1:-http://localhost:8080}"
if ! command -v "$BROWSER" &>/dev/null; then
    if command -v chromium &>/dev/null; then BROWSER="chromium"
    elif command -v chromium-browser &>/dev/null; then BROWSER="chromium-browser"
    else echo "[lyric-kiosk] 错误: 未找到 chromium 浏览器" >&2; exit 1; fi
fi
SESSION_TYPE="x11"
if [ -n "$WAYLAND_DISPLAY" ] && [ -e "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/$WAYLAND_DISPLAY" ]; then
    SESSION_TYPE="wayland"
elif [ -z "$DISPLAY" ]; then
    echo "[lyric-kiosk] 警告: 未检测到显示会话" >&2
fi
for i in $(seq 1 30); do
    curl -s "$URL" > /dev/null 2>&1 && break
    [ "$i" -eq 30 ] && echo "[lyric-kiosk] 警告: Web 服务器未就绪" >&2
    sleep 1
done
COMMON=(--kiosk --noerrdialogs --disable-infobars --start-fullscreen --hide-cursor --disable-translate --disable-features=TranslateUI --no-sandbox)
if [ "$SESSION_TYPE" = "wayland" ]; then
    RENDER=(--ozone-platform=wayland --enable-features=UseOzonePlatform --disable-gpu-compositing)
else
    RENDER=(--disable-gpu)
fi
setsid "$BROWSER" "${COMMON[@]}" "${RENDER[@]}" "$URL" < /dev/null > /dev/null 2>&1 &
echo "[lyric-kiosk] 浏览器已在后台启动 (PID: $!)"
KIOSK_EOF
    chmod +x "$INSTALL_DIR/scripts/start-kiosk.sh"
fi

if [ ! -f "$INSTALL_DIR/scripts/bt-agent.sh" ]; then
    cat > "$INSTALL_DIR/scripts/bt-agent.sh" << 'AGENT_EOF'
#!/bin/bash
# 蓝牙自动配对代理（NoInputNoOutput）
set -e
AGENT=""
for cmd in bt-agent /usr/lib/bluez/test/simple-agent; do
    if command -v "$cmd" &>/dev/null || [ -x "$cmd" ]; then AGENT="$cmd"; break; fi
done
if [ -z "$AGENT" ]; then
    echo "[bt-agent] 错误: 未找到 bt-agent，请安装 bluez-tools" >&2
    exit 1
fi
exec "$AGENT" --capability=NoInputNoOutput
AGENT_EOF
    chmod +x "$INSTALL_DIR/scripts/bt-agent.sh"
fi

# 验证脚本存在
for script in start-kiosk.sh bt-agent.sh; do
    if [ ! -f "$INSTALL_DIR/scripts/$script" ]; then
        echo -e "${RED}错误: 脚本 $script 创建失败${NC}" >&2
        exit 1
    fi
done
echo "脚本文件已就绪: $INSTALL_DIR/scripts/"

# 安装 systemd 服务
echo "安装 systemd 服务..."
if [ -f "systemd/lyric-web.service" ]; then
    cp systemd/lyric-web.service "$SERVICE_DIR/"
fi
if [ -f "systemd/lyric-bt-agent.service" ]; then
    cp systemd/lyric-bt-agent.service "$SERVICE_DIR/"
fi

# 如果 systemd 服务文件不存在（PyInstaller 发布包），内联创建
if [ ! -f "$SERVICE_DIR/lyric-web.service" ]; then
    echo "systemd/ 目录未找到，内联创建服务文件..."
    cat > "$SERVICE_DIR/lyric-web.service" << 'WEB_SVC_EOF'
[Unit]
Description=Lyric Speaker (A2DP Sink + AVRCP + WebServer + Chromium Kiosk)
After=bluetooth.service lyric-bt-agent.service sound.target
Requires=bluetooth.service
Wants=lyric-bt-agent.service sound.target

[Service]
Type=simple
User=__USER__
Group=bluetooth
SupplementaryGroup=pulse-access
ExecStart=/opt/lyric-app/lyric_app
ExecStartPost=/opt/lyric-app/scripts/start-kiosk.sh
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lyric-web
Environment=PULSE_SERVER=unix:/run/user/__UID__/pulse/native
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/__UID__/bus
Environment=XDG_RUNTIME_DIR=/run/user/__UID__
Environment=HOME=__HOME__
Environment=DISPLAY=:0
Environment=WAYLAND_DISPLAY=wayland-0

[Install]
WantedBy=graphical.target
WEB_SVC_EOF
fi

if [ ! -f "$SERVICE_DIR/lyric-bt-agent.service" ]; then
    cat > "$SERVICE_DIR/lyric-bt-agent.service" << 'BT_SVC_EOF'
[Unit]
Description=Bluetooth Auto-Pairing Agent (Lyric Speaker)
After=bluetooth.service
Requires=bluetooth.service
BindsTo=bluetooth.service

[Service]
Type=simple
User=__USER__
Group=bluetooth
ExecStartPre=/bin/sleep 1
ExecStart=/opt/lyric-app/scripts/bt-agent.sh
Restart=always
RestartSec=3
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lyric-bt-agent
Environment=DBUS_SYSTEM_BUS_ADDRESS=unix:path=/run/dbus/system_bus_socket
Environment=XDG_RUNTIME_DIR=/run/user/__UID__
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/__UID__/bus

[Install]
WantedBy=multi-user.target
BT_SVC_EOF
fi

# 自动替换服务文件中的用户名、UID 和 HOME
REAL_USER="${SUDO_USER:-$USER}"
REAL_UID=$(id -u "$REAL_USER")
REAL_HOME=$(eval echo ~"$REAL_USER")
echo "设置服务运行用户: $REAL_USER (uid=$REAL_UID, home=$REAL_HOME)"
for svcfile in "$SERVICE_DIR/lyric-web.service" "$SERVICE_DIR/lyric-bt-agent.service"; do
    if [ -f "$svcfile" ]; then
        sed -i "s/__USER__/$REAL_USER/g" "$svcfile"
        sed -i "s/__UID__/$REAL_UID/g" "$svcfile"
        sed -i "s|__HOME__|$REAL_HOME|g" "$svcfile"
    fi
done

# 确保必要的组存在，并将用户加入
for GRP in bluetooth pulse-access; do
    if ! getent group "$GRP" > /dev/null 2>&1; then
        echo "创建组: $GRP"
        groupadd "$GRP"
    fi
    if ! id -nG "$REAL_USER" | grep -qw "$GRP"; then
        echo "将用户 $REAL_USER 加入组 $GRP"
        usermod -a -G "$GRP" "$REAL_USER"
    fi
done

# 启用用户会话保持（systemd 系统服务需要 D-Bus session bus）
if command -v loginctl &>/dev/null; then
    loginctl enable-linger "$REAL_USER" 2>/dev/null || true
    echo "已启用用户会话保持: $REAL_USER"
fi

# ====================
# BlueZ A2DP sink 配置
# ====================
echo "配置蓝牙 A2DP sink..."
BT_CONF="/etc/bluetooth/main.conf"
if [ -f "config/bluetooth/main.conf" ]; then
    # 备份原有配置（仅首次安装时）
    if [ "$MODE" = "install" ] && [ -f "$BT_CONF" ] && [ ! -f "$BT_CONF.lyric-bak" ]; then
        cp "$BT_CONF" "$BT_CONF.lyric-bak"
        echo "已备份原有蓝牙配置: $BT_CONF.lyric-bak"
    fi
    cp config/bluetooth/main.conf "$BT_CONF"
    echo "已部署蓝牙配置: $BT_CONF"
elif [ ! -f "$BT_CONF" ] || ! grep -q "Lyric Speaker" "$BT_CONF" 2>/dev/null; then
    # 源文件不存在且目标未配置，内联创建
    echo "config/bluetooth/ 未找到，内联创建蓝牙配置..."
    if [ "$MODE" = "install" ] && [ -f "$BT_CONF" ] && [ ! -f "$BT_CONF.lyric-bak" ]; then
        cp "$BT_CONF" "$BT_CONF.lyric-bak"
    fi
    cat > "$BT_CONF" << 'BT_CONF_EOF'
[General]
Name = Lyric Speaker
Class = 0x240438
DiscoverableTimeout = 0
PairableTimeout = 0
FastConnectable = true
Experimental = true

[Policy]
AutoEnable = true
BT_CONF_EOF
    echo "已内联创建蓝牙配置: $BT_CONF"
fi

# 确保蓝牙适配器上电并可发现
if command -v bluetoothctl &>/dev/null; then
    echo "配置蓝牙适配器..."
    bluetoothctl power on 2>/dev/null || true
    bluetoothctl discoverable on 2>/dev/null || true
    bluetoothctl pairable on 2>/dev/null || true
    echo "蓝牙适配器已上电、可发现、可配对"
fi

# 重启蓝牙服务以加载新配置
systemctl restart bluetooth 2>/dev/null || true
echo "蓝牙服务已重启"

# ====================
# PulseAudio / PipeWire 配置
# ====================
echo "配置音频系统..."
if [ -x /usr/bin/pipewire ] || [ -x /usr/bin/pipewire-pulse ]; then
    # PipeWire: 不需要额外配置，pipewire-pulse + wireplumber 自动处理蓝牙音频
    echo "PipeWire 已安装，蓝牙音频由 wireplumber 自动管理"
    # 确保 pipewire-pulse 服务在用户会话中运行
    systemctl --user enable pipewire-pulse 2>/dev/null || true
    systemctl --user enable wireplumber 2>/dev/null || true
else
    # PulseAudio: 部署带蓝牙模块的配置
    PA_CONF="/etc/pulse/default.pa"
    if [ -f "config/pulse/default.pa" ]; then
        if [ "$MODE" = "install" ] && [ -f "$PA_CONF" ] && [ ! -f "$PA_CONF.lyric-bak" ]; then
            cp "$PA_CONF" "$PA_CONF.lyric-bak"
            echo "已备份原有 PulseAudio 配置: $PA_CONF.lyric-bak"
        fi
        cp config/pulse/default.pa "$PA_CONF"
        echo "已部署 PulseAudio 配置: $PA_CONF"
    elif ! grep -q "module-bluetooth-discover" "$PA_CONF" 2>/dev/null; then
        # 源文件不存在且目标未配置蓝牙模块，内联创建
        echo "config/pulse/ 未找到，内联创建 PulseAudio 配置..."
        if [ "$MODE" = "install" ] && [ -f "$PA_CONF" ] && [ ! -f "$PA_CONF.lyric-bak" ]; then
            cp "$PA_CONF" "$PA_CONF.lyric-bak"
        fi
        cat > "$PA_CONF" << 'PA_CONF_EOF'
#!/usr/bin/pulseaudio -n
load-module module-card-restore
load-module module-device-restore
load-module module-default-restore
load-module module-stream-restore
load-module module-augment-properties
load-module module-switch-on-port-available
.ifexists module-udev-detect.so
load-module module-udev-detect tsched=1
.else
load-module module-alsa-sink device=hw:0
.endif
.ifexists module-bluetooth-discover.so
load-module module-bluetooth-discover
.endif
.ifexists module-bluetooth-policy.so
load-module module-bluetooth-policy auto_switch=2
.endif
load-module module-native-protocol-unix
load-module module-always-sink
load-module module-suspend-on-idle
load-module module-rescue-streams
PA_CONF_EOF
        echo "已内联创建 PulseAudio 配置: $PA_CONF"
    fi
fi

# 设置缓存目录权限
chown -R "$REAL_USER:$REAL_USER" "$CACHE_DIR" "$LOG_DIR"

# 重新加载 systemd
echo "重新加载 systemd..."
systemctl daemon-reload

# 启用服务
echo "启用服务..."
systemctl enable lyric-bt-agent.service
systemctl enable lyric-web.service

# 设置权限
echo "设置权限..."
chmod 755 "$INSTALL_DIR"
if [ -f "$CONFIG_DIR/config.json" ]; then
    chmod 644 "$CONFIG_DIR/config.json"
fi

# 升级模式：自动重启服务
if [ "$MODE" = "upgrade" ]; then
    echo ""
    echo "重启服务..."
    systemctl restart lyric-bt-agent.service 2>/dev/null || true
    systemctl restart lyric-web.service
    echo -e "${GREEN}升级完成！服务已自动重启。${NC}"
    echo ""
    echo "如需查看新版本默认配置:"
    echo "  diff $CONFIG_DIR/config.json $CONFIG_DIR/config.json.default"
    echo ""
    echo "日志:"
    echo "  journalctl -u lyric-web -f"
    echo "  journalctl -u lyric-bt-agent -f"
else
    echo -e "${GREEN}安装完成！${NC}"
    echo ""
    echo "使用方法："
    echo "  启动服务:  sudo systemctl start lyric-web"
    echo "  查看日志:  journalctl -u lyric-web -f"
    echo "  配对代理:  journalctl -u lyric-bt-agent -f"
    echo ""
    echo "配置文件:  $CONFIG_DIR/config.json"
    echo "歌词缓存:  $CACHE_DIR"
    echo ""
    echo "蓝牙配对:  手机搜索 'Lyric Speaker' 并连接，自动配对"
    echo ""
    echo -e "${YELLOW}建议重启系统以确保用户组、linger 和音频服务生效: sudo reboot${NC}"
fi
