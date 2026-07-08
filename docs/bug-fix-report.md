# 蓝牙歌词音箱项目 - Bug 检查与修复报告

## 概述

对 `lyric-app` 项目进行了全面的代码审查，重点排查了打包构建和 UI 进程相关的问题。共发现 **12 个问题**，其中 **6 个严重**（直接导致 UI 进程崩溃或功能异常），**4 个中等**，**2 个轻微**。已全部修复。

---

## 严重问题（已修复）

### 1. PyInstaller 缺少 hidden imports — 打包后运行崩溃

**文件**: `lyric_app.spec`

**问题**: `hiddenimports` 为空数组。`watchdog` 库使用动态导入选择平台后端（Linux 上用 `InotifyObserver`），PyInstaller 无法自动检测这些动态加载的模块。`dbus_next` 和 `bluez_peripheral` 也可能存在动态导入。打包后的二进制文件在运行时会因 `ModuleNotFoundError` 崩溃。

**修复**: 在 `lyric_app.spec` 的 `hiddenimports` 中添加了 watchdog 观察者后端、dbus_next 核心模块和 bluez_peripheral 所有子模块。

### 2. Docker 构建不使用 spec 文件 — hidden imports 配置被忽略

**文件**: `Dockerfile.arm64`, `Dockerfile.armhf`

**问题**: Dockerfile 中运行的是 `pyinstaller --onefile --add-data "config/config.json:config" lyric_app.py`（命令行方式），这会让 PyInstaller 自动生成新的 spec 文件，**完全忽略**项目中的 `lyric_app.spec`。即使修复了 spec 文件中的 hidden imports，Docker 构建出的产物仍然会缺失这些模块。

**修复**: 改为 `pyinstaller lyric_app.spec`，让构建过程使用项目中的 spec 文件配置。同时添加了 `procps` 系统依赖（提供 `pgrep` 命令，`display.py` 中的 `_check_x11_running` 依赖它）。

### 3. PyInstaller 打包后配置文件路径错误

**文件**: `lyric_app.py` 第 44 行

**问题**: `load_config_path()` 中，PyInstaller 打包路径写的是 `bundle_dir / 'config.json'`（即 `_MEIPASS/config.json`），但 spec 文件的 `datas=[('config/config.json', 'config')]` 将配置文件放在了 `_MEIPASS/config/config.json`。路径不匹配导致打包后无法通过 `_MEIPASS` 找到内嵌配置。

虽然后续的 `Path(__file__).parent / 'config' / 'config.json'` 路径恰好能命中，但第一个路径是无效的。

**修复**: 改为 `bundle_dir / 'config' / 'config.json'`。

### 4. UI 进程缺少 SIGTERM 信号处理 — systemd 停止时无法清理

**文件**: `lyric_app.py` `run_ui()` 函数

**问题**: BLE 进程通过 `loop.add_signal_handler` 处理了 SIGTERM/SIGINT，但 UI 进程**没有任何信号处理**。当 systemd 执行 `systemctl stop lyric-ui` 时发送 SIGTERM，Python 默认行为是直接终止进程，**不会执行 `finally` 块**。这导致：

- `pygame.quit()` 不执行 → 可能残留显示状态
- `audio_effects.close()` 不执行 → PulseAudio 连接泄漏
- `cleanup_config_manager()` 不执行 → watchdog 观察线程泄漏
- IPC 客户端不正常断开 → 服务端可能仍认为客户端在线

**修复**: 在 UI 主循环前注册 `signal.signal(SIGTERM, ...)` 和 `signal.signal(SIGINT, ...)` 处理器，收到信号时设置 `display._running = False`，让主循环正常退出并执行 `finally` 块清理。

### 5. IPCClient 的 asyncio.Queue 在事件循环外创建 — 跨 loop 绑定

**文件**: `utils/ipc.py` `IPCClient.__init__`

**问题**: `self._send_queue = asyncio.Queue(maxsize=1000)` 在 `__init__` 中创建，此时主线程没有运行中的事件循环。随后 `IPCClient` 在另一个线程的独立事件循环中使用。在 Python 3.9 中，`asyncio.Queue` 在创建时会绑定当前事件循环，导致队列绑定到错误的 loop，后续在正确 loop 中使用时可能抛出 `RuntimeError: Future attached to a different loop`。

**修复**: 将 `asyncio.Queue` 的创建移到 `connect()` 方法中（在事件循环内创建），`__init__` 中设为 `None`。同时更新 `_send_loop` 和 `send` 方法处理队列为 None 的情况。

### 6. BLE 配置直接键访问 — KeyError 风险

**文件**: `modules/ble_server.py` `_run_ble_service()`

**问题**: 使用 `self.config['lyric_service_uuid']` 等直接键访问。如果配置文件缺少 `ble` 段或某个 UUID，会抛出未捕获的 `KeyError`，导致 BLE 服务崩溃。虽然 BLE 有自动重试机制，但每次重试都会立即失败，形成无效的重试循环。

**修复**: 改为 `self.config.get(...)` 加 `None` 检查，配置缺失时抛出带描述的 `ValueError`，日志会显示明确的错误原因。

---

## 中等问题（已修复）

### 7. .gitignore 忽略 spec 文件

**文件**: `.gitignore` 第 39 行

**问题**: `*.spec` 规则会忽略 `lyric_app.spec`，但该文件是打包配置，必须纳入版本控制。虽然文件可能已经通过 `git add -f` 被追踪，但新的修改可能被 git 忽略而不提示。

**修复**: 添加 `!lyric_app.spec` 例外规则。

### 8. systemd 服务文件重复 After 指令

**文件**: `systemd/lyric-ui.service`

**问题**: 文件中有两行 `After=`（第 3 行和第 5 行），虽然 systemd 会合并它们，但 `pulseaudio.service` 只在 `After` 中而未在 `Wants` 中声明，意味着如果 pulseaudio 未安装，UI 服务不会等待它但仍会尝试启动（行为正确但依赖关系不清晰）。

**修复**: 合并为单行 `After=lyric-ble.service network.target graphical.target pulseaudio.service`，并在 `Wants` 中添加 `pulseaudio.service`。

### 9. 日志文件路径不一致

**文件**: `config/config.json`, `lyric_app.py`

**问题**: 代码中日志默认路径是 `/tmp/lyric-ble.log` 和 `/tmp/lyric-ui.log`，但 `install.sh` 创建的日志目录是 `/var/log/lyric-app/`。`/tmp/` 在系统重启后会被清空，日志丢失。`config.json` 中也没有 `logging` 配置段。

**修复**: 在 `config.json` 中添加 `logging` 段，明确指定 `ble_file` 和 `ui_file` 路径为 `/var/log/lyric-app/`。更新 `lyric_app.py` 读取新的配置字段。

### 10. _render_text_cached 在锁外读取 self.style — 竞态条件

**文件**: `modules/display.py` `_render_text_cached()`

**问题**: `_render_text_cached` 通过 `self.style.get('font_size', 48)` 构建 cache key，但这个读取在 `_style_lock` 之外。如果 watchdog 配置监听线程同时修改 `self.style`（通过 `apply_style`），可能读到不一致的状态。虽然 Python 的 GIL 使单次 `dict.get` 原子化，但 cache key 可能与实际使用的字体不匹配。

**修复**: 将 `font_size` 的读取移到 `_render_frame` 的 `_style_lock` 内，作为参数传给 `_render_text_cached`。

---

## 轻微问题（已修复 / 已知限制）

### 11. UPX 压缩配置无效

**文件**: `lyric_app.spec`

**问题**: `upx=True` 但 Docker 镜像中未安装 UPX，PyInstaller 会静默跳过压缩。这不是 bug（不影响功能），但 `upx=True` 设置具有误导性。

**状态**: 保持现状，如需启用 UPX 可在 Dockerfile 中添加 `apt-get install upx-ucl`。

### 12. Display.main_loop() 是死代码

**文件**: `modules/display.py`

**问题**: `Display` 类有 `main_loop()` 方法，但 `run_ui()` 没有使用它，而是自己实现了主循环（因为需要处理 `data_queue`）。`main_loop()` 成为不会被调用的死代码。

**状态**: 保持现状，未来可重构为回调模式消除重复。

---

## 未修改但值得注意的事项

### CI 构建速度

GitHub Actions 在 x86 runner 上用 QEMU 模拟 ARM64 执行 PyInstaller，速度很慢（可能 10-30 分钟）。如果 CI 经常超时，可考虑：
- 使用原生 ARM64 runner（GitHub 已提供 `arm64` runner）
- 使用交叉编译工具链替代 QEMU 模拟

### 音效模块未完成实现

`audio_effects.py` 中 `set_effect` 方法的均衡器加载部分是 TODO 状态（第 105 行 `# TODO: 实际加载均衡器模块`），`_load_equalizer_module` 中参数是占位符 `???`。音效切换功能实际不会生效。

### 双队列冗余

歌词数据经过两次队列传递：`data_queue`（`run_ui` 中）→ `_lyric_queue`（`Display` 中）。功能正确但有冗余，未来可合并为单队列。

### Web 迁移计划

`docs/web-migration-plan.md` 中规划了 Python+Web 前端的迁移方案（用浏览器替代 pygame 渲染），目前仅为文档，未实施。
