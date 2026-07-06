# 蓝牙歌词音箱 (Lyric Speaker)

一个运行在 Linux ARM 开发板上的蓝牙歌词显示应用，支持通过蓝牙接收歌词并全屏显示，同时提供音效控制功能。

## 功能特性

- 🎵 **蓝牙歌词接收**：通过 BLE 接收手机音乐 App 推送的歌词
- 📺 **全屏歌词显示**：使用 Pygame 渲染，支持自动换行、文本缓存和脏矩形优化
- 🎛️ **远程控制**：通过 BLE 控制通道实时修改歌词样式、切换音效、调节音量
- 🔊 **音效管理**：支持多种预设音效（摇滚、流行、古典等）
- 🔄 **进程分离**：BLE 和 UI 分离为两个独立进程，通过 Unix Socket 通信（含心跳检测和自动重连）
- ⚙️ **配置热重载**：修改 `config.json` 后自动生效，无需重启服务
- 📊 **结构化日志**：JSON 格式日志输出，支持日志轮转和性能指标记录
- 🚀 **开机自启**：支持 systemd 服务，开机自动启动

## 系统要求

### 硬件要求

- Linux ARM 开发板（armhf 或 arm64）
- 蓝牙适配器（支持 BLE）
- 显示屏（HDMI/DSI 或 Framebuffer）
- 扬声器

### 软件要求

- Linux 系统已安装：
  - BlueZ >= 5.50（蓝牙协议栈）
  - PulseAudio（音频服务）
  - SDL2（Pygame 依赖）
  - D-Bus 系统总线

- 用户权限：
  - 需要在 `bluetooth` 组中
  - 需要在 `pulse-access` 组中

## 安装步骤

### 方式一：使用预编译包（推荐）

#### 1. 下载安装包

访问 [Releases 页面](https://github.com/Hjw202/lyric-app/releases) 下载最新版本：

- `lyric-app-v1.0.1-arm64.tar.gz` - 适用于 **64位系统**（树莓派 4/5、RK3588 等）
- `lyric-app-v1.0.1-armhf.tar.gz` - 适用于 **32位系统**（树莓派 2/3 等）

#### 2. 传输到开发板

```bash
# 方法一：使用 scp
scp lyric-app-v1.0.1-arm64.tar.gz pi@your-board:~/

# 方法二：使用 U 盘拷贝
# 方法三：在开发板上直接下载
wget https://github.com/Hjw202/lyric-app/releases/latest/download/lyric-app-v1.0.1-arm64.tar.gz
```

#### 3. 解压安装包

```bash
cd ~
tar -xzf lyric-app-v1.0.1-arm64.tar.gz
cd lyric-app
```

#### 4. 运行安装脚本

```bash
sudo ./install.sh
```

安装脚本会自动完成：
- ✅ 安装可执行文件到 `/opt/lyric-app/`
- ✅ 安装配置文件到 `/etc/lyric-app/`
- ✅ 安装 systemd 服务文件
- ✅ 启用开机自启

#### 5. 重启系统

```bash
sudo reboot
```

### 方式二：从源码编译安装

#### 1. 安装系统依赖

**Debian/Ubuntu/Raspberry Pi OS：**
```bash
sudo apt-get update
sudo apt-get install -y \
    bluez \
    pulseaudio \
    libsdl2-2.0-0 \
    libsdl2-image-2.0-0 \
    libsdl2-mixer-2.0-0 \
    libsdl2-ttf-2.0-0 \
    python3-pip \
    python3-venv \
    git
```

**Arch Linux：**
```bash
sudo pacman -S bluez-utils pulseaudio sdl2 python-pip git
```

#### 2. 配置用户权限

```bash
# 将当前用户添加到蓝牙和音频组
sudo usermod -a -G bluetooth $USER
sudo usermod -a -G pulse-access $USER

# 登录后生效（或重启）
newgrp bluetooth
newgrp pulse-access
```

#### 3. 克隆项目

```bash
git clone https://github.com/Hjw202/lyric-app.git
cd lyric-app
```

#### 4. 创建虚拟环境并安装依赖

```bash
python3 -m venv venv
source venv/bin/activate

pip install --upgrade pip
pip install -r requirements.txt
```

#### 5. 手动启动测试

```bash
# 终端1：启动 BLE 服务
python lyric_app.py ble

# 终端2：启动 UI 服务
python lyric_app.py ui
```

#### 6. 配置 systemd 自启

```bash
# 复制服务文件
sudo cp systemd/lyric-ble.service /etc/systemd/system/
sudo cp systemd/lyric-ui.service /etc/systemd/system/

# 重新加载 systemd
sudo systemctl daemon-reload

# 启用服务
sudo systemctl enable lyric-ble lyric-ui

# 启动服务
sudo systemctl start lyric-ble lyric-ui
```

## 使用说明

### 连接蓝牙

1. 打开手机蓝牙设置
2. 搜索名为 "LyricSpeaker" 的设备（名称可在配置文件中修改）
3. 连接设备

### 推送歌词

使用支持 BLE 歌词推送的音乐 App（如网易云音乐、QQ 音乐等），播放音乐时歌词会自动推送到音箱显示。

### 远程控制

通过自研手机 App 或 BLE 调试工具，向控制特征写入 JSON 命令：

#### 修改歌词样式
```json
{
  "cmd": "style",
  "color": [255, 0, 0],
  "bg_color": [0, 0, 0],
  "font_size": 64
}
```

#### 切换音效
```json
{
  "cmd": "effect",
  "name": "rock"
}
```

#### 调节音量
```json
{
  "cmd": "volume",
  "level": 80
}
```

## 配置文件说明

配置文件支持**热重载**，修改后自动生效，无需重启服务。

```json
{
  "ble": {
    "lyric_service_uuid": "0000FFE0-0000-1000-8000-00805F9B34FB",  // 歌词服务 UUID
    "lyric_char_uuid": "0000FFE1-0000-1000-8000-00805F9B34FB",     // 歌词特征 UUID
    "control_service_uuid": "12345678-1234-1234-1234-123456789ABC", // 控制服务 UUID
    "control_char_uuid": "12345678-1234-1234-1234-123456789ABD",    // 控制特征 UUID
    "adapter": "/org/bluez/hci0",         // 蓝牙适配器路径
    "device_name": "LyricSpeaker"          // 蓝牙设备名称
  },
  "display": {
    "driver": "fbcon",                     // 显示驱动 (fbcon/x11)
    "fb_device": "/dev/fb0",               // Framebuffer 设备
    "x11_display": ":0",                   // X11 显示地址（driver=x11 时使用）
    "default_style": {
      "font_size": 48,                     // 字体大小
      "color": [0, 255, 0],               // 文字颜色 (RGB)
      "bg_color": [0, 0, 0],              // 背景颜色 (RGB)
      "font_name": null,                   // 字体路径（null 为自动检测）
      "line_spacing": 10,                  // 行间距
      "padding": 40                        // 边距
    }
  },
  "audio": {
    "presets": {                           // 音效预设
      "rock": { "module": "module-ladspa-sink", "label": "rock" },
      "pop": { "module": "module-ladspa-sink", "label": "pop" },
      "classical": { "module": "module-ladspa-sink", "label": "classical" },
      "flat": { "module": null, "label": null }
    },
    "default_volume": 70                   // 默认音量 (0-100)
  },
  "ipc": {
    "socket_path": "/tmp/lyric.sock"       // Unix Socket 路径
  },
  "logging": {
    "file": "/tmp/lyric-app.log"           // 日志文件路径
  }
}
```

## 日志查看

日志采用 JSON 结构化格式，支持日志轮转（10MB/份，保留 5 份）。

```bash
# 查看 BLE 服务日志
journalctl -u lyric-ble -f

# 查看 UI 服务日志
journalctl -u lyric-ui -f

# 查看 BLE 应用日志文件
tail -f /tmp/lyric-ble.log

# 查看 UI 应用日志文件
tail -f /tmp/lyric-ui.log
```

## 开发说明

### 从源码运行

```bash
# 克隆项目
git clone https://github.com/Hjw202/lyric-app.git
cd lyric-app

# 创建虚拟环境
python3 -m venv venv
source venv/bin/activate

# 安装依赖
pip install -r requirements.txt

# 运行 BLE 服务
python lyric_app.py ble

# 运行 UI 服务（另一个终端）
python lyric_app.py ui
```

### 打包可执行文件

#### 方式一：本地打包（Linux 系统）
```bash
# 安装 PyInstaller
pip install pyinstaller

# 打包
pyinstaller --onefile --add-data "config/config.json:config" lyric_app.py

# 生成的可执行文件在 dist/ 目录中
```

#### 方式二：GitHub Actions 自动打包（推荐）
1. 推送代码到 GitHub
2. 在 Actions 标签页查看构建进度
3. 构建完成后在 Releases 页面下载

```bash
# 创建 tag 触发发布
git tag v1.0.0
git push origin v1.0.0
```

自动构建的文件：
- `lyric_app_arm64` - ARM64 版本（树莓派 4/5 等）
- `lyric_app_armhf` - ARM32 版本（树莓派 2/3 等）

## 故障排除

### 蓝牙无法连接

1. 检查蓝牙服务状态：
   ```bash
   sudo systemctl status bluetooth
   ```

2. 检查蓝牙适配器：
   ```bash
   bluetoothctl list
   ```

3. 检查用户是否在 bluetooth 组：
   ```bash
   groups $USER
   ```

### 歌词不显示

1. 检查 BLE 服务是否正常运行：
   ```bash
   sudo systemctl status lyric-ble
   ```

2. 检查 IPC Socket 是否存在：
   ```bash
   ls -la /tmp/lyric.sock
   ```

3. 检查日志：
   ```bash
   journalctl -u lyric-ble -n 50
   ```

### 音效不生效

1. 检查 PulseAudio 状态：
   ```bash
   pulseaudio --check
   pactl info
   ```

2. 检查用户是否在 pulse-access 组：
   ```bash
   groups $USER
   ```

## 许可证

MIT License

## 联系方式

- 问题反馈：[GitHub Issues](https://github.com/Hjw202/lyric-app/issues)
