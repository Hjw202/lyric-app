#!/bin/bash
# bt-agent: 蓝牙自动配对代理
# 功能: 自动接受手机的蓝牙配对请求（音箱模式，无需手动确认）
# 能力: NoInputNoOutput (Just Works pairing)
#
# 部署到: /opt/lyric-app/scripts/bt-agent.sh

set -e

# 查找 bt-agent 命令
AGENT=""
for cmd in bt-agent /usr/lib/bluez/test/simple-agent; do
    if command -v "$cmd" &>/dev/null || [ -x "$cmd" ]; then
        AGENT="$cmd"
        break
    fi
done

if [ -z "$AGENT" ]; then
    echo "[bt-agent] 错误: 未找到 bt-agent，请安装 bluez-tools" >&2
    exit 1
fi

echo "[bt-agent] 启动蓝牙配对代理: $AGENT (NoInputNoOutput)"

# NoInputNoOutput: 无需用户交互，自动接受配对
# 适合音箱类设备：手机点连接即可配对
exec "$AGENT" --capability=NoInputNoOutput
