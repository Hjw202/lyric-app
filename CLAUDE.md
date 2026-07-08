# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

A Bluetooth lyric speaker app for Linux ARM boards (e.g., Raspberry Pi). The dev board acts as a Bluetooth speaker (A2DP sink) — phones play music to it directly via Bluetooth. The app reads the now-playing metadata via AVRCP, fetches LRC lyrics from the internet, and syncs them to the playback position with line-by-line highlighting on a fullscreen chromium kiosk display. The final deliverable is a PyInstaller-packaged standalone executable — the target board does not need Python installed.

## Running from Source

```bash
# Setup
python3 -m venv venv && source venv/bin/activate
pip install -r requirements.txt

# Run (single process: AVRCP + lyrics sync + web server)
python lyric_app.py web
# Then open http://localhost:8080 in a browser, or use:
# chromium-browser --kiosk --no-sandbox --disable-gpu http://localhost:8080
```

The board must be configured as a Bluetooth A2DP sink (BlueZ + PulseAudio/PipeWire). See install.sh for system requirements.

## Building

```bash
# Use the spec file (includes hidden imports for watchdog, dbus_next, aiohttp)
pyinstaller lyric_app.spec
# Output: dist/lyric_app
```

## Architecture

Single-process model:

```
lyric-web process (asyncio event loop):
  ├─ AVRCPController (D-Bus → BlueZ MediaPlayer1)
  │   ├─ Track property → on_track_changed → LyricsFetcher → parse_lrc → LyricSync
  │   ├─ Position property → on_position_changed → LyricSync.update_position()
  │   └─ Status property → on_status_changed → LyricSync.update_status()
  ├─ LyricsFetcher (aiohttp HTTP → 网易云 API)
  │   ├─ Search song by title+artist → song_id
  │   ├─ Fetch LRC by song_id
  │   └─ Memory + disk cache
  ├─ LyricSync (position ↔ LRC timestamp matching)
  │   ├─ Binary search: find line where time_ms <= position
  │   ├─ Local clock interpolation between AVRCP position reports
  │   └─ on_line_changed → WebServer.broadcast_line(index)
  ├─ WebServer (aiohttp)
  │   ├─ GET /    → web/index.html
  │   ├─ GET /ws  → WebSocket (song/lyrics/line/style push, ping/pong heartbeat)
  │   └─ GET /*   → static files (style.css, app.js)
  ├─ AudioEffects (pulsectl) — volume control
  └─ ConfigManager (watchdog hot-reload)

Browser (chromium --kiosk http://localhost:8080):
  └─ app.js: WebSocket client, line-by-line highlight with CSS transitions
```

**Entry point**: `lyric_app.py web` — starts AVRCP + WebServer + LyricSync in one asyncio event loop. AVRCP callbacks use `asyncio.create_task()` to schedule async work (lyrics fetch, WebSocket broadcast). Signal handling via `loop.add_signal_handler()` for graceful shutdown on SIGTERM.

### Data flow

1. Phone connects to board via Bluetooth (A2DP), plays music
2. BlueZ creates MediaPlayer1 D-Bus object → AVRCPController detects it
3. AVRCPController reads Track (title, artist) → LyricsFetcher fetches LRC
4. LrcParser parses timestamps → LyricSync stores sorted lines
5. WebServer broadcasts full lyrics list to browser (one-time)
6. AVRCPController reports Position → LyricSync finds current line index
7. On line change → WebServer broadcasts line index → browser highlights

### WebSocket protocol

JSON messages with `type` field:
- `{"type": "song", "title": "...", "artist": "..."}` — track change
- `{"type": "lyrics", "lines": ["line1", "line2", ...]}` — full lyrics (on song change)
- `{"type": "line", "index": N}` — current line index (real-time updates)
- `{"type": "style", "data": {...}}` — style update (color, font_size, etc.)
- `{"type": "ping"}` / `{"type": "pong"}` — heartbeat

### Key module relationships

- `lyric_app.py` wires everything: `run_web()` creates `AVRCPController` + `LyricsFetcher` + `LyricSync` + `WebServer` + `AudioEffects` + `CommandHandler`
- `AVRCPController` connects to BlueZ system bus via `dbus_next`, reads `org.bluez.MediaPlayer1` properties
- `LyricsFetcher` uses `aiohttp.ClientSession` to query NetEase Cloud API, caches to disk
- `LyricSync` does binary search on LRC timestamps, uses local clock for interpolation
- `CommandHandler` processes browser-originated JSON commands (style/volume)
- `ConfigManager` uses `watchdog` for hot-reload; registers listeners for `display.*` config changes

## Key Dependencies

- `dbus-next` — D-Bus communication with BlueZ (AVRCP MediaPlayer1)
- `aiohttp` — Web server + WebSocket + HTTP client for lyrics API
- `pulsectl` — PulseAudio volume control
- `watchdog` — config file hot-reload
- `pyinstaller` — packaging

## System Requirements (target board)

BlueZ ≥ 5.50, PulseAudio (or PipeWire with pipewire-pulse + wireplumber), D-Bus, X11/Wayland + chromium-browser. The board is configured as an A2DP sink by install.sh, which deploys: BlueZ `main.conf` (device class + discoverable), PulseAudio `default.pa` (bluetooth modules), and `lyric-bt-agent.service` (auto-pairing agent). User must be in `bluetooth` and `pulse-access` groups. `loginctl enable-linger` required for headless D-Bus session. Network access required for lyrics API queries.
