# 歌词音箱 v2.0 优化计划

> 目标：在保持 Python 后端 + D-Bus/AVRCP 架构不变的前提下，全面升级前端体验和功能扩展。
>
> 创建日期：2026-07-09
>
> 状态：🟡 待执行

---

## 总览

| 模块 | 优先级 | 复杂度 | 预估工时 | 依赖 |
|------|--------|--------|----------|------|
| 1. Vue 3 前端重写 | P0 | 中 | 3-4 天 | 无 |
| 2. GSAP 动画升级 | P1 | 低 | 2-3 天 | 依赖模块 1 |
| 3. 手机远程控制页 | P1 | 中 | 3-4 天 | 依赖模块 1 |
| 4. 多源歌词 API | P2 | 中 | 2-3 天 | 无 |

**原则**：后端（Python）零改动或最小改动，所有变化集中在 `web/` 目录和 `config/config.json`。

---

## 模块 1：Vue 3 前端重写

### 1.1 背景

当前 `web/` 目录是手写原生 JS（[app.js](web/app.js) 182 行），功能可用但：
- 无组件化，扩展困难（加远程控制页面需要大量 if/else）
- 无状态管理，歌词/样式/连接状态散落在全局变量
- 无构建工具，无法使用 TypeScript / 组件库

### 1.2 技术选型

| 项 | 选择 | 理由 |
|----|------|------|
| 框架 | **Vue 3** + Composition API | 轻量、学习成本低、适合嵌入式场景 |
| 构建 | **Vite** | 极速 HMR，构建产物小 |
| 状态 | **Pinia** | Vue 官方推荐，轻量 |
| 路由 | **Vue Router** | 远程控制页需要多页面 |
| 样式 | **UnoCSS** 或手写 CSS 变量 | 保持现有 CSS 变量体系，兼容后端 style 推送 |
| TypeScript | **可选启用** | 建议启用，WebSocket 消息类型安全 |

### 1.3 目录结构

```
web/                          # 旧文件保留备份 → web-legacy/
├── src/
│   ├── main.ts               # 入口
│   ├── App.vue               # 根组件
│   ├── router/
│   │   └── index.ts          # 路由：/ → 大屏显示，/remote → 远程控制
│   ├── stores/
│   │   ├── lyrics.ts         # 歌词状态：lines, currentIndex, song
│   │   ├── websocket.ts      # WS 连接管理：connect/disconnect/reconnect
│   │   └── style.ts          # 样式状态：颜色、字号等（兼容后端推送）
│   ├── composables/
│   │   └── useWebSocket.ts   # WebSocket hook（指数退避重连、ping/pong）
│   ├── views/
│   │   ├── LyricDisplay.vue  # 大屏歌词显示（对应现有功能）
│   │   └── RemoteControl.vue # 手机远程控制页（模块 3）
│   ├── components/
│   │   ├── LyricLine.vue     # 单行歌词组件（接收 current/prev/next/near 状态）
│   │   ├── SongInfo.vue      # 顶部歌曲信息
│   │   ├── ConnectionStatus.vue # 连接状态遮罩
│   │   └── StylePanel.vue    # 样式调节面板（远程控制用）
│   └── types/
│       └── ws.ts             # WebSocket 消息类型定义
├── index.html                # Vite 入口 HTML
├── vite.config.ts            # 构建配置：base → './'，输出到 dist/
├── package.json
└── tsconfig.json
```

### 1.4 WebSocket 协议类型定义

```typescript
// types/ws.ts
interface SongMessage {
  type: 'song'
  title: string
  artist: string
}

interface LyricsMessage {
  type: 'lyrics'
  lines: string[]
}

interface LineMessage {
  type: 'line'
  index: number
}

interface StyleMessage {
  type: 'style'
  data: StyleData
}

interface PingMessage { type: 'ping' }
interface PongMessage { type: 'pong' }

type ServerMessage = SongMessage | LyricsMessage | LineMessage | StyleMessage | PingMessage

// 客户端上行命令（后端 cmd_handler 已支持）
interface StyleCommand {
  cmd: 'style'
  color?: [number, number, number] | string
  bg_color?: [number, number, number] | string
  font_size?: number
  line_spacing?: number
  padding?: number
}

interface EffectCommand {
  cmd: 'effect'
  name: string
}

interface VolumeCommand {
  cmd: 'volume'
  level: number
}

type ClientCommand = StyleCommand | EffectCommand | VolumeCommand
```

### 1.5 后端兼容性

**后端零改动**。关键兼容点：

| 后端行为 | 前端适配 |
|----------|---------|
| `broadcast_style()` 推送 CSS 变量 | Pinia style store 监听 → 动态设置 `document.documentElement.style` |
| `broadcast_line()` 推送索引 | lyrics store 更新 `currentIndex` |
| `broadcast_lyrics()` 推送全文 | lyrics store 替换 `lines` 数组 |
| 上行 `{"cmd":"style",...}` | RemoteControl 页通过同一个 WS 连接发送 |
| ping/pong 心跳 | useWebSocket composable 自动回复 pong |

### 1.6 构建输出

```typescript
// vite.config.ts 关键配置
export default defineConfig({
  base: './',  // 相对路径，适配 PyInstaller 打包
  build: {
    outDir: '../web-dist',  // 输出到项目根的 web-dist/
    emptyOutDir: true,
  },
  server: {
    proxy: {
      '/ws': 'ws://127.0.0.1:8080',  // 开发时代理 WS
    }
  }
})
```

**部署方式变更**：

```
当前：Python 直接服务 web/ 目录的静态文件
改为：Python 服务 web-dist/（Vite 构建产物），web/ 仅保留源码
```

修改 [web_server.py:48-49](modules/web_server.py#L48-L49) 中的路径优先级：

```python
# 优先使用构建产物，回退到源码目录
for d in ['web-dist', 'web']:
    candidate = root / d
    if (candidate / 'index.html').exists():
        web_dir = candidate
        break
```

### 1.7 实现步骤

1. 初始化 Vue 3 + Vite 项目，配置 TypeScript
2. 实现 `useWebSocket` composable（复用现有重连逻辑）
3. 实现 Pinia stores（lyrics, websocket, style）
4. 重写 `LyricDisplay.vue`（等价现有 `index.html` + `app.js` + `style.css`）
5. 实现 `LyricLine.vue` 组件，保持现有 CSS 类名体系
6. 修改 `web_server.py` 静态文件路径
7. 验证：大屏显示效果与现有一致

---

## 模块 2：GSAP 动画升级

### 2.1 背景

当前动画完全依赖 CSS transitions（[style.css:68-72](web/style.css#L68-L72)）：
- 行切换只有 opacity + transform 过渡
- 滚动用原生 `scrollIntoView({ behavior: 'smooth' })`，在大屏上不够丝滑
- 无入场/退场动画，歌词切换显得生硬

### 2.2 动画方案

| 效果 | 当前 | 升级后 |
|------|------|--------|
| 行高亮切换 | CSS transition 0.4s | GSAP timeline：当前行缩放+发光，邻近行渐变 |
| 滚动 | `scrollIntoView smooth` | GSAP `ScrollToPlugin` 精确滚动到中心 |
| 歌曲切换 | 无过渡 | 整屏淡出 → 歌词逐行入场（stagger） |
| 无歌词状态 | 静态文字 | 呼吸灯动画 + 粒子背景 |
| 发光效果 | CSS text-shadow | GSAP 动态脉冲 + 颜色呼吸 |

### 2.3 GSAP 集成

```typescript
// composables/useLyricAnimation.ts
import gsap from 'gsap'
import { ScrollToPlugin } from 'gsap/ScrollToPlugin'

gsap.registerPlugin(ScrollToPlugin)

export function useLyricAnimation(lineRefs: Ref<HTMLElement[]>) {
  // 行切换动画
  function animateToLine(index: number) {
    const lines = lineRefs.value
    const tl = gsap.timeline()

    // 当前行：放大 + 发光脉冲
    tl.to(lines[index], {
      scale: 1,
      opacity: 1,
      textShadow: '0 0 30px var(--text-color)',
      duration: 0.4,
      ease: 'power2.out',
    })

    // 邻近行：淡出
    lines.forEach((el, i) => {
      if (i !== index) {
        const dist = Math.abs(i - index)
        gsap.to(el, {
          opacity: dist <= 1 ? 0.35 : 0.12,
          scale: dist <= 1 ? 0.95 : 0.9,
          duration: 0.4,
          ease: 'power2.out',
        })
      }
    })

    // 精确滚动
    gsap.to('#lyrics', {
      scrollTo: { y: lines[index], offsetY: window.innerHeight / 2 - 40 },
      duration: 0.6,
      ease: 'power2.inOut',
    })
  }

  // 歌曲切换：整屏淡出 + 新歌词 stagger 入场
  function animateSongChange(callback: () => void) {
    const tl = gsap.timeline()
    tl.to('#lyrics', { opacity: 0, duration: 0.3 })
      .call(callback)  // 替换歌词内容
      .fromTo('.lyric-line',
        { opacity: 0, y: 20 },
        { opacity: 1, y: 0, duration: 0.4, stagger: 0.03, ease: 'power2.out' }
      )
  }

  return { animateToLine, animateSongChange }
}
```

### 2.4 性能考量

- GSAP 在 ARM + Chromium 上运行良好（纯 CSS transform/opacity，触发 GPU 合成层）
- 避免动画 `color` / `background-color`（触发重绘），用 CSS 变量 + `opacity` 代替
- 大量歌词行（>200）时只对可见区域 ±5 行做动画，其余保持静态

### 2.5 实现步骤

1. 安装 `gsap`，创建 `useLyricAnimation` composable
2. 替换 `LyricLine.vue` 的 CSS transition 为 GSAP 调用
3. 替换 `scrollIntoView` 为 `ScrollToPlugin`
4. 添加歌曲切换过渡动画
5. 测试 ARM 设备上的帧率（目标 60fps）

---

## 模块 3：手机远程控制页

### 3.1 背景

当前控制方式：
- 修改 `config.json` → watchdog 热重载
- 或通过 WebSocket 发送 JSON 命令（但无 UI）

用户需要一个手机端页面，通过浏览器访问 `http://<板子IP>:8080/remote`，实时控制显示效果。

### 3.2 功能设计

```
┌──────────────────────────────────┐
│  🎵 Lyric Speaker Remote   🔵   │  ← 连接状态指示
├──────────────────────────────────┤
│                                  │
│  🎵 周杰伦 - 晴天                │  ← 当前歌曲（只读）
│                                  │
├──────────────────────────────────┤
│                                  │
│  字号  ────●──────────  48px    │  ← 滑块
│  行距  ──────●────────  10px    │
│  内边距 ───●──────────  40px    │
│                                  │
├──────────────────────────────────┤
│                                  │
│  主题色    🔴 🟢 🔵 🟡 ⚪       │  ← 快捷色板
│  背景色    ⚫ 🔴 🟣 🔵           │
│                                  │
├──────────────────────────────────┤
│                                  │
│  音量  ──────────●────  70%     │
│                                  │
│  音效  [摇滚] [流行] [古典] [平坦]│  ← 按钮组
│                                  │
└──────────────────────────────────┘
```

### 3.3 路由与页面

```
/           → LyricDisplay.vue   （大屏歌词，现有功能）
/remote     → RemoteControl.vue  （手机控制页）
```

### 3.4 后端改动

**WebSocket 连接复用**：RemoteControl 页连接同一个 `ws://<IP>:8080/ws`，通过现有 `on_command` 回调处理命令。

**需要新增的上行消息类型**：

```typescript
// 查询当前状态（连接时自动发送）
interface QueryStateCommand {
  cmd: 'query_state'
}

// 后端新增广播
interface StateMessage {
  type: 'state'
  song: { title: string; artist: string } | null
  lyrics_count: number
  current_line: number
  style: StyleData
  volume: number
  effect: string
}
```

**后端改动清单**（`modules/` 下，极小改动）：

| 文件 | 改动 |
|------|------|
| [cmd_handler.py](modules/cmd_handler.py) | 新增 `_handle_query_state` 方法，返回当前状态 |
| [web_server.py](modules/web_server.py) | 新增 `broadcast_state()` 方法 |
| [lyric_app.py](lyric_app.py) | 在 `on_browser_command` 中处理 `query_state` |

### 3.5 RemoteControl.vue 核心逻辑

```typescript
// 伪代码
const ws = useWebSocket()  // 复用同一个 WS 连接

// 连接后查询状态
ws.onConnected(() => {
  ws.send({ cmd: 'query_state' })
})

// 实时同步：滑块拖动时节流发送
const sendStyle = throttle((style) => {
  ws.send({ cmd: 'style', ...style })
}, 200)

// 音效切换：点击即发送
function setEffect(name: string) {
  ws.send({ cmd: 'effect', name })
}

// 音量调节
function setVolume(level: number) {
  ws.send({ cmd: 'volume', level })
}
```

### 3.6 实现步骤

1. 后端：`cmd_handler.py` 新增 `query_state` 命令处理
2. 后端：`web_server.py` 新增 `broadcast_state()` + 状态快照 API
3. 前端：Vue Router 添加 `/remote` 路由
4. 前端：实现 `RemoteControl.vue`（滑块、色板、按钮）
5. 前端：样式表单绑定 → WS 命令发送（throttle 200ms）
6. 测试：手机浏览器访问，实时调节数值，大屏同步变化

---

## 模块 4：多源歌词 API

### 4.1 背景

当前只有网易云音乐 API（[lyrics_fetcher.py:28](modules/lyrics_fetcher.py#L28)），问题：
- 网易云部分歌曲无歌词或歌词质量差
- 不同音乐平台的版权歌曲在网易云搜不到
- 需要备选源提高覆盖率

### 4.2 架构设计

```
LyricsFetcher（改造为路由器）
  ├── NeteaseProvider      ← 现有代码迁移
  ├── QQMusicProvider      ← 新增
  ├── KugouProvider        ← 新增
  └── LocalLrcProvider     ← 新增：本地 .lrc 文件查找
```

### 4.3 Provider 接口

```python
# modules/lyrics/providers/base.py
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional

@dataclass
class LyricsResult:
    lrc_text: str           # LRC 格式原文
    source: str             # 来源标识：netease / qq / kugou / local
    song_id: str = ''       # 源站歌曲 ID
    matched_title: str = '' # 实际匹配的歌名
    matched_artist: str = '' # 实际匹配的歌手

class LyricsProvider(ABC):
    """歌词提供者接口"""

    @property
    @abstractmethod
    def name(self) -> str:
        """提供者名称"""
        ...

    @abstractmethod
    async def search_and_fetch(self, title: str, artist: str) -> Optional[LyricsResult]:
        """搜索并获取歌词，返回 None 表示未找到"""
        ...

    async def close(self):
        """释放资源"""
        pass
```

### 4.4 各 Provider 实现

#### NeteaseProvider（迁移现有代码）

将 [lyrics_fetcher.py](modules/lyrics_fetcher.py) 中的搜索 + 获取逻辑迁移到 `providers/netease.py`，接口不变。

#### QQMusicProvider

```python
# modules/lyrics/providers/qq_music.py
class QQMusicProvider(LyricsProvider):
    """
    QQ 音乐歌词 API（非官方）
    搜索：https://c.y.qq.com/soso/fcgi-bin/client_search_cp?w={query}&format=json
    歌词：https://c.y.qq.com/lyric/fcgi-bin/fcg_query_lyric_new.fcg?songmid={mid}&format=json
    注意：歌词接口需要 Referer 头：https://y.qq.com
    """
    name = 'qq'

    async def search_and_fetch(self, title: str, artist: str) -> Optional[LyricsResult]:
        # 1. 搜索歌曲获取 songmid
        # 2. 获取歌词（base64 编码，需解码）
        # 3. 转换为标准 LRC 格式
        ...
```

#### KugouProvider

```python
# modules/lyrics/providers/kugou.py
class KugouProvider(LyricsProvider):
    """
    酷狗音乐歌词 API（非官方）
    搜索：https://mobilecdn.kugou.com/api/v3/search/song?keyword={query}&page=1&pagesize=5
    歌词：https://krcs.kugou.com/search?ver=1&man=yes&client=mobi&keyword={title}&duration={ms}&hash={hash}
    """
    name = 'kugou'

    async def search_and_fetch(self, title: str, artist: str) -> Optional[LyricsResult]:
        # 1. 搜索歌曲获取 hash
        # 2. 获取歌词候选列表
        # 3. 下载最佳匹配的 LRC
        ...
```

#### LocalLrcProvider

```python
# modules/lyrics/providers/local.py
class LocalLrcProvider(LyricsProvider):
    """
    本地 .lrc 文件查找
    搜索路径：/var/cache/lyric-app/lrc/, /opt/lyric-app/lrc/
    文件命名：{artist} - {title}.lrc
    """
    name = 'local'

    async def search_and_fetch(self, title: str, artist: str) -> Optional[LyricsResult]:
        # 按优先级搜索本地 .lrc 文件
        ...
```

### 4.5 路由策略

```python
# modules/lyrics_fetcher.py（改造后）
class LyricsFetcher:
    def __init__(self, config: dict):
        providers_config = config.get('lyrics', {}).get('providers', [])
        self.providers: List[LyricsProvider] = []
        self.cache = LyricsCache(config)  # 缓存逻辑抽取

        # 按配置顺序初始化 Provider
        for p in providers_config:
            provider = create_provider(p)
            if provider:
                self.providers.append(provider)

        # 默认顺序：local → netease → qq → kugou
        if not self.providers:
            self.providers = [
                LocalLrcProvider(),
                NeteaseProvider(),
                QQMusicProvider(),
                KugouProvider(),
            ]

    async def fetch_lyrics(self, title: str, artist: str) -> Optional[str]:
        # 1. 查缓存
        cached = self.cache.get(title, artist)
        if cached:
            return cached

        # 2. 按优先级遍历 Provider
        for provider in self.providers:
            try:
                result = await provider.search_and_fetch(title, artist)
                if result:
                    self.cache.set(title, artist, result.lrc_text, result.source)
                    logger.info(f"歌词来源: {provider.name} | {result.matched_title} - {result.matched_artist}")
                    return result.lrc_text
            except Exception as e:
                logger.warning(f"{provider.name} 查询失败: {e}")
                continue

        return None
```

### 4.6 配置扩展

```json
{
  "lyrics": {
    "providers": [
      { "name": "local", "enabled": true, "paths": ["/var/cache/lyric-app/lrc"] },
      { "name": "netease", "enabled": true },
      { "name": "qq", "enabled": true },
      { "name": "kugou", "enabled": true }
    ],
    "cache_dir": "/var/cache/lyric-app/lyrics",
    "cache_ttl": 2592000,
    "request_timeout": 10
  }
}
```

### 4.7 实现步骤

1. 创建 `modules/lyrics/` 包，定义 `LyricsProvider` 基类
2. 迁移现有网易云逻辑到 `providers/netease.py`
3. 实现 `providers/qq_music.py`（QQ 音乐）
4. 实现 `providers/kugou.py`（酷狗）
5. 实现 `providers/local.py`（本地 .lrc）
6. 改造 `LyricsFetcher` 为路由器模式
7. 更新 `config.json` 添加 providers 配置
8. 测试：同一首歌从不同源获取，验证覆盖率提升

---

## 实施顺序

```
Phase 1（基础）     模块 1: Vue 3 前端重写
                    ↓
Phase 2（增强）     模块 2: GSAP 动画  +  模块 3: 远程控制页（可并行）
                    ↓
Phase 3（扩展）     模块 4: 多源歌词 API（独立于前端，可随时做）
```

### Phase 1 验收标准

- [ ] `npm run build` 产出 `web-dist/` 目录
- [ ] 浏览器访问 `http://localhost:8080` 显示歌词（功能等价现有）
- [ ] WebSocket 连接、心跳、自动重连正常
- [ ] 样式推送（后端 → 前端）正常
- [ ] Chromium kiosk 模式正常全屏

### Phase 2 验收标准

- [ ] 歌词行切换有 GSAP 动画，60fps 无掉帧
- [ ] 歌曲切换有整屏过渡动画
- [ ] 手机访问 `http://<IP>:8080/remote` 显示控制面板
- [ ] 调节滑块实时改变大屏显示效果
- [ ] 切换音效/音量实时生效

### Phase 3 验收标准

- [ ] 网易云搜不到的歌，自动 fallback 到 QQ/酷狗
- [ ] 缓存命中时不重复请求
- [ ] 日志显示每次歌词的实际来源
- [ ] 配置可禁用/启用特定 Provider

---

## 风险与注意事项

| 风险 | 影响 | 缓解措施 |
|------|------|----------|
| QQ/酷狗 API 为非官方，可能变动 | 歌词获取失败 | Provider 接口隔离，单源故障不影响其他源；定期监控 |
| GSAP 在低端 ARM 设备卡顿 | 动画掉帧 | 降级方案：检测 FPS < 30 时回退到 CSS transition |
| Vite 构建产物未部署到板子 | 大屏无显示 | install.sh 中添加 `npm run build` 步骤，或 CI 预构建 |
| 远程控制页被陌生人访问 | 样式被乱改 | 可选：添加简单 PIN 码或局域网 IP 白名单 |
| WebSocket 连接数过多 | 内存/CPU 占用 | 现有广播逻辑已处理，远程控制页只发少量命令，影响可忽略 |
