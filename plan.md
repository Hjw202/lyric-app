
# 蓝牙歌词音箱软件 – 项目开发计划

## 项目状态

| 阶段 | 状态 | 备注 |
|------|------|------|
| 项目骨架 + IPC | ✅ 已完成 | Unix Socket 双向通信，支持心跳检测和自动重连 |
| BLE 模块 | ✅ 已完成 | 自动重试、连接状态监控、统计信息 |
| 显示模块 | ✅ 已完成 | 文本缓存、脏矩形更新、中文字体自动检测 |
| 命令处理 | ✅ 已完成 | JSON 命令解析与分发 |
| 音效控制 | ⚠️ 基础完成 | 音量控制已实现，均衡器预设加载为 TODO |
| 配置管理 | ✅ 已完成 | watchdog 热重载 + 变更通知 |
| 日志系统 | ✅ 已完成 | 结构化 JSON 日志 + 性能指标 |
| systemd 服务 | ✅ 已完成 | lyric-ble / lyric-ui 两个服务单元 |
| 安装脚本 | ✅ 已完成 | install.sh |
| PyInstaller 打包 | ✅ 已完成 | lyric_app.spec |

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

## 5. 项目文件结构（实际交付）

```
lyric-app/
├── lyric_app.py              # 统一入口，根据命令行参数启动 ble 或 ui
├── modules/
│   ├── __init__.py
│   ├── ble_server.py         # BLE 服务注册、歌词/控制特征处理（含自动重试）
│   ├── display.py            # Pygame 初始化、歌词渲染、样式更新（含文本缓存）
│   ├── cmd_handler.py        # 命令解析与分发（调用 display 和 audio）
│   ├── audio_effects.py      # 音效预设管理（调用 pulsectl）
│   └── config_manager.py     # 配置管理器（watchdog 热重载 + 变更通知）
├── config/
│   └── config.json           # 默认样式、UUID 配置、音效预设名
├── utils/
│   ├── __init__.py
│   ├── ipc.py                # Unix Socket 服务端/客户端封装（含心跳检测）
│   └── logger.py             # 结构化日志 + 性能指标记录
├── systemd/
│   ├── lyric-ble.service
│   └── lyric-ui.service
├── requirements.txt
├── install.sh                # 安装脚本
├── lyric_app.spec            # PyInstaller 打包配置
├── CLAUDE.md                 # Claude Code 开发指南
├── plan.md                   # 本文件
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

**已实现的增强功能**：
- `BLEState` 状态机（IDLE → STARTING → RUNNING → ERROR → STOPPING）
- 自动重试机制（可配置 `max_retries` 和 `retry_delay`，默认无限重试）
- `BLEStats` 统计信息（连接数、歌词/命令接收数、错误数、重启次数）
- `get_status()` 方法返回服务状态和统计信息

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

**已实现的增强功能**：
- `TextCache` LRU 缓存（最多 200 条），避免重复渲染相同文本
- 脏矩形更新：歌词变化时只重绘变化区域，样式变化时全屏重绘
- 双缓冲 + 硬件加速（`DOUBLEBUF | HWSURFACE`）
- 中文字体自动检测：依次尝试 wqy-microhei → DroidSansFallback → NotoSansCJK
- 线程安全的样式锁（`_style_lock`）

**渲染要求**：
- 歌词居中显示，支持多行自动换行（针对长文本）。
- 默认样式从 `config.json` 加载。
- 无歌词时显示空白或默认提示（如”等待连接...”）。

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

**待完善**：
- `_load_equalizer_module()` 中 LADSPA 均衡器的实际加载逻辑需要根据目标硬件配置具体参数（插件路径、控制端口等），当前为 TODO 状态。

### 6.6 IPC 通信模块 `utils/ipc.py`
**提供**：
- `IPCServer`：Unix Socket 服务端，支持多客户端连接，每收到一条完整行（`\n` 分隔）调用回调函数。
- `IPCClient`：Unix Socket 客户端，监听数据并回调，支持指数退避重连（初始 2 秒，1.5 倍退避，最大 30 秒）。
- 回调函数接受 `line: str`（已去除换行符）。

**已实现的增强功能**：
- 心跳检测（30 秒间隔）和客户端超时清理（60 秒无活动）
- `IPCStats` 流量统计（收发消息数、字节数、连接数、错误数）
- `broadcast()` 向所有客户端广播，自动清理断开的连接
- `send_to_client()` 向指定客户端发送
- 客户端发送队列（异步队列，最大 1000 条）

### 6.7 配置管理模块 `modules/config_manager.py`
**功能**：
- `ConfigManager`：加载 JSON 配置文件，支持点号分隔的路径访问（如 `display.default_style.font_size`）
- 使用 `watchdog` 监听配置文件变更，实现热重载
- `ConfigChangeEvent` 变更事件，递归通知嵌套字典的变更
- 监听器机制：BLE 和 UI 进程注册回调，配置变更时自动更新运行时状态
- 全局单例模式：`init_config_manager()` / `get_config_manager()` / `cleanup_config_manager()`

### 6.8 日志模块 `utils/logger.py`
**功能**：
- `StructuredFormatter`：JSON 格式日志输出，包含时间戳、级别、服务名、消息、异常信息
- `MetricsLogger`：性能指标记录器，支持 `set_metric()` / `increment()` / `log_metrics()`
- `setup_logger()`：配置日志记录器，支持控制台 + 文件输出（RotatingFileHandler，10MB 轮转，保留 5 份）
- `LogContext`：上下文管理器，自动记录操作耗时

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

## 8. 实现步骤

1. ✅ **搭建项目骨架**
   - 创建目录结构，编写 `lyric_app.py` 入口。
   - 编写 `config.json`。
   - 编写 `utils/ipc.py`（含心跳检测、流量统计、自动重连）。

2. ✅ **实现 BLE 模块**
   - 编写 `ble_server.py`，实现歌词/控制两个 GATT 服务。
   - 集成 Socket 广播，自动重试机制。

3. ✅ **实现显示模块**
   - 编写 `display.py`，全屏显示 + 文本缓存 + 脏矩形更新。
   - 中文字体自动检测，双缓冲硬件加速。

4. ✅ **实现命令处理**
   - 编写 `cmd_handler.py`，解析 JSON 并调用 display 和 audio。
   - 支持 style / effect / volume 三种命令。

5. ⚠️ **实现音效控制**
   - 编写 `audio_effects.py`，音量控制已实现。
   - 均衡器预设加载需根据目标硬件配置（TODO）。

6. ✅ **配置管理与日志**
   - 编写 `config_manager.py`，watchdog 热重载 + 变更通知。
   - 编写 `utils/logger.py`，结构化 JSON 日志 + 性能指标。

7. ✅ **完整集成**
   - BLE 和 UI 进程通过 Unix Socket 通信。
   - 配置变更自动生效。

8. ✅ **打包**
   - 配置 PyInstaller spec 文件，打包为单文件可执行。
   - 生成 `dist/lyric_app`。

9. ✅ **systemd 服务和安装脚本**
   - 编写 `lyric-ble.service` 和 `lyric-ui.service`。
   - 编写 `install.sh`，自动化安装流程。

10. ✅ **交付文档**
    - `README.md`：系统要求、安装步骤、使用说明、配置文件释义。
    - `CLAUDE.md`：开发指南。
    - `plan.md`：本文件（项目计划与状态）。

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
