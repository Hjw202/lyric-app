
# 蓝牙歌词音箱软件 – 项目开发计划

## 1. 项目目标

开发一个运行在 Linux（ARM）开发板上的应用软件，实现以下核心功能：

- 接收手机通过 **蓝牙 A2DP** 推送的音频，由开发板本地扬声器播放（该部分由系统环境保证，本软件不处理音频接收，但可控制音效）。
- 接收主流音乐 App（网易云、QQ 音乐等）通过 **BLE** 推送的歌词，并全屏显示在屏幕上。
- 提供 **BLE 控制通道**，允许手机自定义控制 App 发送命令，实时修改歌词显示样式、切换音效、调节音量。
- 软件以 **两个独立进程** 运行，通过 Unix Socket 通信，并支持 **开机自启动**。
- **最终交付物**：一个免安装的独立可执行文件（基于 PyInstaller 打包），不依赖目标板上的 Python 环境。

## 2. 系统环境前提（由硬件团队负责，应用只需假设已就绪）

- Linux 系统（armhf 或 arm64），已安装并运行：
  - BlueZ ≥ 5.50（`bluetoothd`）
  - PulseAudio（含 `module-bluetooth-discover` 等蓝牙音频模块）
  - 显示 Framebuffer 设备（`/dev/fb0`）或 X11（`DISPLAY=:0`）
- 运行应用的用户（如 `pi`）需在 `bluetooth` 和 `pulse-access` 组中
- 开发板已正确连接扬声器和显示屏

## 3. 技术选型

| 组件 | 选用技术 |
|------|----------|
| 编程语言 | Python 3.9+ |
| 蓝牙 BLE 外设 | `bluez-peripheral`（基于 BlueZ D-Bus API） |
| 音频控制 | `pulsectl`（Python PulseAudio 绑定） |
| 歌词显示 | `pygame`（全屏渲染，支持 Framebuffer） |
| 进程通信 | Unix Domain Socket（行协议，JSON / 纯文本） |
| 打包交付 | PyInstaller（单文件可执行） |
| 服务管理 | systemd（开机自启） |

## 4. 软件架构

```
┌─────────────────────┐     Unix Socket      ┌──────────────────────┐
│   lyric-ble 进程     │◄─────────────────────►│   lyric-ui 进程       │
│                     │   /tmp/lyric.sock     │                      │
│ - BLE 歌词服务      │ 歌词文本 / JSON 命令    │ - Pygame 全屏显示     │
│ - BLE 控制服务      │                       │ - 命令执行器          │
│ - 转发数据到 UI     │                       │ - 音效管理            │
└─────────────────────┘                       └──────────────────────┘
```

- **lyric-ble 进程**：负责与手机蓝牙通信，提供两个 BLE 特征（歌词接收 + 控制命令），将收到的所有数据通过 Socket 转发给 `lyric-ui`。
- **lyric-ui 进程**：从 Socket 读取数据，区分歌词文本和 JSON 命令，更新 Pygame 显示界面，并调用 PulseAudio 音效接口。

## 5. 项目文件结构（交付前源码）

```
lyric-app/
├── lyric_app.py              # 统一入口，根据命令行参数启动 ble 或 ui
├── modules/
│   ├── __init__.py
│   ├── ble_server.py         # BLE 服务注册、歌词/控制特征处理
│   ├── display.py            # Pygame 初始化、歌词渲染、样式更新
│   ├── cmd_handler.py        # 命令解析与分发（调用 display 和 audio）
│   └── audio_effects.py      # 音效预设管理（调用 pulsectl）
├── config/
│   └── config.json           # 默认样式、UUID 配置、音效预设名
├── utils/
│   ├── __init__.py
│   └── ipc.py                # Unix Socket 服务端/客户端封装
├── systemd/
│   ├── lyric-ble.service
│   └── lyric-ui.service
├── requirements.txt
├── install.sh                # 安装脚本
└── README.md
```

## 6. 详细模块需求

### 6.1 统一入口 `lyric_app.py`
- 接受一个命令行参数：`ble` 或 `ui`。
- 如果参数是 `ble`，导入 `modules.ble_server.main()` 并运行。
- 如果参数是 `ui`，导入并启动 UI 主循环（包含 Socket 客户端、Pygame、命令处理等）。

### 6.2 BLE 服务模块 `ble_server.py`
**功能**：
- 使用 `bluez-peripheral` 创建一个 BLE 外设。
- 注册两个 GATT 服务：
  1. **歌词服务** (UUID 来自 `config.json`，默认 `0000FFE0-...`)，特征 UUID `0000FFE1-...`，支持 **Write** 和 **WriteWithoutResponse**。收到数据时解码为 UTF-8 字符串，通过 Socket 发送（每条文本后跟 `\n`）。
  2. **控制服务** (UUID 自定义，如 `12345678-...`)，特征 UUID `12345678-...`，同样支持写入。收到数据时直接作为一整行通过 Socket 转发（可能是 JSON 命令）。
- 维持 BLE 广播，自动处理连接/断开，断开后自动重启广播。
- 初始化时创建 Unix Socket 服务端（路径 `/tmp/lyric.sock`），并接受连接。

**技术要求**：
- 全部使用 `asyncio` 驱动，因为 `bluez-peripheral` 依赖异步。
- 必须捕获异常，避免进程意外退出，确保长期运行稳定性。

### 6.3 歌词显示模块 `display.py`
**功能**：
- 初始化 Pygame，根据配置选择 Framebuffer 或 X11（通过读取环境变量决定，或默认 `fbcon`）。
- 维护一个**歌词文本状态**和**样式状态**（字体大小、颜色、背景色等）。
- 提供线程安全的函数：
  - `update_lyrics(text: str)` – 替换当前显示的歌词
  - `apply_style(style_dict: dict)` – 更新显示样式
  - `get_current_style() -> dict` – 返回当前样式（用于保存）
- 主循环（`main_loop()`）在 UI 进程中被调用，持续刷新画面，从内部队列获取最新歌词并渲染。

**渲染要求**：
- 歌词居中显示，支持多行自动换行（针对长文本）。
- 默认样式从 `config.json` 加载。
- 无歌词时显示空白或默认提示（如“等待连接...”）。

### 6.4 命令处理模块 `cmd_handler.py`
**功能**：
- 解析从 Socket 接收到的字符串。如果字符串以 `{` 开头，尝试解析为 JSON，提取 `cmd` 字段：
  - `style` → 调用 `display.apply_style()`
  - `effect` → 调用 `audio_effects.set_effect(name)`
  - `volume` → 调用 `audio_effects.set_volume(level)`
- 若解析失败或非 JSON，忽略（因为可能是歌词文本，由其他逻辑处理）。
- 提供 `process_command(json_str: str)` 函数。

### 6.5 音效控制模块 `audio_effects.py`
**功能**：
- 使用 `pulsectl.Pulse()` 获取默认 sink。
- `set_effect(name: str)`：根据配置加载 PulseAudio 均衡器模块（如 `module-ladspa-sink` 或 `module-equalizer-sink`），支持预设名如 `rock`, `pop`, `flat` 等。若名称为 `none` 或 `flat`，卸载所有均衡器模块，恢复原始输出。
- `set_volume(level: int)`：设置音量值（0-100），调用 `pulsectl` 的 volume 设置接口。
- 所有模块加载/卸载需处理好异常，避免 PulseAudio 状态混乱。

### 6.6 IPC 通信模块 `utils/ipc.py`
**提供**：
- `create_server(sock_path)`：创建 Unix Socket 服务端，返回一个 `asyncio` 服务器对象，连接到来时接受并开始监听数据，每收到一条完整行（`\n` 分隔）调用回调函数。
- `create_client(sock_path, on_data_callback)`：创建客户端，连接到已有的 Socket，监听数据并回调。
- 回调函数接受 `line: str`（已去除换行符）。
- 需处理重连逻辑：如果连接失败，客户端应持续重试（间隔 2 秒），直到成功。

### 6.7 配置文件 `config/config.json`
```json
{
  "ble": {
    "lyric_service_uuid": "0000FFE0-0000-1000-8000-00805F9B34FB",
    "lyric_char_uuid": "0000FFE1-0000-1000-8000-00805F9B34FB",
    "control_service_uuid": "12345678-1234-1234-1234-123456789ABC",
    "control_char_uuid": "12345678-1234-1234-1234-123456789ABD"
  },
  "display": {
    "driver": "fbcon",
    "fb_device": "/dev/fb0",
    "default_style": {
      "font_size": 48,
      "color": [0, 255, 0],
      "bg_color": [0, 0, 0]
    }
  },
  "audio": {
    "presets": {
      "rock": "Rock",
      "pop": "Pop",
      "classical": "Classical",
      "flat": "flat"
    }
  }
}
```

## 7. 进程主循环设计

### 7.1 lyric-ble 进程主循环
1. 启动 Socket 服务端。
2. 注册 BLE 外设（歌词服务 + 控制服务）。
3. 开始 BLE 广播。
4. 当有客户端连接到 Socket，将 BLE 收到的数据通过回调发送给该客户端。
5. 保持 `asyncio` 事件循环运行，处理所有异步任务。

### 7.2 lyric-ui 进程主循环
1. 启动 Socket 客户端，连接到 `/tmp/lyric.sock`。
2. 初始化 Pygame 和显示窗口。
3. 创建命令处理器和音效管理器。
4. 进入 Pygame 主循环，每帧：
   - 处理 Pygame 事件（如按 ESC 退出）。
   - 从 Socket 客户端收到的数据中提取歌词/命令并处理。
   - 根据当前样式重新渲染文本。
   - 刷新显示。
5. 设置帧率为 10fps 足够。

> 注意：Socket 客户端读取数据应在独立线程中运行，通过队列将歌词/命令传给主线程，保证 Pygame 主循环不阻塞。

## 8. 实现步骤（建议按此顺序进行）

1. **搭建项目骨架**  
   - 创建目录结构，编写 `lyric_app.py` 入口。
   - 编写 `config.json`。
   - 编写 `utils/ipc.py` 并测试（用简单脚本模拟客户端/服务端通信）。

2. **实现 BLE 模块**  
   - 编写 `ble_server.py`，暂时只实现歌词服务，能接收手机 App 推送的歌词并打印。
   - 集成 Socket 发送，验证歌词能到达 Socket 客户端。

3. **实现显示模块**  
   - 编写 `display.py`，能全屏显示静态文本，样式可配置。
   - 编写一个测试 UI 入口，从 Socket 客户端接收文本并显示。

4. **实现命令处理**  
   - 编写 `cmd_handler.py`，解析 JSON 并调用 display 和 audio 的桩函数。
   - 将命令处理逻辑集成到 UI 进程中。

5. **实现音效控制**  
   - 编写 `audio_effects.py`，使用 `pulsectl` 加载均衡器预设。
   - 测试音量调节。

6. **扩展 BLE 控制服务**  
   - 在 `ble_server.py` 中添加控制特征，接收手机命令并转发给 UI。

7. **完整集成与调试**  
   - 在开发板实机运行，使用手机测试歌词显示、样式切换、音效切换。
   - 处理长文本换行、异常断连、资源竞争等问题。

8. **打包**  
   - 配置 PyInstaller spec 文件，将入口 `lyric_app.py` 打包为单文件 `lyric_app`。
   - 确保运行时能读取同目录下的 `config.json`。
   - 生成最终可执行文件。

9. **编写 systemd 服务和安装脚本**  
   - 编写 `lyric-ble.service` 和 `lyric-ui.service`。
   - 编写 `install.sh`，将 `lyric_app` 复制到 `/opt/lyric-app/`，配置文件复制到 `/etc/lyric-app/`，安装并启用服务。

10. **交付文档**  
    - `README.md`：系统要求、安装步骤、使用说明、配置文件释义。

## 9. 打包与交付说明

- 使用 **PyInstaller** 在 ARM 开发板上（或通过 QEMU 模拟）构建。
- 打包命令：`pyinstaller --onefile --add-data "config/config.json:config" lyric_app.py`
- 最终交付压缩包包含：
  ```
  lyric-app-v1.0-arm64.tar.gz
  ├── lyric_app          # 可执行文件
  ├── config.json        # 外部配置文件
  ├── systemd/
  │   ├── lyric-ble.service
  │   └── lyric-ui.service
  └── install.sh
  ```

## 10. 关键约束与注意事项

- 所有外部依赖（`pygame`, `pulsectl`, `bluez-peripheral` 等）在打包时会自动包含进可执行文件，**目标系统无需安装 Python**。
- 系统级库（如 `libsdl2`, `libbluetooth`, `libpulse`）不在打包范围内，必须由硬件团队在系统环境中预装，这些已在“系统环境前提”中说明。
- 蓝牙设备适配器路径默认使用 `/org/bluez/hci0`，若硬件不同，需从配置读取或自动探测。
- 使用 BLE 控制服务时，自研手机 App 需写入该特征并遵循 JSON 协议。
