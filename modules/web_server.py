"""
Web 服务器模块 - aiohttp HTTP + WebSocket

功能：
- 静态文件服务（web/ 目录下的 HTML/CSS/JS）
- WebSocket 双向通信（歌词推送、样式更新、心跳）
- 兼容 PyInstaller 打包路径
"""

import sys
import json
import logging
import asyncio
from pathlib import Path
from typing import Set, Optional, Callable, Any, Dict

try:
    from aiohttp import web, WSMsgType
    from aiohttp.web import WebSocketResponse
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False
    logger = logging.getLogger(__name__)
    logger.warning("aiohttp 未安装，Web 服务器功能不可用")

logger = logging.getLogger(__name__)


class WebServer:
    """aiohttp Web 服务器：HTTP 静态文件 + WebSocket 广播"""

    def __init__(
        self,
        config: dict,
        on_command: Optional[Callable[[str], None]] = None,
    ):
        if not AIOHTTP_AVAILABLE:
            raise RuntimeError("aiohttp 未安装，无法启动 Web 服务器")

        self.web_config = config.get('web', {})
        self.host = self.web_config.get('host', '127.0.0.1')
        self.port = self.web_config.get('port', 8080)
        self.on_command = on_command

        # 定位 web 静态文件目录（兼容 PyInstaller 打包和源码运行）
        if getattr(sys, 'frozen', False):
            web_dir = Path(sys._MEIPASS) / 'web'
        else:
            web_dir = Path(__file__).parent.parent / 'web'

        self.web_dir = web_dir

        # aiohttp 应用
        self.app = web.Application()
        self._setup_routes()
        self.runner: Optional[web.AppRunner] = None

        # WebSocket 客户端管理
        self._websockets: Set[WebSocketResponse] = set()
        self._lock = asyncio.Lock()

        # 心跳间隔（秒），aiohttp WebSocket 内置 ping/pong
        self._heartbeat_interval = 30.0

    def _setup_routes(self):
        """注册路由"""
        self.app.router.add_get('/', self._index_handler)
        self.app.router.add_get('/ws', self._ws_handler)
        if self.web_dir.exists():
            self.app.router.add_static('/', path=str(self.web_dir), show_index=False)

    async def _index_handler(self, request: web.Request) -> web.StreamResponse:
        """返回主页面"""
        index_path = self.web_dir / 'index.html'
        if index_path.exists():
            return web.FileResponse(index_path)
        return web.Response(text='web directory not found', status=404)

    async def _ws_handler(self, request: web.Request) -> WebSocketResponse:
        """WebSocket 连接处理"""
        ws = WebSocketResponse(heartbeat=self._heartbeat_interval)
        await ws.prepare(request)

        async with self._lock:
            self._websockets.add(ws)
        logger.info(f"WebSocket 客户端已连接: {request.remote}")

        try:
            async for msg in ws:
                if msg.type == WSMsgType.TEXT:
                    # 预留：处理浏览器上行命令
                    try:
                        data = json.loads(msg.data)
                        if data.get('type') == 'pong':
                            continue
                        if self.on_command:
                            self.on_command(msg.data)
                    except json.JSONDecodeError:
                        pass
                elif msg.type == WSMsgType.ERROR:
                    logger.error(f"WebSocket 错误: {ws.exception()}")
        except Exception as e:
            logger.error(f"WebSocket 处理错误: {e}")
        finally:
            async with self._lock:
                self._websockets.discard(ws)
            logger.info("WebSocket 客户端已断开")

        return ws

    async def broadcast(self, message: Dict[str, Any]):
        """向所有 WebSocket 客户端广播 JSON 消息"""
        if not self._websockets:
            return

        text = json.dumps(message, ensure_ascii=False)
        disconnected = set()

        async with self._lock:
            clients = list(self._websockets)

        for ws in clients:
            try:
                await ws.send_str(text)
            except Exception:
                disconnected.add(ws)

        if disconnected:
            async with self._lock:
                for ws in disconnected:
                    self._websockets.discard(ws)

    async def broadcast_song(self, title: str, artist: str = ''):
        """广播曲目变更"""
        await self.broadcast({"type": "song", "title": title, "artist": artist})

    async def broadcast_lyrics(self, lines: list):
        """广播完整歌词列表（切歌时一次性发送）"""
        await self.broadcast({"type": "lyrics", "lines": lines})

    async def broadcast_line(self, index: int):
        """广播当前歌词行索引"""
        await self.broadcast({"type": "line", "index": index})

    async def broadcast_style(self, style: dict):
        """广播样式更新"""
        await self.broadcast({"type": "style", "data": style})

    async def start(self):
        """启动 Web 服务器"""
        self.runner = web.AppRunner(self.app)
        await self.runner.setup()
        site = web.TCPSite(self.runner, self.host, self.port)
        await site.start()
        logger.info(f"Web 服务器已启动: http://{self.host}:{self.port}")

    async def stop(self):
        """停止 Web 服务器"""
        # 关闭所有 WebSocket
        async with self._lock:
            for ws in self._websockets:
                await ws.close()
            self._websockets.clear()

        if self.runner:
            await self.runner.cleanup()
        logger.info("Web 服务器已停止")

    def get_stats_dict(self) -> Dict[str, Any]:
        """获取统计信息"""
        return {
            'host': self.host,
            'port': self.port,
            'websockets_active': len(self._websockets),
            'web_dir': str(self.web_dir),
        }
