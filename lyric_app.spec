# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['lyric_app.py'],
    pathex=[],
    binaries=[],
    datas=[
        ('config/config.json', 'config'),
        ('web/', 'web'),
        ('scripts/', 'scripts'),
    ],
    hiddenimports=[
        # watchdog 使用动态导入选择平台后端，PyInstaller 无法自动检测
        'watchdog.observers.inotify_buffer',
        'watchdog.observers.inotify',
        'watchdog.observers.polling',
        # dbus_next 用于 AVRCP D-Bus 通信
        'dbus_next',
        'dbus_next.aio',
        'dbus_next.constants',
        'dbus_next.message_bus',
        'dbus_next.proxy',
        'dbus_next.validators',
        'dbus_next.signature',
        # aiohttp（Web 服务器 + 歌词 API 查询）
        'aiohttp',
        'aiohttp.web',
        'aiohttp.web_app',
        'aiohttp.web_runner',
        'aiohttp.web_socketserver',
        'aiohttp.websocket',
        'aiohttp.http_parser',
        'aiohttp.client',
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='lyric_app',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=True,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
