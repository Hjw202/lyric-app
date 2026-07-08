# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['lyric_app.py'],
    pathex=[],
    binaries=[],
    datas=[('config/config.json', 'config')],
    hiddenimports=[
        # watchdog 使用动态导入选择平台后端，PyInstaller 无法自动检测
        'watchdog.observers.inotify_buffer',
        'watchdog.observers.inotify',
        'watchdog.observers.polling',
        # bluez_peripheral / dbus_next 可能使用动态导入
        'dbus_next',
        'dbus_next.aio',
        'dbus_next.constants',
        'dbus_next.message_bus',
        'dbus_next.proxy',
        'dbus_next.validators',
        'dbus_next.signature',
        'bluez_peripheral',
        'bluez_peripheral.advert',
        'bluez_peripheral.gatt',
        'bluez_peripheral.service',
        'bluez_peripheral.util',
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
