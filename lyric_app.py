#!/usr/bin/env python3
"""
蓝牙歌词音箱 - 统一入口

特性：
- A2DP 蓝牙音箱模式（手机直接连播放音频）
- AVRCP 读取播放曲目和进度
- 联网查询 LRC 歌词，按播放进度逐行高亮同步
- 配置热重载
- Chromium kiosk 全屏显示

使用方法：
  lyric_app.py        : 启动 Web 模式（AVRCP 歌词同步 + 浏览器渲染）
  lyric_app.py web    : 同上（web 参数可选）
"""

import sys
import os
import asyncio
import signal
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
        config_paths.insert(0, bundle_dir / 'config' / 'config.json')

    for config_path in config_paths:
        if config_path.exists():
            return str(config_path)

    return str(config_paths[0])  # 返回默认路径


def run_web(config_path: str):
    """运行 Web 模式（AVRCP 歌词同步 + WebServer 渲染）"""
    from modules.avrcp_controller import AVRCPController, TrackInfo
    from modules.lyrics_fetcher import LyricsFetcher
    from modules.lrc_parser import parse_lrc
    from modules.lyric_sync import LyricSync
    from modules.web_server import WebServer
    from modules.audio_effects import AudioEffects
    from modules.cmd_handler import CommandHandler

    # 初始化配置管理器
    config_manager = init_config_manager(config_path, auto_reload=True)
    config = config_manager.config

    # 初始化日志
    global logger
    log_file = config.get('logging', {}).get('web_file', '/var/log/lyric-app/lyric-web.log')
    logger = MetricsLogger(setup_logger(
        'lyric-web',
        log_file=log_file,
        service_name='lyric-web',
    ))

    # 创建事件循环（必须在定义回调之前）
    loop = asyncio.new_event_loop()
    asyncio.set_event_loop(loop)

    # 创建各组件
    web_server = WebServer(config)
    lyrics_fetcher = LyricsFetcher(config)
    audio_effects = AudioEffects(config)
    cmd_handler = CommandHandler(config, audio_effects)

    # 歌词同步引擎：行变更 → 广播行索引到浏览器
    lyric_sync = LyricSync(
        on_line_changed=lambda index, text: loop.is_running() and asyncio.create_task(
            web_server.broadcast_line(index)
        )
    )

    # 当前曲目信息（用于判断是否同一首歌）
    current_track_key = [None]  # 可变容器供闭包修改

    async def handle_track_change(track: TrackInfo):
        """曲目变更处理：查歌词 → 解析 → 同步 → 广播"""
        track_key = f"{track.artist}_{track.title}".lower()
        if track_key == current_track_key[0]:
            return  # 同一首歌，不重复处理
        current_track_key[0] = track_key

        logger.logger.info(f"处理曲目变更: {track.title} - {track.artist}")
        await web_server.broadcast_song(track.title, track.artist)

        # 查询歌词
        lrc_text = await lyrics_fetcher.fetch_lyrics(track.title, track.artist)
        if lrc_text:
            parsed = parse_lrc(lrc_text)
            if not parsed.is_empty:
                lyric_sync.set_lyrics(parsed)
                await web_server.broadcast_lyrics(parsed.line_texts)
                logger.logger.info(f"歌词已加载: {len(parsed.lines)} 行")
            else:
                lyric_sync.clear()
                await web_server.broadcast_lyrics([])
                logger.logger.warning("LRC 解析结果为空")
        else:
            lyric_sync.clear()
            await web_server.broadcast_lyrics([])
            logger.logger.info("未找到歌词")

    # AVRCP 回调
    def on_track_changed(track: TrackInfo):
        """AVRCP 曲目变更回调（从事件循环内调用，可 schedule task）"""
        if loop.is_running():
            asyncio.create_task(handle_track_change(track))

    def on_position_changed(pos: int):
        """AVRCP 播放进度回调"""
        lyric_sync.update_position(pos)

    def on_status_changed(status: str):
        """AVRCP 播放状态回调"""
        lyric_sync.update_status(status)

    avrcp = AVRCPController(
        on_track_changed=on_track_changed,
        on_position_changed=on_position_changed,
        on_status_changed=on_status_changed,
    )

    # 浏览器上行命令处理
    def on_browser_command(text: str):
        if loop.is_running():
            cmd_handler.process_command(
                text,
                on_style=lambda style: asyncio.create_task(
                    web_server.broadcast_style(style)
                )
            )

    web_server.on_command = on_browser_command

    # 配置变更监听
    def on_config_change(event):
        logger.logger.info(f"配置变更: {event.key}")
        if event.key.startswith('display.'):
            style = config_manager.get('display.default_style', {})
            if loop.is_running():
                asyncio.create_task(web_server.broadcast_style(style))

    config_manager.add_listener(on_config_change)

    # 信号处理
    shutdown_event = asyncio.Event()

    def signal_handler():
        logger.logger.info("收到停止信号")
        shutdown_event.set()

    for sig in (signal.SIGINT, signal.SIGTERM):
        loop.add_signal_handler(sig, signal_handler)

    async def main():
        """异步主函数"""
        # 启动 Web 服务器
        await web_server.start()

        # 启动 AVRCP 监听
        avrcp_task = asyncio.create_task(avrcp.start())

        # 启动歌词同步轮询
        sync_task = asyncio.create_task(lyric_sync.start_polling(interval=0.2))

        # 等待停止信号
        await shutdown_event.wait()

        # 停止服务
        logger.logger.info("正在停止服务...")
        avrcp_task.cancel()
        sync_task.cancel()
        try:
            await avrcp_task
        except asyncio.CancelledError:
            pass
        try:
            await sync_task
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
        loop.run_until_complete(lyrics_fetcher.close())
        cleanup_config_manager()
        loop.close()
        logger.log_metrics("Web 服务统计")


def main():
    """主入口函数"""
    # 支持可选的 'web' 参数，无参数时直接启动
    mode = sys.argv[1].lower() if len(sys.argv) > 1 else 'web'

    if mode not in ('web', '--help', '-h'):
        print(f"未知参数: {mode}")
        print("用法: lyric_app.py [web]")
        sys.exit(1)

    if mode in ('--help', '-h'):
        print("用法: lyric_app.py [web]")
        print("  web  - 启动 Web 单进程模式（A2DP 蓝牙音箱 + AVRCP 歌词同步 + 浏览器渲染）")
        sys.exit(0)

    config_path = load_config_path()
    run_web(config_path)


if __name__ == '__main__':
    main()
