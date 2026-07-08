#!/bin/bash
# chromium kiosk 启动脚本
# 用法: ./start-kiosk.sh [URL]
# 环境变量: BROWSER=chromium-browser
# 自动检测 Wayland / X11 会话

set -e

BROWSER="${BROWSER:-chromium-browser}"
URL="${1:-http://localhost:8080}"

# 自动检测可用的浏览器
if ! command -v "$BROWSER" &>/dev/null; then
    if command -v chromium &>/dev/null; then
        BROWSER="chromium"
    elif command -v chromium-browser &>/dev/null; then
        BROWSER="chromium-browser"
    else
        echo "[lyric-kiosk] 错误: 未找到 chromium 浏览器" >&2
        exit 1
    fi
fi

# 检测显示服务器类型：Wayland 或 X11
SESSION_TYPE="x11"
if [ -n "$WAYLAND_DISPLAY" ] && [ -e "${XDG_RUNTIME_DIR:-/run/user/$(id -u)}/$WAYLAND_DISPLAY" ]; then
    SESSION_TYPE="wayland"
    echo "[lyric-kiosk] 检测到 Wayland 会话"
elif [ -n "$DISPLAY" ]; then
    SESSION_TYPE="x11"
    echo "[lyric-kiosk] 检测到 X11 会话"
else
    echo "[lyric-kiosk] 警告: 未检测到显示会话，尝试 X11 回退" >&2
fi

# 等待 Web 服务器就绪（最多 30 秒）
for i in $(seq 1 30); do
    if curl -s "$URL" > /dev/null 2>&1; then
        echo "[lyric-kiosk] Web 服务器已就绪"
        break
    fi
    if [ "$i" -eq 30 ]; then
        echo "[lyric-kiosk] 警告: Web 服务器未就绪，仍尝试启动浏览器" >&2
    fi
    sleep 1
done

# 公共参数（Wayland 和 X11 都需要）
COMMON_FLAGS=(
    --kiosk
    --noerrdialogs
    --disable-infobars
    --start-fullscreen
    --hide-cursor
    --disable-translate
    --disable-features=TranslateUI
    --no-sandbox
)

# 按显示服务器类型设置渲染参数
if [ "$SESSION_TYPE" = "wayland" ]; then
    # Wayland: 使用 ozone 平台后端，保留 GPU 加速
    RENDER_FLAGS=(
        --ozone-platform=wayland
        --enable-features=UseOzonePlatform
        --disable-gpu-compositing
    )
else
    # X11: 禁用 GPU 避免某些驱动问题
    RENDER_FLAGS=(
        --disable-gpu
    )
fi

echo "[lyric-kiosk] 启动浏览器: $BROWSER $URL (${SESSION_TYPE})"

# 后台启动浏览器，不阻塞 systemd ExecStartPost
# setsid 创建新会话脱离终端，但保留在同一 cgroup 内（服务停止时 systemd 会一并清理）
setsid "$BROWSER" \
    "${COMMON_FLAGS[@]}" \
    "${RENDER_FLAGS[@]}" \
    "$URL" < /dev/null > /dev/null 2>&1 &
echo "[lyric-kiosk] 浏览器已在后台启动 (PID: $!)"
