# Python + Web 前端改造计划

> **状态**：规划中，尚未实施
> **基于**：`tech-comparison.md` 方案 5（Python+Web，改动最小，UI 效果提升大）
> **目标**：用浏览器 CSS 动画替代 Pygame 渲染，提升歌词显示效果（逐字高亮、平滑过渡、自定义字体），同时完全复用现有 BLE 和音效代码。

---

## 架构变更

```
改造前（双进程）:
  BLE进程 (IPC Server) ←──Unix Socket──→ UI进程 (Pygame 全屏渲染)

改造后（单进程）:
  主进程 (asyncio 事件循环):
    ├─ BLE peripheral (bluez-peripheral)        ← 完全复用，不改动
    │   └─ on_lyric(text) / on_command(text) 回调
    ├─ WebServer (aiohttp)
    │   ├─ GET /           → 返回 web/index.html
    │   ├─ GET /ws         → WebSocket 双向通信
    │   └─ GET /static/*   → CSS/JS 静态文件
    ├─ AudioEffects (pulsectl)                  ← 完全复用，不改动
    ├─ CommandHandler                           ← 适配：style 命令通过 WebSocket 推送
    └─ ConfigManager (watchdog 热重载)          ← 完全复用，不改动

  Browser (chromium --kiosk http://localhost:8080)
    └─ Web UI: WebSocket 客户端 + CSS 逐字高亮歌词渲染
```

核心变化：双进程合并为单进程，Unix Socket IPC 被 WebSocket 替代，Pygame 渲染被浏览器 CSS 动画替代。BLE 和音效模块完全不动。

---

## WebSocket 通信协议

原 IPC 使用行协议（`\n` 分隔，纯文本=歌词，`{` 开头=JSON 命令）。WebSocket 改为统一 JSON 消息，每条消息包含 `type` 字段区分类型：

```jsonc
// 服务端 → 浏览器：歌词推送
{"type": "lyric", "text": "轰轰烈烈的疯狂 追求希望的荧火"}

// 服务端 → 浏览器：样式更新
{"type": "style", "data": {"color": [255, 0, 0], "font_size": 56}}

// 服务端 → 浏览器：心跳（30s 一次，浏览器需在 60s 内回 pong）
{"type": "ping"}

// 浏览器 → 服务端：心跳响应
{"type": "pong"}

// 浏览器 → 服务端：（当前无上行命令，预留扩展）
```

设计理由：统一 JSON 避免歌词文本中偶然出现 `{` 被误判为命令的问题；`type` 字段使协议可扩展。

---

## 改动文件清单

### 新增文件

| 文件 | 说明 |
|---|---|
| `modules/web_server.py` | aiohttp Web 服务器（HTTP 静态文件 + WebSocket 广播 + 心跳管理） |
| `web/index.html` | 歌词显示页面（全屏黑底，居中歌词，逐字高亮） |
| `web/style.css` | 样式：全屏布局、CSS 变量驱动主题、逐字高亮过渡动画 |
| `web/app.js` | WebSocket 客户端 + 逐字高亮渲染逻辑 + 断线重连 |
| `systemd/lyric-web.service` | 单进程 systemd 服务（Python + chromium） |
| `scripts/start-kiosk.sh` | chromium kiosk 启动脚本（带 GPU/沙箱适配） |

### 修改文件

| 文件 | 改动内容 |
|---|---|
| `lyric_app.py` | 新增 `run_web(config_path)` 函数，集成 BLE + WebServer + AudioEffects；保留 `ble`/`ui` 模式向后兼容 |
| `modules/cmd_handler.py` | `process_command()` 增加可选回调参数，style 命令通过回调推送到浏览器；effect/volume 仍直接调 audio_effects |
| `config/config.json` | 新增 `web` 配置段（host、port、kiosk 选项）；`display.default_style` 保留供 Web 前端读取 |
| `lyric_app.spec` | `datas` 新增 `web/` 目录打包；`hiddenimports` 新增 aiohttp 相关模块 |
| `requirements.txt` | 新增 `aiohttp>=3.9.0`；`pygame>=2.5.0` 改为可选（标注 `# 仅 ui 模式需要`） |
| `Dockerfile.arm64` / `Dockerfile.armhf` | 无需新增系统依赖（aiohttp 是纯 Python），保持不变 |
| `.gitignore` | 新增 `web/` 目录不被忽略（确保打包时能找到） |
| `CLAUDE.md` | 更新架构图和运行说明 |

### 不改动（完全复用）

| 文件 | 说明 |
|---|---|
| `modules/ble_server.py` | BLE 外设，完全不变 |
| `modules/audio_effects.py` | PulseAudio 控制，完全不变 |
| `modules/config_manager.py` | 配置热重载，完全不变 |
| `utils/logger.py` | 日志系统，完全不变 |
| `utils/ipc.py` | 单进程不再需要，但保留文件不删除（向后兼容 `ble`/`ui` 模式） |

---

## 实现步骤

### Step 1: 新增 Web 前端文件

#### `web/index.html` — 歌词全屏页面

- 全屏黑色背景，歌词居中显示
- 引入 style.css 和 app.js
- 结构：`<div id="lyrics">` 包含逐字 `<span>` 元素
- 断线提示遮罩层（`<div id="status">`），连接恢复后自动隐藏

#### `web/style.css` — 样式

- CSS 变量 `--text-color`, `--bg-color`, `--font-size`, `--line-spacing`, `--padding` 驱动主题
- JavaScript 通过 `document.documentElement.style.setProperty()` 动态修改变量
- 逐字高亮：`.char.active` 类用亮色，`.char` 默认用暗色（`opacity: 0.35`），带 `transition: color 0.3s, opacity 0.3s`
- 全屏无滚动条：`html, body { margin: 0; padding: 0; overflow: hidden; }`
- 字体优先级：`'WenQuanYi Micro Hei', 'Noto Sans CJK SC', 'Droid Sans Fallback', sans-serif`
- 断线提示遮罩：`#status { position: fixed; top: 0; left: 0; width: 100%; height: 100%; ... }`

#### `web/app.js` — 前端逻辑

```javascript
class LyricClient {
    constructor() {
        this.ws = null;
        this.reconnectDelay = 2000;  // 初始重连延迟 2s
        this.maxReconnectDelay = 30000;  // 最大 30s
        this.heartbeatTimer = null;
        this.karaokeTimer = null;
        this.chars = [];       // 当前歌词的字符 span 数组
        this.activeIndex = 0;  // 当前高亮到第几个字
        this.charInterval = 200; // 每字高亮间隔（ms），可配置
    }

    connect() { /* WebSocket 连接 + 指数退避重连 */ }
    onMessage(event) {
        const msg = JSON.parse(event.data);
        switch (msg.type) {
            case 'lyric':  this.renderLyric(msg.text); break;
            case 'style':  this.applyStyle(msg.data); break;
            case 'ping':   this.ws.send(JSON.stringify({type: 'pong'})); break;
        }
    }
    renderLyric(text) { /* 逐字拆分为 <span>，启动高亮定时器 */ }
    applyStyle(data) { /* 更新 CSS 变量 */ }
    startKaraoke() { /* 定时器逐字添加 .active 类 */ }
}
```

逐字高亮说明：收到歌词后，将文本逐字拆分为 `<span class="char">`，每个字初始为暗色。定时器按 `charInterval` 毫秒间隔逐个添加 `.active` 类（变亮），形成卡拉OK效果。间隔速度可通过 style 命令配置（`{"type":"style","data":{"char_interval":150}}`）。

### Step 2: 新增 Web 服务器

#### `modules/web_server.py`

```python
import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Set, Optional, Callable
from aiohttp import web, WebSocketResponse, WSMsgType

logger = logging.getLogger(__name__)


class WebServer:
    """aiohttp Web 服务器：HTTP 静态文件 + WebSocket 广播"""

    def __init__(
        self,
        config: dict,
        on_command: Optional[Callable[[str], None]] = None,
    ):
        self.web_config = config.get('web', {})
        self.host = self.web_config.get('host', '127.0.0.1')
        self.port = self.web_config.get('port', 8080)
        self.on_command = on_command  # 浏览器上行命令回调（预留）

        # 定位 web 静态文件目录（兼容 PyInstaller 打包和源码运行）
        if getattr(sys, 'frozen', False):
            web_dir = Path(sys._MEIPASS) / 'web'
        else:
            web_dir = Path(__file__).parent.parent / 'web'

        self.web_dir = web_dir
        self.app = web.Application()
        self._setup_routes()

        # WebSocket 客户端管理
        self._websockets: Set[WebSocketResponse] = set()
        self._lock = asyncio.Lock()

        # 心跳配置
        self._heartbeat_interval = 30.0
        self._heartbeat_task: Optional[asyncio.Task] = None

    def _setup_routes(self):
        self.app.router.add_get('/', self._index_handler)
        self.app.router.add_get('/ws', self._ws_handler)
        if self.web_dir.exists():
            self.app.router.add_static('/', path=str(self.web_dir))

    async def _index_handler(self, request):
        return web.FileResponse(self.web_dir / 'index.html')

    async def _ws_handler(self, request):
        ws = WebSocketResponse(heartbeat=self._heartbeat_interval)
        await ws.prepare(request)

        async with self._lock:
            self._websockets.add(ws)
        logger.info(f"WebSocket 客户端已连接: {request.remote}")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # 预留：处理浏览器上行命令
                    try:
                        data = json.loads(msg.data)
                        if data.get('type') == 'pong':
                            continue
                        if self.on_command:
                            self.on_command(msg.data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket 错误: {ws.exception()}")
        finally:
            async with self._lock:
                self._websockets.discard(ws)
            logger.info("WebSocket 客户端已断开")

    async def broadcast(self, message: dict):
        """向所有 WebSocket 客户端广播 JSON 消息"""
        text = json.dumps(message, ensure_ascii=False)
        disconnected = set()

        async with self._lock:
            clients = list(self._websockets)

        for ws in clients:
            try:
                await ws.send_str(text)
            except Exception:
                disconnected.add(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._websockets.discard(ws)

    async def broadcast_lyric(self, text: str):
        """广播歌词"""
        await self.broadcast({"type": "lyric", "text": text})

    async def broadcast_style(self, style: dict):
        """广播样式更新"""
        await self.broadcast({"type": "style", "data": style})

    async def start(self):
        """启动 Web 服务器"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"Web 服务器已启动: http://{self.host}:{self.port}")

    async def stop(self):
        """停止 Web 服务器"""
        # 关闭所有 WebSocket
        async with self._lock:
            for ws in self._websockets:
                await ws.close()
            self._websockets.clear()

        if hasattr(self, 'runner'):
            await self.runner.cleanup()
        logger.info("Web 服务器已停止")
```

关键设计点：
- 静态文件路径兼容 PyInstaller 打包（`sys._MEIPASS`）和源码运行（`__file__`）
- WebSocket 使用 aiohttp 内置 `heartbeat` 参数实现心跳（自动 ping/pong），无需手动管理
- `broadcast` 方法处理客户端断线清理，避免向已关闭的 WebSocket 发送
- `host` 默认 `127.0.0.1`（仅本地访问，chromium 在同一设备上运行）

### Step 3: 修改 lyric_app.py

新增 `run_web(config_path)` 函数，合并 BLE + WebServer 为单进程：

```python
def run_web(config_path: str):
    """运行 Web 单进程模式（BLE + WebServer 合一）"""
    from modules.ble_server import BLEServer
    from modules.web_server import WebServer
    from modules.audio_effects import AudioEffects
    from modules.cmd_handler import CommandHandler
    from modules.config_manager import init_config_manager, cleanup_config_manager

    config_manager = init_config_manager(config_path, auto_reload=True)
    config = config_manager.config

    global logger
    log_file = config.get('logging', {}).get('web_file', '/var/log/lyric-app/lyric-web.log')
    logger = MetricsLogger(setup_logger('lyric-web', log_file=log_file, service_name='lyric-web'))

    # 创建音效和命令处理器
    audio_effects = AudioEffects(config)
    cmd_handler = CommandHandler(config, None, audio_effects)  # display=None

    # 创建 Web 服务器
    web_server = WebServer(config)

    # 命令处理回调：BLE 收到命令后，先处理音效，再推送到浏览器
    def on_command(text: str):
        # CommandHandler 处理 effect/volume（直接调 audio_effects）
        # style 命令需要推送到浏览器
        style_result = cmd_handler.process_command_with_callback(
            text,
            on_style=lambda s: asyncio.run_coroutine_threadsafe(
                web_server.broadcast_style(s), loop
            )
        )

    def on_lyric(text: str):
        asyncio.run_coroutine_threadsafe(
            web_server.broadcast_lyric(text), loop
        )

    # 创建 BLE 服务器
    ble_config = config.get('ble', {})
    ble_server = BLEServer(ble_config, on_lyric, on_command)

    # 事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 信号处理
    shutdown_event = asyncio.Event()
    def signal_handler():
        shutdown_event.set()
    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    # 配置变更监听
    def on_config_change(event):
        if event.key.startswith('display.'):
            style = config_manager.get('display.default_style', {})
            asyncio.run_coroutine_threadsafe(web_server.broadcast_style(style), loop)
    config_manager.add_listener(on_config_change)

    async def main():
        await web_server.start()
        ble_task = asyncio.create_task(ble_server.start())
        await shutdown_event.wait()
        ble_task.cancel()
        try:
            await ble_task
        except asyncio.CancelledError:
            pass
        await web_server.stop()

    try:
        with LogContext(logger.logger, "Web 服务"):
            loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.logger.info("收到中断信号")
    except Exception as e:
        logger.logger.error(f"Web 服务错误: {e}")
    finally:
        audio_effects.close()
        cleanup_config_manager()
        loop.close()
        logger.log_metrics("Web 服务统计")
```

CLI 入口更新：

```python
def main():
    if len(sys.argv) < 2:
        print("用法: lyric_app.py <web|ble|ui>")
        print("  web  - 启动 Web 单进程模式（推荐）")
        print("  ble  - 启动 BLE 服务进程（向后兼容）")
        print("  ui   - 启动 Pygame UI 显示进程（向后兼容）")
        sys.exit(1)
    mode = sys.argv[1].lower()
    config_path = load_config_path()
    if mode == 'web':
        run_web(config_path)
    elif mode == 'ble':
        run_ble(config_path)
    elif mode == 'ui':
        run_ui(config_path)
    # ...
```

### Step 4: 修改 cmd_handler.py

新增 `process_command_with_callback` 方法，在处理 style 命令时通过回调通知外部（web_server），而非直接操作 display：

```python
def process_command_with_callback(self, json_str: str, on_style=None) -> bool:
    """处理 JSON 命令，style 命令通过回调推送"""
    json_str = json_str.strip()
    if not json_str.startswith('{'):
        return False
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError:
        return False

    cmd = data.get('cmd')
    handler = self._handlers.get(cmd)
    if not handler:
        return False

    if cmd == 'style':
        # style 命令：提取样式后通过回调推送，同时更新本地 display（如有）
        style = self._extract_style(data)
        if style:
            if self.display:
                self.display.apply_style(style)
            if on_style:
                on_style(style)  # 推送到浏览器
        return True
    else:
        # effect/volume 命令：直接执行（不需要推送到浏览器）
        try:
            handler(data)
            return True
        except Exception as e:
            logger.error(f"执行命令 {cmd} 失败: {e}")
            return False
```

原有的 `process_command` 保持不变（向后兼容 `ui` 模式）。

### Step 5: 配置和部署

#### config.json 新增 web 配置段

```json
{
  "web": {
    "host": "127.0.0.1",
    "port": 8080,
    "kiosk": {
      "enabled": true,
      "browser": "chromium-browser",
      "flags": ["--kiosk", "--noerrdialogs", "--disable-infobars", "--disable-gpu", "--no-sandbox"]
    }
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
  }
}
```

`host` 默认 `127.0.0.1`（仅本地），如需远程调试可改为 `0.0.0.0`。`kiosk.flags` 中 `--disable-gpu` 适配部分 ARM 板的 GPU 驱动问题，`--no-sandbox` 适配 systemd 服务无用户会话的场景。

#### `scripts/start-kiosk.sh` — chromium 启动脚本

```bash
#!/bin/bash
# chromium kiosk 启动脚本
BROWSER="${BROWSER:-chromium-browser}"
URL="${URL:-http://localhost:8080}"

# 等待 Web 服务器就绪
for i in $(seq 1 30); do
    if curl -s "$URL" > /dev/null 2>&1; then
        break
    fi
    sleep 1
done

exec "$BROWSER" \
    --kiosk \
    --noerrdialogs \
    --disable-infobars \
    --disable-gpu \
    --no-sandbox \
    --disable-software-rasterizer \
    --start-fullscreen \
    --hide-cursor \
    "$URL"
```

启动脚本先等待 Web 服务器就绪再启动浏览器，避免浏览器加载空白页面。

#### `systemd/lyric-web.service` — 单进程服务

```ini
[Unit]
Description=Lyric Speaker Web Service (BLE + WebServer + chromium)
After=bluetooth.service graphical.target pulseaudio.service
Requires=bluetooth.service
Wants=pulseaudio.service

[Service]
Type=simple
User=__USER__
Group=bluetooth
SupplementaryGroup=pulse-access
ExecStart=/opt/lyric-app/lyric_app web
ExecStartPost=/opt/lyric-app/scripts/start-kiosk.sh
Restart=always
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=lyric-web

# 环境变量
Environment=DISPLAY=:0
Environment=PULSE_SERVER=unix:/run/pulse/native
Environment=XDG_RUNTIME_DIR=/run/user/__UID__
Environment=DBUS_SESSION_BUS_ADDRESS=unix:path=/run/user/__UID__/bus

[Install]
WantedBy=graphical.target
```

说明：
- `SupplementaryGroup=pulse-access` 让单进程同时拥有 bluetooth 组和 pulse-access 组权限（原双进程分别用不同组）
- `ExecStartPost` 在 Python 进程启动后拉起 chromium
- `WantedBy=graphical.target` 而非 `multi-user.target`，因为需要 X11/Wayland 图形环境
- chromium 崩溃不影响主进程（`ExecStartPost` 失败不触发 `Restart`），但可通过添加独立的 chromium systemd 服务实现自动重启

#### 从双进程迁移到单进程

```bash
# 1. 停止旧服务
sudo systemctl stop lyric-ble lyric-ui
sudo systemctl disable lyric-ble lyric-ui

# 2. 升级安装
sudo ./install.sh --upgrade

# 3. 启动新服务
sudo systemctl enable lyric-web
sudo systemctl start lyric-web

# 4. （可选）删除旧服务文件
sudo rm /etc/systemd/system/lyric-ble.service /etc/systemd/system/lyric-ui.service
sudo systemctl daemon-reload
```

`install.sh` 需要更新：检测到 `lyric-web.service` 时安装新服务，同时保留 `lyric-ble.service` 和 `lyric-ui.service` 的安装逻辑（向后兼容）。

### Step 6: 更新 PyInstaller 打包配置

#### `lyric_app.spec` 修改

```python
a = Analysis(
    ['lyric_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config/config.json', 'config'),
        ('web/', 'web'),                    # 新增：打包 Web 前端文件
        ('scripts/', 'scripts'),            # 新增：打包启动脚本
    ],
    hiddenimports=[
        # 现有 hidden imports 保持不变
        'watchdog.observers.inotify_buffer',
        'watchdog.observers.inotify',
        'watchdog.observers.polling',
        'dbus_next', 'dbus_next.aio', 'dbus_next.constants',
        'dbus_next.message_bus', 'dbus_next.proxy',
        'dbus_next.validators', 'dbus_next.signature',
        'bluez_peripheral', 'bluez_peripheral.advert',
        'bluez_peripheral.gatt', 'bluez_peripheral.service',
        'bluez_peripheral.util',
        # 新增：aiohttp 相关
        'aiohttp', 'aiohttp.web', 'aiohttp.web_app',
        'aiohttp.web_runner', 'aiohttp.web_socketserver',
        'aiohttp.websocket', 'aiohttp.http_parser',
    ],
    # ... 其余不变
)
```

关键：`datas` 必须包含 `('web/', 'web')`，否则打包后的二进制找不到 HTML/CSS/JS 文件。

#### `requirements.txt` 修改

```
# BLE 蓝牙外设
bluez-peripheral>=0.1.7
dbus-next>=0.2.0

# 音频控制
pulsectl>=23.5.0

# Web 服务器（新增）
aiohttp>=3.9.0

# 配置文件监听
watchdog>=3.0.0

# 图形显示（仅 ui 模式需要，web 模式不需要）
# pygame>=2.5.0
```

pygame 注释掉或移除，减少包体积约 5-10MB。如果仍需 `ui` 模式向后兼容，可保留但标注为可选。

### Step 7: 更新 install.sh

`install.sh` 需要适配新的 `lyric-web.service`：

- 检测并安装 `lyric-web.service`（如果存在）
- 保留 `lyric-ble.service` 和 `lyric-ui.service` 的安装（向后兼容）
- `scripts/` 目录也需复制到安装目录
- chromium 依赖检测：检查 `chromium-browser` 或 `chromium` 是否安装，未安装时提示用户

### Step 8: 更新 CLAUDE.md

更新架构图、运行命令和依赖说明。

---

## 数据流

```
手机 App
  │ BLE Write (歌词文本 / JSON 命令)
  ▼
BLEServer (bluez-peripheral, D-Bus 回调)
  │ decode UTF-8
  ├─ on_lyric(text)
  │   └─ web_server.broadcast_lyric(text)  ──WebSocket──→  浏览器
  │                                                          ├─ 收到歌词 → 逐字拆分 <span>
  │                                                          └─ 定时器逐字高亮（卡拉OK效果）
  │
  └─ on_command(text)
      └─ cmd_handler.process_command_with_callback(text, on_style)
          ├─ cmd == "style"  → on_style(style_dict)
          │                     └─ web_server.broadcast_style(style)  ──WebSocket──→  浏览器
          │                                                                          └─ 更新 CSS 变量
          ├─ cmd == "effect" → audio_effects.set_effect(name)  （后端直接处理）
          └─ cmd == "volume" → audio_effects.set_volume(level)  （后端直接处理）
```

---

## 错误处理与容错

### chromium 启动失败

`start-kiosk.sh` 脚本中 Web 服务器等待超时后仍会尝试启动浏览器。如果 `chromium-browser` 不存在，`exec` 会失败但主 Python 进程不受影响（`ExecStartPost` 失败不停止主服务）。用户可通过日志排查：

```bash
journalctl -u lyric-web -f
```

建议在 `install.sh` 中添加 chromium 依赖检测：

```bash
if ! command -v chromium-browser &>/dev/null && ! command -v chromium &>/dev/null; then
    echo -e "${YELLOW}警告: 未找到 chromium-browser，Web 模式需要安装${NC}"
    echo "  sudo apt install chromium-browser"
fi
```

### WebSocket 断线重连

浏览器端 `app.js` 实现指数退避重连（初始 2s，最大 30s），重连期间显示"正在重连..."遮罩。服务端清理断开的 WebSocket 连接，重连后重新推送当前歌词状态。

### 端口冲突

如果 8080 端口被占用，aiohttp 启动时会抛出 `OSError: [Errno 98] Address already in use`。建议在 `config.json` 中配置备用端口，或在日志中明确提示端口冲突。

### 配置热重载联动

`ConfigManager` 检测到 `display.default_style` 变更时，通过 `on_config_change` 回调将新样式推送到浏览器（通过 WebSocket `broadcast_style`），实现配置修改后实时生效，无需重启服务。

---

## 验证方案

1. **本地页面测试**：`python lyric_app.py web`，浏览器打开 `http://localhost:8080` 确认页面加载，黑底居中歌词区域可见
2. **WebSocket 测试**：用 `wscat -c ws://localhost:8080/ws` 连接，发送 `{"type":"pong"}` 确认连接正常；服务端发送 `{"type":"lyric","text":"测试歌词"}` 确认浏览器显示
3. **逐字高亮测试**：发送长歌词，观察逐字高亮动画效果和速度
4. **样式命令测试**：发送 `{"cmd":"style","color":[255,0,0],"font_size":56}` 确认浏览器颜色和字号变化
5. **音效命令测试**：发送 `{"cmd":"effect","name":"rock"}` 和 `{"cmd":"volume","level":50}` 确认后端音效执行（浏览器无变化是正常的）
6. **断线重连测试**：停止服务端，观察浏览器显示"正在重连..."；重启服务端，确认自动恢复
7. **BLE 端到端测试**：用手机 BLE 工具（如 nRF Connect）连接写入歌词，确认浏览器实时更新
8. **kiosk 模式测试**：在目标板运行 `start-kiosk.sh`，确认 chromium 全屏打开并显示歌词页面
9. **打包测试**：`pyinstaller lyric_app.spec` 后运行二进制，确认 `web/` 目录正确打包，页面可访问
10. **systemd 部署测试**：`install.sh` 安装后 `systemctl start lyric-web`，确认 Python 进程和 chromium 均启动

---

## 迁移路线（从双进程到单进程）

### 阶段一：并行共存

- 实现 `web` 模式，同时保留 `ble` + `ui` 模式
- 在开发板上同时部署两套服务（但不同时运行），对比效果
- 验证 BLE 稳定性不受影响（同一份 `ble_server.py`）

### 阶段二：切换到 Web 模式

- 确认 Web 模式稳定后，停用 `lyric-ble` + `lyric-ui`，启用 `lyric-web`
- 保留旧服务文件，可随时回退

### 阶段三：清理（可选）

- 确认无问题后，移除 `ui` 模式相关代码（`display.py`、`pygame` 依赖）
- 删除 `utils/ipc.py`（不再需要进程间通信）
- 删除 `lyric-ble.service` 和 `lyric-ui.service`

---

## 注意事项

- **chromium 依赖**：目标 ARM 板需要预装 `chromium-browser` 或 `chromium`。树莓派 OS 和 Ubuntu 均自带，精简系统需手动安装：`apt install chromium-browser`
- **GPU 兼容性**：部分 ARM 板 GPU 驱动有 bug，chromium `--disable-gpu` 标志可避免渲染崩溃。如 GPU 正常可移除此标志以获得更好性能
- **安全考量**：`host` 默认 `127.0.0.1`（仅本地访问）。如需远程访问改为 `0.0.0.0`，但 Web 服务器无认证，仅在可信局域网内开放
- **内存对比**：Pygame 模式约 30MB，Web 模式约 50MB（Python）+ 100MB（chromium）= 150MB。目标板需有足够内存
- **aiohttp PyInstaller 兼容**：aiohttp 的 C 扩展（HTTP parser）在 PyInstaller 中通常能自动检测，但建议在 `hiddenimports` 中显式声明
- **asyncio 事件循环共享**：BLE 回调来自 D-Bus 线程，通过 `asyncio.run_coroutine_threadsafe` 调度到主事件循环执行 WebSocket 广播，与现有 BLE 进程的做法一致
