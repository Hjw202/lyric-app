# 歌词蓝牙音箱 - 技术方案汇总

---

## 方案 1：Python + Pygame（当前方案）✅ 已实现

```
BLE进程 (bluez-peripheral + dbus-next)
  ↕ Unix Socket
UI进程 (Pygame 全屏渲染)
  ↕ pulsectl
PulseAudio 音效控制
```

| 项 | 值 |
|---|---|
| BLE 外设 | `bluez-peripheral` (Python, D-Bus, 成熟稳定) |
| UI | Pygame SDL2 (基础文字渲染) |
| 包体积 | ~20MB |
| 内存占用 | ~30MB |
| 跨平台 | ❌ 仅 Linux |
| 状态 | ✅ 已完成 |

---

## 方案 2：Electron + @stoprocent/bleno

```
主进程 (Node.js: @stoprocent/bleno BLE + child_process 调 pactl)
  ↕ Electron IPC
渲染进程 (WebView: CSS/HTML 歌词动画)
```

| 项 | 值 |
|---|---|
| BLE 外设 | `@stoprocent/bleno` (Node.js, HCI socket) |
| UI | WebView (CSS 动画、任意字体、丰富效果) |
| 包体积 | ~120MB |
| 内存占用 | ~200MB |
| 跨平台 | ✅ Win/Mac/Linux |
| 状态 | ⚠️ 需验证 bleno 在目标板子的稳定性 |

---

## 方案 3：Electron + C++ N-API addon（D-Bus）

```
主进程 (Node.js)
  ↕ N-API
C++ addon → D-Bus → bluetoothd (BlueZ)
  ↕ Electron IPC
渲染进程 (WebView)
```

| 项 | 值 |
|---|---|
| BLE 外设 | 自研 C++ addon，走 D-Bus（和 Python 方案同底层） |
| UI | WebView |
| 包体积 | ~120MB + addon 几百KB |
| 内存占用 | ~200MB |
| 跨平台 | ✅ (BLE addon 需按平台适配) |
| 状态 | ⚠️ 开发成本较高，但最稳定 |

---

## 方案 4：Electron + Rust napi-rs（btleplug）

```
主进程 (Node.js)
  ↕ napi-rs
Rust (btleplug → D-Bus → bluetoothd)
  ↕ Electron IPC
渲染进程 (WebView)
```

| 项 | 值 |
|---|---|
| BLE 外设 | Rust `btleplug` crate (D-Bus, 内存安全) |
| UI | WebView |
| 包体积 | ~120MB + Rust lib 几MB |
| 内存占用 | ~200MB |
| 跨平台 | ✅ (btleplug 支持多平台) |
| 状态 | ⚠️ 开发成本中等，Rust 交叉编译到 ARM64 方便 |

---

## 方案 5：Python 后端 + Web 前端（轻量混合）

```
Python BLE进程 (bluez-peripheral)
  ↕ WebSocket
轻量 Web 服务器 (Flask/FastAPI)
  ↕ 浏览器打开 (chromium-browser --kiosk)
Web UI (HTML/CSS/JS 歌词)
```

| 项 | 值 |
|---|---|
| BLE 外设 | Python `bluez-peripheral`（现有代码复用） |
| UI | 浏览器 WebView（CSS 动画） |
| 包体积 | ~20MB Python + 浏览器用系统自带的 |
| 内存占用 | ~50MB Python + ~100MB 浏览器 |
| 跨平台 | ❌ 仅 Linux |
| 状态 | ⚠️ 改动最小，UI 效果提升大 |

---

## 方案 6：Go + Fyne / Wails

```
Go (go-ble BLE库 + Fyne/Wails UI)
单二进制文件
```

| 项 | 值 |
|---|---|
| BLE 外设 | `go-ble/ble` (Go 原生) |
| UI | Fyne (原生) 或 Wails (WebView) |
| 包体积 | ~15-30MB |
| 内存占用 | ~30-50MB |
| 跨平台 | ✅ |
| 状态 | ⚠️ 完全重写，Go BLE 库 Peripheral 模式支持有限 |

---

## 横向对比

| 方案 | BLE 稳定性 | UI 效果 | 包体积 | 内存 | 开发成本 | 推荐度 |
|---|---|---|---|---|---|---|
| ① Python+Pygame | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ✅ 已完成 | 当前 |
| ② Electron+bleno | ⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 中 | ⭐⭐⭐ |
| ③ Electron+C++ | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 高 | ⭐⭐ |
| ④ Electron+Rust | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ | ⭐⭐ | ⭐⭐ | 中高 | ⭐⭐⭐ |
| ⑤ Python+Web | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐ | 低 | ⭐⭐⭐⭐ |
| ⑥ Go | ⭐⭐⭐ | ⭐⭐⭐ | ⭐⭐⭐⭐ | ⭐⭐⭐⭐ | 高（重写） | ⭐⭐ |

---

## 推荐

**如果想改善 UI**：方案 5（Python+Web）改动最小，BLE 代码完全复用，UI 用 CSS 动画效果好很多。

**如果想全面重写**：方案 4（Electron+Rust）是最平衡的选择——Rust BLE 稳定且交叉编译方便，Electron UI 效果最好。
