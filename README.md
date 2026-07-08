# 蓝牙歌词音箱 (Lyric Speaker)

一个运行在 Linux ARM 开发板上的蓝牙歌词显示应用。开发板作为 A2DP 蓝牙音箱接收手机音频，同时通过 AVRCP 协议读取正在播放的曲目信息，联网查询 LRC 歌词，按播放进度逐行高亮同步显示在全屏浏览器上。

## 工作原理

```
手机播放音乐（任何 App）
    │
    ├── A2DP ──→ 开发板接收音频，通过扬声器/HDMI 播放
    │
    └── AVRCP ──→ 读取歌名、歌手、播放进度
                      │
                      ├── 联网查询 LRC 歌词（网易云音乐 API）
                      │
                      └── 按播放进度逐行高亮显示
                              │
                              └── Chromium Kiosk 全屏渲染
```

与 BLE 方案不同，A2DP + AVRCP 是标准蓝牙音频协议，**任何音乐 App 都可以直接使用**——网易云音乐、QQ 音乐、Spotify、Apple Music 等，无需安装额外插件或使用专用客户端。

## 功能特性

- **A2DP 蓝牙音箱**：开发板作为蓝牙音频接收端，手机连接后直接播放音频
- **AVRCP 歌词同步**：通过 AVRCP 协议读取歌名、歌手、播放进度，按 LRC 时间戳逐行高亮
- **联网歌词查询**：自动从网易云音乐 API 搜索并获取 LRC 歌词，带磁盘缓存（30 天）
- **Chromium Kiosk 全屏**：Web 页面渲染，当前行高亮 + 平滑滚动，支持 Wayland 和 X11
- **自动配对**：蓝牙配对代理（NoInputNoOutput），手机点连接即配对，无需手动确认
- **音效管理**：支持多种预设音效（摇滚、流行、古典等），基于 LADSPA 插件
- **配置热重载**：修改 `config.json` 后自动生效，无需重启服务
- **PipeWire 兼容**：自动检测 PulseAudio 或 PipeWire（树莓派 Bookworm 默认），两种音频系统均可使用

## 系统要求

### 硬件

| 项目 | 要求 |
|------|------|
| 开发板 | Linux ARM（armhf 或 arm64），如树莓派 3/4/5、RK3588 等 |
| 蓝牙 | 支持蓝牙 4.0+ 的适配器（板载或 USB），需支持 A2DP |
| 显示 | HDMI / DSI 显示屏（Chromium Kiosk 需要 GUI 环境） |
| 音频 | 3.5mm / HDMI / USB 扬声器或音频输出 |
| 网络 | 需要联网（查询歌词 API） |

### 软件

- **BlueZ** ≥ 5.50（蓝牙协议栈，含 A2DP + AVRCP 支持）
- **PulseAudio** 或 **PipeWire**（含 pipewire-pulse + wireplumber）
- **Chromium**（浏览器，用于 Kiosk 全屏显示）
- **D-Bus** 系统总线（AVRCP 通过 D-Bus 读取媒体信息）
- **bluez-tools**（提供 bt-agent 自动配对代理）
- **X11 或 Wayland**（显示服务器）

> 树莓派 Bookworm 默认使用 PipeWire + Wayland，完全兼容。安装脚本会自动检测并安装所需依赖。

---

## 安装

### 第一步：准备系统

```bash
# 更新系统
sudo apt-get update && sudo apt-get upgrade -y

# 安装基础依赖（安装脚本也会自动检测并安装缺失的包）
sudo apt-get install -y bluez bluez-tools pulseaudio chromium-browser curl
```

如果是树莓派 Bookworm（默认 PipeWire），安装脚本会自动检测并安装 `pipewire-audio` 和 `wireplumber`。

### 第二步：获取应用

#### 方式 A：下载预编译包（推荐）

从 [Releases](https://github.com/Hjw202/lyric-app/releases) 下载最新版本：

```bash
# ARM64（树莓派 4/5、RK3588 等 64 位系统）
wget https://github.com/Hjw202/lyric-app/releases/latest/download/lyric-app-arm64.tar.gz
tar -xzf lyric-app-arm64.tar.gz
cd lyric-app

# ARM32（树莓派 3 等 32 位系统）
# wget https://github.com/Hjw202/lyric-app/releases/latest/download/lyric-app-armhf.tar.gz
# tar -xzf lyric-app-armhf.tar.gz
# cd lyric-app
```

#### 方式 B：从源码编译

```bash
git clone https://github.com/Hjw202/lyric-app.git
cd lyric-app

python3 -m venv venv
source venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt

# 打包为独立可执行文件
pip install pyinstaller
pyinstaller lyric_app.spec
# 输出：dist/lyric_app
```

### 第三步：运行安装脚本

```bash
sudo ./install.sh
```

安装脚本自动完成以下操作：

| 步骤 | 说明 |
|------|------|
| 安装系统依赖 | bluez、bluez-tools、pulseaudio/pipewire、chromium、curl |
| 复制可执行文件 | → `/opt/lyric-app/lyric_app` |
| 复制配置文件 | → `/etc/lyric-app/config.json` |
| 部署 BlueZ 配置 | `/etc/bluetooth/main.conf`（A2DP sink 设备类型，始终可发现） |
| 部署 PulseAudio 配置 | `/etc/pulse/default.pa`（加载蓝牙音频模块），PipeWire 系统跳过 |
| 部署 bt-agent 服务 | `/etc/systemd/system/lyric-bt-agent.service`（自动配对代理） |
| 部署 Web 服务 | `/etc/systemd/system/lyric-web.service`（主应用服务） |
| 配置蓝牙适配器 | `bluetoothctl power on`、`discoverable on`、`pairable on` |
| 设置运行用户 | 自动检测 sudo 用户，设置 User/UID/HOME 环境变量 |
| 创建用户组 | 将用户加入 `bluetooth`、`pulse-access` 组 |
| 启用用户会话保持 | `loginctl enable-linger`（无头运行 D-Bus 会话） |
| 创建缓存目录 | `/var/cache/lyric-app/lyrics`（歌词缓存） |
| 创建日志目录 | `/var/log/lyric-app/` |
| 启用开机自启 | `systemctl enable lyric-bt-agent lyric-web` |

> 原有 BlueZ 和 PulseAudio 配置会备份为 `.lyric-bak` 文件，卸载时可恢复。

### 第四步：重启并验证

```bash
sudo reboot
```

重启后验证服务状态：

```bash
# 检查服务状态
sudo systemctl status lyric-web
sudo systemctl status lyric-bt-agent

# 检查蓝牙适配器
bluetoothctl show

# 查看日志
journalctl -u lyric-web -f
journalctl -u lyric-bt-agent -f
```

---

## 使用方法

### 连接蓝牙播放音乐

1. 打开手机蓝牙设置
2. 搜索名为 **"Lyric Speaker"** 的设备
3. 点击连接——自动配对，无需输入 PIN 或确认
4. 打开任意音乐 App（网易云、QQ 音乐、Spotify 等）播放音乐
5. 音频从开发板扬声器输出，屏幕全屏显示同步歌词

歌词会随播放进度自动逐行高亮，切歌时自动查询新歌词。

### 修改蓝牙设备名称

编辑配置文件：

```bash
sudo nano /etc/lyric-app/config.json
```

修改 `bluetooth.device_name` 字段。同时编辑 `/etc/bluetooth/main.conf` 中的 `Name` 字段保持一致，然后重启蓝牙服务：

```bash
sudo systemctl restart bluetooth
sudo systemctl restart lyric-web
```

### 修改歌词显示样式

编辑 `/etc/lyric-app/config.json` 中的 `display.default_style`：

```json
{
  "display": {
    "default_style": {
      "font_size": 48,
      "color": [0, 255, 0],
      "bg_color": [0, 0, 0],
      "line_spacing": 10,
      "padding": 40
    }
  }
}
```

修改后自动热重载生效，无需重启服务。

### 浏览器手动访问

如果不使用 Kiosk 全屏模式，也可以在任意浏览器中访问 `http://<开发板IP>:8080` 查看歌词页面。通过 WebSocket 实时同步歌词和播放进度。

---

## 配置文件

配置文件位于 `/etc/lyric-app/config.json`，支持热重载。

<details>
<summary>完整配置项</summary>

```jsonc
{
  // 蓝牙配置
  "bluetooth": {
    "adapter": "/org/bluez/hci0",   // 蓝牙适配器 D-Bus 路径
    "device_name": "LyricSpeaker"    // 蓝牙设备名称
  },

  // 显示样式
  "display": {
    "default_style": {
      "font_size": 48,               // 字体大小 (px)
      "color": [0, 255, 0],          // 当前行文字颜色 (RGB)
      "bg_color": [0, 0, 0],         // 背景颜色 (RGB)
      "line_spacing": 10,            // 行间距 (px)
      "padding": 40                  // 页面内边距 (px)
    }
  },

  // 音效预设
  "audio": {
    "presets": {
      "rock":      { "module": "module-ladspa-sink", "label": "rock" },
      "pop":       { "module": "module-ladspa-sink", "label": "pop" },
      "classical": { "module": "module-ladspa-sink", "label": "classical" },
      "flat":      { "module": null, "label": null }   // 原声无音效
    },
    "default_volume": 70             // 默认音量 (0-100)
  },

  // 歌词查询
  "lyrics": {
    "api_base": "https://music.163.com",  // 歌词 API 地址
    "cache_dir": "/var/cache/lyric-app/lyrics",  // 歌词缓存目录
    "cache_ttl": 2592000,            // 缓存有效期 (秒，30天=2592000)
    "request_timeout": 10            // 请求超时 (秒)
  },

  // Web 服务器
  "web": {
    "host": "127.0.0.1",             // 监听地址
    "port": 8080,                    // 监听端口
    "kiosk": {
      "enabled": true,               // 是否启动时自动打开 Kiosk
      "browser": "chromium-browser", // 浏览器命令
      "flags": ["--kiosk", "--noerrdialogs", "--disable-infobars", "--disable-gpu", "--no-sandbox"]
    }
  },

  // 日志
  "logging": {
    "web_file": "/var/log/lyric-app/lyric-web.log",
    "level": "INFO"
  }
}
```

</details>

---

## 服务管理

系统包含两个 systemd 服务：

| 服务 | 说明 |
|------|------|
| `lyric-bt-agent` | 蓝牙自动配对代理，在 bluetooth 服务之后启动 |
| `lyric-web` | 主应用服务（AVRCP 监听 + Web 服务器 + Chromium Kiosk），在 bt-agent 之后启动 |

```bash
# 启动
sudo systemctl start lyric-web

# 停止
sudo systemctl stop lyric-web

# 重启
sudo systemctl restart lyric-web

# 查看状态
sudo systemctl status lyric-web
sudo systemctl status lyric-bt-agent

# 查看实时日志
journalctl -u lyric-web -f
journalctl -u lyric-bt-agent -f

# 查看最近 50 行
journalctl -u lyric-web -n 50
```

> `lyric-bt-agent` 通常不需要手动管理，开机自动启动。仅在配对异常时可能需要重启。

---

## 系统配置文件

安装脚本会部署以下系统配置文件（均备份原有配置）：

### BlueZ 配置：`/etc/bluetooth/main.conf`

设置设备类型为蓝牙音箱（Class = 0x240438），始终可发现、可配对，开机自动上电适配器。

### PulseAudio 配置：`/etc/pulse/default.pa`

加载 `module-bluetooth-discover` 和 `module-bluetooth-policy` 模块，使 PulseAudio 能处理 A2DP 蓝牙音频连接。PipeWire 系统不需要此文件（wireplumber 自动管理）。

### 蓝牙配对代理：`lyric-bt-agent.service`

运行 `bt-agent --capability=NoInputNoOutput`，自动接受手机的蓝牙配对请求。手机点连接即配对，无需在开发板上手动确认。

---

## 故障排除

### 手机搜不到蓝牙设备

```bash
# 检查蓝牙服务
sudo systemctl status bluetooth

# 检查适配器状态
bluetoothctl show
# PowerState 应为 active，Discoverable 应为 yes

# 手动设置
sudo bluetoothctl power on
sudo bluetoothctl discoverable on
sudo bluetoothctl pairable on

# 检查 bt-agent 是否运行
sudo systemctl status lyric-bt-agent
```

### 手机连接后没有声音

```bash
# 检查 PulseAudio / PipeWire
pactl info        # PulseAudio
wpctl status      # PipeWire

# 检查音频输出设备
pactl list sinks short

# 检查 PULSE_SERVER 路径
# 应为 /run/user/$(id -u)/pulse/native
echo $PULSE_SERVER

# 重启音频服务
# PulseAudio:
pulseaudio --kill && pulseaudio --start
# PipeWire:
systemctl --user restart pipewire pipewire-pulse wireplumber
```

### 歌词不显示

```bash
# 检查 AVRCP 是否读取到曲目信息
journalctl -u lyric-web -f | grep "曲目变更"

# 检查网络连接（歌词 API 需要联网）
curl -s "https://music.163.com" | head -1

# 检查歌词缓存目录
ls /var/cache/lyric-app/lyrics/

# 手动测试歌词查询
curl -s "https://music.163.com/api/search/get?s=晴天&limit=1" | python3 -m json.tool
```

### Chromium 不显示 / 黑屏

```bash
# 检查 Web 服务器是否运行
curl -s http://localhost:8080 | head -1

# 检查显示环境
echo $DISPLAY
echo $WAYLAND_DISPLAY
echo $XDG_RUNTIME_DIR

# 检查 start-kiosk.sh 日志
journalctl -u lyric-web | grep "lyric-kiosk"

# 树莓派 Wayland 问题：
# 确认 start-kiosk.sh 检测到 Wayland
journalctl -u lyric-web | grep "检测到.*会话"

# 手动测试浏览器
DISPLAY=:0 chromium-browser --kiosk http://localhost:8080
```

### D-Bus 权限错误

```bash
# 确认用户在 bluetooth 组
groups $USER

# 如果没有 bluetooth 组，手动添加
sudo usermod -a -G bluetooth,pulse-access $USER

# 确认 enable-linger
loginctl show-user $USER | grep Linger

# 如果 Linger=no
sudo loginctl enable-linger $USER

# 重启后生效
sudo reboot
```

---

## 升级

```bash
# 下载新版本
wget https://github.com/Hjw202/lyric-app/releases/latest/download/lyric-app-arm64.tar.gz
tar -xzf lyric-app-arm64.tar.gz
cd lyric-app

# 运行升级
sudo ./install.sh --upgrade
```

升级会自动备份当前配置文件（带时间戳），保留你的 `config.json` 不变，替换可执行文件和服务文件，自动重启服务。

```bash
# 对比新旧配置差异
diff /etc/lyric-app/config.json /etc/lyric-app/config.json.default
```

---

## 卸载

```bash
sudo ./install.sh --uninstall
```

停止所有服务，删除程序文件、配置文件、缓存和日志。BlueZ 和 PulseAudio 的原始配置备份（`.lyric-bak` 文件）会尝试恢复。

---

## 开发

### 从源码运行

```bash
git clone https://github.com/Hjw202/lyric-app.git
cd lyric-app

python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 直接运行（无参数默认 Web 模式）
python lyric_app.py
```

### 项目结构

```
lyric-app/
├── lyric_app.py              # 主入口（单进程：AVRCP + WebServer + Kiosk）
├── lyric_app.spec            # PyInstaller 打包配置
├── install.sh                # 安装/升级/卸载脚本
├── requirements.txt          # Python 依赖
├── modules/
│   ├── avrcp_controller.py   # AVRCP D-Bus 控制器（读取曲目/进度/状态）
│   ├── lyrics_fetcher.py     # 歌词查询（网易云 API + 缓存）
│   ├── lrc_parser.py         # LRC 格式解析
│   ├── lyric_sync.py         # 歌词同步引擎（二分查找 + 时钟插值）
│   ├── web_server.py         # aiohttp Web 服务器 + WebSocket
│   ├── audio_effects.py      # PulseAudio 音效控制
│   ├── cmd_handler.py        # 浏览器命令处理
│   └── config_manager.py     # 配置管理 + 热重载
├── web/
│   ├── index.html            # 歌词页面
│   ├── app.js                # WebSocket 客户端 + 逐行高亮
│   └── style.css             # 样式（当前行高亮 + 平滑滚动）
├── scripts/
│   ├── start-kiosk.sh        # Chromium Kiosk 启动（Wayland/X11 自动检测）
│   └── bt-agent.sh           # 蓝牙自动配对代理
├── systemd/
│   ├── lyric-web.service     # 主应用服务
│   └── lyric-bt-agent.service# 配对代理服务
├── config/
│   ├── config.json           # 应用配置
│   ├── bluetooth/main.conf   # BlueZ A2DP sink 配置
│   └── pulse/default.pa      # PulseAudio 蓝牙模块配置
└── utils/
    └── logger.py             # 结构化日志
```

### 打包

```bash
pip install pyinstaller
pyinstaller lyric_app.spec
# 输出：dist/lyric_app
```

> 必须使用 `lyric_app.spec` 而非 `--onefile` 命令行参数，否则 spec 中的 hiddenimports 等配置会被忽略。

---

## 许可证

MIT License

## 联系方式

- 问题反馈：[GitHub Issues](https://github.com/Hjw202/lyric-app/issues)
