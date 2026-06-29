# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Bluetooth lyric speaker app for Linux ARM boards. It receives lyrics from phone music apps (NetEase Cloud, QQ Music) via BLE and displays them fullscreen using Pygame, with audio effect control via PulseAudio. The final deliverable is a PyInstaller-packaged standalone executable — the target board does not need Python installed.

## Running from Source

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Start BLE service (one terminal)
python lyric_app.py ble

# Start UI display (another terminal)
python lyric_app.py ui
```

## Building

```bash
pyinstaller --onefile --add-data "config/config.json:config" lyric_app.py
# Output: dist/lyric_app
```

## Architecture

The app runs as **two separate processes** communicating via Unix Socket (`/tmp/lyric.sock`):

```
lyric-ble process  ←── Unix Socket (line protocol) ──→  lyric-ui process
│                                                       │
├─ BLE peripheral (bluez-peripheral + dbus-next)        ├─ Pygame fullscreen display
├─ Lyric characteristic (write)                         ├─ Command handler (JSON parsing)
├─ Control characteristic (write)                       ├─ Audio effects (pulsectl)
└─ IPC Server                                           └─ IPC Client (runs in daemon thread)
```

**Entry point**: `lyric_app.py` — takes `ble` or `ui` as CLI argument. Config is loaded from `config/config.json` (searched in project dir, `/etc/lyric-app/`, or cwd; PyInstaller bundle has its own path).

### Key module relationships

- `lyric_app.py` wires everything: creates `IPCServer`/`IPCClient`, instantiates `BLEServer`, `Display`, `AudioEffects`, `CommandHandler`
- BLE callbacks (`on_lyric`, `on_command`) broadcast data to all IPC clients via `IPCServer.broadcast()`
- UI process reads IPC data into a `queue.Queue` (thread-safe bridge from asyncio IPC thread to Pygame main thread), then tries `CommandHandler.process_command()` first; if it returns False, treats data as lyric text
- `CommandHandler` parses JSON with a `cmd` field: `style` → `Display.apply_style()`, `effect` → `AudioEffects.set_effect()`, `volume` → `AudioEffects.set_volume()`
- `ConfigManager` uses `watchdog` for hot-reload; BLE and UI processes register listeners to react to config changes at runtime

### BLE services

Two GATT services registered via `bluez-peripheral`:
- **Lyric service** (`0000FFE0-...`): characteristic accepts raw lyric text (Write/WriteWithoutResponse)
- **Control service** (`12345678-...`): characteristic accepts JSON commands (same Write flags)

### Display rendering

`Display` class manages Pygame with double-buffered hardware-accelerated fullscreen. Uses `TextCache` (LRU, max 200 entries) for rendered text surfaces. Supports dirty-rect updates when only lyrics change, full redraw on style change. Frame rate capped at 10fps. Font fallback: wqy-microhei → DroidSansFallback → NotoSansCJK → system default.

### IPC protocol

Line-based over Unix Domain Socket (`\n`-delimited). Each line is either:
- Plain text → treated as lyrics
- JSON string starting with `{` → parsed as command

`IPCServer` has heartbeat detection (30s interval) and client timeout (60s). `IPCClient` has exponential backoff reconnection (2s initial, 1.5x backoff, 30s max).

## Key Dependencies

- `bluez-peripheral` + `dbus-next` — BLE GATT peripheral via D-Bus
- `pygame` — fullscreen rendering (requires SDL2 system libs)
- `pulsectl` — PulseAudio volume/effect control
- `watchdog` — config file hot-reload
- `pyinstaller` — packaging

## System Requirements (target board)

BlueZ ≥ 5.50, PulseAudio, SDL2, D-Bus. User must be in `bluetooth` and `pulse-access` groups. Framebuffer (`/dev/fb0`) or X11 display.
