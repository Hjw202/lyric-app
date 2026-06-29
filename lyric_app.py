#!/usr/bin/env python3
"""
蓝牙歌词音箱 - 统一入口 (优化版)

优化特性：
- 结构化日志
- 配置热重载
- 优雅的信号处理
- 性能监控

使用方法：
  lyric_app.py ble  : 启动 BLE 服务进程
  lyric_app.py ui   : 启动 UI 显示进程
"""

import sys
import os
import asyncio
import signal
import threading
from pathlib import Path
from typing import Optional

# 添加项目根目录到 Python 路径
sys.path.insert(0, str(Path(__file__).parent))

from utils.logger import setup_logger, MetricsLogger, LogContext
from modules.config_manager import init_config_manager, cleanup_config_manager

# 日志记录器
logger: Optional[MetricsLogger] = None


def load_config_path() -> str:
    """获取配置文件路径"""
    config_paths = [
        Path(__file__).parent / 'config' / 'config.json',
        Path('/etc/lyric-app/config.json'),
        Path.cwd() / 'config' / 'config.json',
    ]

    # PyInstaller 打包路径
    if getattr(sys, 'frozen', False):
        bundle_dir = Path(sys._MEIPASS)
        config_paths.insert(0, bundle_dir / 'config.json')

    for config_path in config_paths:
        if config_path.exists():
            return str(config_path)

    return str(config_paths[0])  # 返回默认路径


def run_ble(config_path: str):
    """运行 BLE 服务进程"""
    from modules.ble_server import BLEServer
    from utils.ipc import IPCServer

    # 初始化配置管理器
    config_manager = init_config_manager(config_path, auto_reload=True)
    config = config_manager.config

    # 初始化日志
    global logger
    log_file = config.get('logging', {}).get('file', '/tmp/lyric-ble.log')
    logger = MetricsLogger(setup_logger(
        'lyric-ble',
        log_file=log_file,
        service_name='lyric-ble',
    ))

    socket_path = config.get('ipc', {}).get('socket_path', '/tmp/lyric.sock')
    ble_config = config.get('ble', {})

    # 创建 IPC 服务器
    ipc_server = IPCServer(socket_path)

    def on_lyric(text: str):
        """歌词数据回调"""
        logger.increment('lyrics_received')
        logger.logger.debug(f"收到歌词: {text[:50]}...")
        asyncio.run_coroutine_threadsafe(
            ipc_server.broadcast(text),
            loop
        )

    def on_command(text: str):
        """命令数据回调"""
        logger.increment('commands_received')
        logger.logger.debug(f"收到命令: {text}")
        asyncio.run_coroutine_threadsafe(
            ipc_server.broadcast(text),
            loop
        )

    # 配置变更监听
    def on_config_change(event):
        logger.logger.info(f"配置变更: {event.key}")
        # 更新 BLE 配置
        if event.key.startswith('ble.'):
            nonlocal ble_config
            ble_config = config_manager.get_section('ble')

    config_manager.add_listener(on_config_change)

    # 创建 BLE 服务器
    ble_server = BLEServer(ble_config, on_lyric, on_command)

    # 创建事件循环
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 信号处理
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.logger.info("收到停止信号")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    async def main():
        """异步主函数"""
        # 启动 IPC 服务端
        await ipc_server.start()
        logger.logger.info(f"IPC 服务端已启动: {socket_path}")

        # 启动 BLE 服务
        ble_task = asyncio.create_task(ble_server.start())

        # 等待停止信号
        await shutdown_event.wait()

        # 停止服务
        logger.logger.info("正在停止服务...")
        ble_task.cancel()
        try:
            await ble_task
        except asyncio.CancelledError:
            pass
        await ipc_server.stop()

    try:
        with LogContext(logger.logger, "BLE 服务"):
            loop.run_until_complete(main())
    except KeyboardInterrupt:
        logger.logger.info("收到中断信号")
    except Exception as e:
        logger.logger.error(f"BLE 服务错误: {e}")
    finally:
        cleanup_config_manager()
        loop.close()
        logger.log_metrics("BLE 服务统计")


def run_ui(config_path: str):
    """运行 UI 显示进程"""
    import queue
    from modules.display import Display
    from modules.cmd_handler import CommandHandler
    from modules.audio_effects import AudioEffects
    from utils.ipc import IPCClient

    # 初始化配置管理器
    config_manager = init_config_manager(config_path, auto_reload=True)
    config = config_manager.config

    # 初始化日志
    global logger
    log_file = config.get('logging', {}).get('file', '/tmp/lyric-ui.log')
    logger = MetricsLogger(setup_logger(
        'lyric-ui',
        log_file=log_file,
        service_name='lyric-ui',
    ))

    socket_path = config.get('ipc', {}).get('socket_path', '/tmp/lyric.sock')

    # 创建显示、音效和命令处理器
    display = Display(config)
    audio_effects = AudioEffects(config)
    cmd_handler = CommandHandler(config, display, audio_effects)

    # 数据接收队列
    data_queue = queue.Queue()

    def on_data(line: str):
        """IPC 数据回调"""
        data_queue.put(line)

    # 配置变更监听
    def on_config_change(event):
        logger.logger.info(f"配置变更: {event.key}")
        if event.key.startswith('display.'):
            display.apply_style(config_manager.get('display.default_style', {}))

    config_manager.add_listener(on_config_change)

    # 创建 IPC 客户端
    ipc_client = IPCClient(socket_path, on_data)

    # IPC 客户端线程
    def ipc_thread():
        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(ipc_client.connect())
        except Exception as e:
            logger.logger.error(f"IPC 客户端错误: {e}")
        finally:
            loop.close()

    # 启动 IPC 客户端线程
    ipc_thread_obj = threading.Thread(target=ipc_thread, daemon=True)
    ipc_thread_obj.start()

    # Pygame 主循环
    import pygame

    display._setup_display()
    display._running = True

    try:
        while display._running:
            # 处理 Pygame 事件
            for event in pygame.event.get():
                if event.type == pygame.QUIT:
                    display._running = False
                elif event.type == pygame.KEYDOWN:
                    if event.key == pygame.K_ESCAPE:
                        display._running = False

            # 处理队列中的数据
            try:
                while True:
                    line = data_queue.get_nowait()
                    logger.increment('messages_processed')
                    # 尝试作为命令处理
                    if not cmd_handler.process_command(line):
                        # 如果不是命令，则作为歌词处理
                        display.update_lyrics(line)
            except queue.Empty:
                pass

            # 渲染帧
            display._render_frame()
            display.clock.tick(10)

    except KeyboardInterrupt:
        logger.logger.info("收到中断信号")
    except Exception as e:
        logger.logger.error(f"UI 循环错误: {e}")
    finally:
        # 清理
        asyncio.run(ipc_client.disconnect())
        audio_effects.close()
        cleanup_config_manager()
        pygame.quit()
        logger.log_metrics("UI 服务统计")


def main():
    """主入口函数"""
    if len(sys.argv) < 2:
        print("用法: lyric_app.py <ble|ui>")
        print("  ble  - 启动 BLE 服务进程")
        print("  ui   - 启动 UI 显示进程")
        sys.exit(1)

    mode = sys.argv[1].lower()
    config_path = load_config_path()

    if mode == 'ble':
        run_ble(config_path)
    elif mode == 'ui':
        run_ui(config_path)
    else:
        print(f"未知模式: {mode}")
        print("请使用 'ble' 或 'ui'")
        sys.exit(1)


if __name__ == '__main__':
    main()
