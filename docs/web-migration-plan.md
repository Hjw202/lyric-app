# Python + Web 前端改造计划

## 架构变更

```
改造前（双进程）:
  BLE进程 (IPC Server) ←──Unix Socket──→ UI进程 (Pygame)

改造后（单进程）:
  主进程:
    ├─ BLE peripheral (bluez-peripheral) ← 不变
    ├─ aiohttp Web Server (HTTP + WebSocket)
    │   ├─ GET /          → 返回歌词页面 HTML
    │   ├─ GET /ws        → WebSocket 推送歌词/命令
    │   └─ GET /static/*  → CSS/JS 静态文件
    ├─ AudioEffects (pulsectl) ← 不变
    └─ CommandHandler ← 适配：style 命令通过 WebSocket 推送到浏览器

  Browser (chromium --kiosk http://localhost:8080)
    └─ Web UI: WebSocket 客户端 + 逐字高亮歌词渲染
```

---

## 改动文件清单

### 新增文件

| 文件 | 说明 |
|---|---|
| `web/index.html` | 歌词显示页面（全屏黑底，居中歌词，逐字高亮） |
| `web/style.css` | 样式：全屏布局、字体、过渡动画、CSS 变量驱动主题 |
| `web/app.js` | WebSocket 客户端 + 逐字高亮渲染逻辑 |
| `web_server.py` | aiohttp Web 服务器（HTTP 静态文件 + WebSocket 广播） |
| `systemd/lyric-web.service` | 单进程 systemd 服务 |

### 修改文件

| 文件 | 改动内容 |
|---|---|
| `lyric_app.py` | 新增 `web` 模式，集成 web_server，移除 Pygame UI 主循环 |
| `modules/cmd_handler.py` | style 命令改为返回样式 dict，由 web_server 通过 WebSocket 推送 |
| `config/config.json` | display 部分改为 web 配置（port、host） |
| `requirements.txt` | 移除 pygame，新增 aiohttp |
| `Dockerfile.arm64` | 移除 SDL2 依赖，新增 aiohttp |
| `CLAUDE.md` | 更新架构文档 |

### 不改动（完全复用）

| 文件 | 说明 |
|---|---|
| `modules/ble_server.py` | BLE 外设，完全不变 |
| `modules/audio_effects.py` | PulseAudio 控制，完全不变 |
| `modules/config_manager.py` | 配置热重载，完全不变 |
| `utils/logger.py` | 日志系统，完全不变 |
| `utils/ipc.py` | 单进程不再需要，但保留文件不删除 |

---

## 实现步骤

### Step 1: 新增 Web 前端文件

**`web/index.html`** — 歌词全屏页面
- 全屏黑色背景，歌词居中显示
- 引入 style.css 和 app.js
- 结构：`<div id="lyrics">` 包含逐字 `<span>` 元素

**`web/style.css`** — 样式
- CSS 变量 `--text-color`, `--bg-color`, `--font-size` 驱动主题（支持 JSON 命令动态修改）
- 逐字高亮：`.char.active` 类用亮色，其余用暗色，带平滑 transition
- 全屏无滚动条，`overflow: hidden`
- 字体：优先 wqy-microhei, Noto Sans CJK

**`web/app.js`** — 前端逻辑
- WebSocket 连接 `ws://host:8080/ws`
- 收到歌词文本 → 逐字拆分为 `<span>` 插入 DOM
- 收到 style 命令 → 更新 CSS 变量
- 收到 effect/volume 命令 → 忽略（后端直接处理）
- 逐字高亮动画：定时器按字高亮（类似卡拉OK），速度可配置
- 断线自动重连

### Step 2: 新增 Web 服务器

**`web_server.py`**

```python
class WebServer:
    def __init__(self, config, cmd_handler, audio_effects):
        self.app = web.Application()
        self.app.router.add_get('/', self.index_handler)
        self.app.router.add_get('/ws', self.ws_handler)
        self.app.router.add_static('/static/', path='web/')
        self.websockets = set()

    async def broadcast_lyric(self, text):
        """向所有 WebSocket 客户端发送歌词"""
        ...

    async def broadcast_command(self, cmd_dict):
        """向所有 WebSocket 客户端发送样式/命令"""
        ...

    async def ws_handler(self, request):
        """WebSocket 连接处理，接收客户端命令转发给 cmd_handler"""
        ...
```

### Step 3: 修改 lyric_app.py

- 新增 `run_web(config_path)` 函数，替代 `run_ble` + `run_ui`
- 创建 BLE server、Web server、AudioEffects、CommandHandler
- BLE 回调 → `web_server.broadcast_lyric()` / `web_server.broadcast_command()`
- 移除 IPC 相关代码（单进程不需要）
- CLI 支持：`lyric_app.py web` 启动单进程模式
- 保留 `lyric_app.py ble` 和 `lyric_app.py ui` 向后兼容（但不再推荐）

### Step 4: 修改 cmd_handler.py

- `process_command()` 改为返回处理结果 dict 而非直接调 display
- style 命令返回 `{"type": "style", "data": {...}}`
- effect/volume 命令仍然直接调 audio_effects（无需推送到浏览器）

### Step 5: 配置和部署

**config.json** 新增 web 配置：

```json
{
  "web": {
    "host": "0.0.0.0",
    "port": 8080,
    "auto_launch_browser": true
  },
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

**chromium 自启动** systemd 服务或 xdg autostart：

```bash
chromium-browser --kiosk --noerrdialogs --disable-infobars http://localhost:8080
```

### Step 6: 更新构建

- `requirements.txt`: 移除 pygame，新增 aiohttp
- `Dockerfile.arm64`: 移除 SDL2 相关，新增 aiohttp
- `CLAUDE.md`: 更新架构图和运行说明

---

## 数据流

```
手机 App
  │ BLE Write (歌词文本 / JSON 命令)
  ▼
BLEServer (bluez-peripheral)
  │ decode UTF-8
  │ on_lyric(text) / on_command(text)
  ▼
WebServer.broadcast_lyric(text)
  │ WebSocket 推送
  ▼
浏览器 (chromium --kiosk)
  ├─ 收到歌词 → 逐字拆分 → <span> 逐个高亮动画
  └─ 收到 style 命令 → 更新 CSS 变量（颜色/字号/背景）
```

---

## 验证方案

1. **本地测试**：`python lyric_app.py web`，浏览器打开 `http://localhost:8080` 确认页面加载
2. **WebSocket 测试**：用 wscat 或浏览器 DevTools 连接 `/ws`，发送歌词文本确认显示
3. **逐字高亮**：发送歌词后观察逐字高亮动画效果
4. **命令测试**：发送 `{"cmd":"style","color":[255,0,0]}` 确认样式变化
5. **BLE 测试**：用手机 BLE 工具连接写入歌词，确认页面实时更新
6. **打包测试**：PyInstaller 打包后在板子上运行，确认 chromium --kiosk 自动打开
