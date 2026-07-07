# 蓝牙歌词音箱 (Lyric Speaker)

一个运行在 Linux ARM 开发板上的蓝牙歌词显示应用，通过 BLE 接收手机音乐 App（网易云音乐、QQ 音乐等）的歌词并全屏显示，同时支持音效控制。

## 功能特性

- 🎵 **蓝牙歌词接收**：通过 BLE GATT 接收手机音乐 App 推送的歌词
- 📺 **全屏歌词显示**：Pygame 硬件加速渲染，自动换行、LRU 文本缓存、脏矩形优化
- 🎛️ **远程控制**：通过 BLE 控制通道实时修改歌词样式、切换音效、调节音量
- 🔊 **音效管理**：支持多种预设音效（摇滚、流行、古典等），基于 LADSPA 插件
- 🔄 **进程分离**：BLE 和 UI 分离为两个独立进程，通过 Unix Socket 通信（心跳检测 + 自动重连）
- ⚙️ **配置热重载**：修改 `config.json` 后自动生效，无需重启服务
- 📊 **结构化日志**：JSON 格式日志输出，支持日志轮转（10MB/份，保留 5 份）
- 🚀 **开机自启**：systemd 服务管理，开机自动启动

---

## 系统要求

### 硬件

| 项目 | 要求 |
|------|------|
| 开发板 | Linux ARM（armhf 或 arm64），如树莓派 2/3/4/5、RK3588 等 |
| 蓝牙 | 支持 BLE 4.0+ 的蓝牙适配器（板载或 USB） |
| 显示 | HDMI / DSI 显示屏，或支持 Framebuffer 的屏幕 |
| 音频 | 3.5mm / HDMI / USB 扬声器或音频输出 |

### 软件

- **BlueZ** ≥ 5.50（蓝牙协议栈）
- **PulseAudio**（音频服务，含 LADSPA 插件支持）
- **SDL2**（Pygame 图形依赖）
- **D-Bus** 系统总线

> `bluetooth` 和 `pulse-access` 用户组由安装脚本自动创建并加入当前用户，无需手动配置。

---

## 全新系统安装指南

> 以下步骤适用于全新刷机的 Debian / Ubuntu / Raspberry Pi OS 系统，从头完成所有准备工作。

### 第一步：更新系统 & 安装依赖

```bash
sudo apt-get update && sudo apt-get upgrade -y

sudo apt-get install -y \
    bluez \
    pulseaudio \
    pulseaudio-utils \
    swh-plugins \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    fonts-wqy-microhei \
    git
```

> **说明：**
> - `swh-plugins` 提供 LADSPA 音效插件（摇滚/流行/古典等音效依赖它）
> - `fonts-wqy-microhei` 是中文字体，歌词显示必需（如已安装其他中文字体可跳过）
> - `pulseaudio-utils` 提供 `pactl` 等管理工具

### 第二步：获取应用

#### 方式 A：下载预编译包（推荐）

从 [Releases 页面](https://github.com/Hjw202/lyric-app/releases) 下载最新版本：

```bash
# ARM64（树莓派 4/5、RK3588 等 64 位系统）
wget https://github.com/Hjw202/lyric-app/releases/latest/download/lyric-app-arm64.tar.gz
tar -xzf lyric-app-arm64.tar.gz
cd lyric-app

# ARM32（树莓派 2/3 等 32 位系统）
# wget https://github.com/Hjw202/lyric-app/releases/latest/download/lyric-app-armhf.tar.gz
# tar -xzf lyric-app-armhf.tar.gz
# cd lyric-app
```

#### 方式 B：从源码编译

```bash
# 克隆项目
git clone https://github.com/Hjw202/lyric-app.git
cd lyric-app

# 创建 Python 虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装 Python 依赖
pip install --upgrade pip
pip install -r requirements.txt

# （可选）打包为独立可执行文件
pip install pyinstaller
pyinstaller --onefile --add-data "config/config.json:config" lyric_app.py
# 输出：dist/lyric_app
```

### 第三步：运行安装脚本

```bash
sudo ./install.sh
```

安装脚本会自动完成：

| 步骤 | 说明 |
|------|------|
| ✅ 复制可执行文件 | → `/opt/lyric-app/lyric_app` |
| ✅ 复制配置文件 | → `/etc/lyric-app/config.json` |
| ✅ 安装 systemd 服务 | → `/etc/systemd/system/lyric-ble.service`、`lyric-ui.service` |
| ✅ 自动配置运行用户 | 将服务中的 `User` 设为当前 `sudo` 用户 |
| ✅ 自动创建系统组 | 创建 `bluetooth`、`pulse-access` 组（如不存在）并加入当前用户 |
| ✅ 启用开机自启 | `systemctl enable lyric-ble lyric-ui` |
| ✅ 创建日志目录 | → `/var/log/lyric-app/` |

> **注意：** 安装脚本会自动检测执行 `sudo` 的用户名，并设置为 systemd 服务的运行用户，无需手动修改。同时会自动创建 `bluetooth` 和 `pulse-access` 组并将当前用户加入。

### 第四步：配置显示模式

编辑配置文件，根据你的显示方式选择驱动：

```bash
sudo nano /etc/lyric-app/config.json
```

```jsonc
{
  "display": {
    "driver": "x11",        // "x11"（桌面环境）或 "fbcon"（纯 Framebuffer）
    "fb_device": "/dev/fb0",
    "x11_display": ":0",
    // ...
  }
}
```

| 环境 | driver 值 | 说明 |
|------|-----------|------|
| 有桌面环境（Raspberry Pi OS Desktop 等） | `"x11"` | 使用 X11 窗口系统 |
| 无桌面（Lite 版 / 纯终端） | `"fbcon"` | 直接写入 Framebuffer |

### 第五步：启动服务 & 验证

```bash
# 启动服务
sudo systemctl start lyric-ble
sudo systemctl start lyric-ui

# 检查服务状态
sudo systemctl status lyric-ble
sudo systemctl status lyric-ui

# 查看实时日志
journalctl -u lyric-ble -f
journalctl -u lyric-ui -f
```

验证蓝牙是否正常广播：

```bash
# 在手机上打开蓝牙设置，搜索 "LyricSpeaker" 设备
# 如需修改设备名称，编辑 /etc/lyric-app/config.json 中的 ble.device_name
```

### 第六步：重启（可选）

```bash
sudo reboot
```

重启后服务会自动启动，无需手动操作。

---

## 使用说明

### 连接蓝牙

1. 打开手机蓝牙设置
2. 搜索名为 **"LyricSpeaker"** 的设备（名称可在 `config.json` 中修改 `ble.device_name`）
3. 连接设备

### 推送歌词

使用支持 BLE 歌词推送的音乐 App（网易云音乐、QQ 音乐等），播放音乐时歌词会自动推送到音箱显示。

### 远程控制

通过 BLE 调试工具（如 nRF Connect）或自研手机 App，向**控制特征**写入 JSON 命令：

#### 修改歌词样式
```json
{"cmd": "style", "color": [255, 0, 0], "bg_color": [0, 0, 0], "font_size": 64}
```

#### 切换音效
```json
{"cmd": "effect", "name": "rock"}
```

#### 调节音量
```json
{"cmd": "volume", "level": 80}
```

---

## 配置文件

配置文件位于 `/etc/lyric-app/config.json`（源码开发时为 `config/config.json`）。

**支持热重载** —— 修改后自动生效，无需重启服务。

<details>
<summary>完整配置项说明</summary>

```jsonc
{
  "ble": {
    "lyric_service_uuid": "0000FFE0-0000-1000-8000-00805F9B34FB",  // 歌词服务 UUID
    "lyric_char_uuid": "0000FFE1-0000-1000-8000-00805F9B34FB",     // 歌词特征 UUID
    "control_service_uuid": "12345678-1234-1234-1234-123456789ABC", // 控制服务 UUID
    "control_char_uuid": "12345678-1234-1234-1234-123456789ABD",    // 控制特征 UUID
    "adapter": "/org/bluez/hci0",         // 蓝牙适配器路径
    "device_name": "LyricSpeaker"          // 蓝牙广播名称
  },
  "display": {
    "driver": "x11",                       // 显示驱动 (x11 / fbcon)
    "fb_device": "/dev/fb0",               // Framebuffer 设备（fbcon 模式）
    "x11_display": ":0",                   // X11 显示地址（x11 模式）
    "default_style": {
      "font_size": 48,                     // 字体大小
      "color": [0, 255, 0],               // 文字颜色 (RGB)
      "bg_color": [0, 0, 0],              // 背景颜色 (RGB)
      "font_name": null,                   // 字体路径（null 自动检测）
      "line_spacing": 10,                  // 行间距
      "padding": 40                        // 边距
    }
  },
  "audio": {
    "presets": {                           // 音效预设
      "rock": { "module": "module-ladspa-sink", "label": "rock" },
      "pop": { "module": "module-ladspa-sink", "label": "pop" },
      "classical": { "module": "module-ladspa-sink", "label": "classical" },
      "flat": { "module": null, "label": null }   // 原声（无音效）
    },
    "default_volume": 70                   // 默认音量 (0-100)
  },
  "ipc": {
    "socket_path": "/tmp/lyric.sock"       // Unix Socket 路径
  }
}
```

</details>

---

## 服务管理

```bash
# 启动
sudo systemctl start lyric-ble lyric-ui

# 停止
sudo systemctl stop lyric-ble lyric-ui

# 重启
sudo systemctl restart lyric-ble lyric-ui

# 查看状态
sudo systemctl status lyric-ble
sudo systemctl status lyric-ui

# 开机自启（安装时已默认启用）
sudo systemctl enable lyric-ble lyric-ui
```

## 日志查看

日志采用 JSON 结构化格式，支持日志轮转。

```bash
# systemd 日志（推荐）
journalctl -u lyric-ble -f
journalctl -u lyric-ui -f

# 查看最近 50 行
journalctl -u lyric-ble -n 50

# 应用日志文件
tail -f /tmp/lyric-ble.log
tail -f /tmp/lyric-ui.log
```

---

## 故障排除

### 蓝牙无法连接

```bash
# 1. 检查蓝牙服务
sudo systemctl status bluetooth

# 2. 检查蓝牙适配器
bluetoothctl list

# 3. 检查 BLE 服务日志
journalctl -u lyric-ble -n 50

# 4. 确认用户在 bluetooth 组（安装脚本会自动添加）
groups $USER
```

### 歌词不显示

```bash
# 1. 检查两个服务是否都在运行
sudo systemctl status lyric-ble lyric-ui

# 2. 检查 IPC Socket 是否存在
ls -la /tmp/lyric.sock

# 3. 查看 UI 日志是否有错误
journalctl -u lyric-ui -n 50

# 4. 检查显示驱动配置是否正确
cat /etc/lyric-app/config.json | grep driver
```

### 音效不生效

```bash
# 1. 检查 PulseAudio
pulseaudio --check
pactl info

# 2. 确认 LADSPA 插件已安装
dpkg -l | grep swh-plugins

# 3. 确认用户在 pulse-access 组
groups $USER
```

### 画面不显示（X11 模式）

```bash
# 确认 DISPLAY 环境变量
echo $DISPLAY

# 确认有 X11 会话
ps aux | grep Xorg

# 如果是 SSH 远程，需要设置 DISPLAY
export DISPLAY=:0
```

---

## 升级到新版本

已安装旧版本时，无需卸载，直接升级即可。安装脚本会自动备份你的配置文件并替换可执行文件。

### 升级步骤

#### 1. 下载新版本

```bash
# 下载新版本压缩包（替换为你实际的版本号）
wget https://github.com/Hjw202/lyric-app/releases/latest/download/lyric-app-arm64.tar.gz
tar -xzf lyric-app-arm64.tar.gz
cd lyric-app
```

#### 2. 运行升级命令

```bash
sudo ./install.sh --upgrade
```

升级脚本会自动完成：

| 步骤 | 说明 |
|------|------|
| ✅ 备份当前配置 | → `/etc/lyric-app/config.json.bak.20260707120000`（带时间戳） |
| ✅ 保留你的配置 | 你的 `config.json` 不会被覆盖 |
| ✅ 保存新版本默认配置 | → `/etc/lyric-app/config.json.default`（供参考） |
| ✅ 替换可执行文件 | → `/opt/lyric-app/lyric_app` |
| ✅ 更新 systemd 服务 | 服务文件会更新，自动配置运行用户和 UID |
| ✅ 创建必要系统组 | `bluetooth`、`pulse-access` 组不存在则自动创建，并加入当前用户 |
| ✅ 重载并重启服务 | `systemctl daemon-reload` + 服务自动重启，无需手动操作 |

#### 3. 检查新版本配置变化（可选）

如果新版本新增了配置项，可以对比查看：

```bash
diff /etc/lyric-app/config.json /etc/lyric-app/config.json.default
```

将你需要的新配置项手动合并到 `/etc/lyric-app/config.json` 中，保存后会自动热重载生效。

#### 4. 验证

```bash
# 检查服务状态
sudo systemctl status lyric-ble lyric-ui

# 查看日志确认新版本正常运行
journalctl -u lyric-ble -n 20
journalctl -u lyric-ui -n 20
```

> **不会丢失的内容：** 你的配置文件、日志文件、systemd 服务状态。
>
> **会被替换的内容：** 可执行文件、systemd 服务文件。

---

## 卸载

```bash
sudo ./install.sh --uninstall
```

这会停止所有服务、删除程序文件、配置文件和日志。如需保留配置，手动备份 `/etc/lyric-app/config.json`。

---

## 开发

### 从源码运行

```bash
git clone https://github.com/Hjw202/lyric-app.git
cd lyric-app
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# 终端 1：BLE 服务
python lyric_app.py ble

# 终端 2：UI 服务
python lyric_app.py ui
```

### 打包

```bash
pip install pyinstaller
pyinstaller --onefile --add-data "config/config.json:config" lyric_app.py
# 输出：dist/lyric_app
```

### CI/CD

推送 tag 自动触发 GitHub Actions 构建：

```bash
git tag v1.0.0
git push origin v1.0.0
```

构建产物：
- `lyric_app_arm64` — ARM64 版本
- `lyric_app_armhf` — ARM32 版本

---

## 许可证

MIT License

## 联系方式

- 问题反馈：[GitHub Issues](https://github.com/Hjw202/lyric-app/issues)
