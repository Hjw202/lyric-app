"""
AVRCP 控制器 - 通过 BlueZ D-Bus 读取手机媒体播放信息

BlueZ 的 MediaPlayer1 接口提供：
- Track 属性: 当前歌曲的 Title/Artist/Album/Duration
- Position 属性: 播放进度（毫秒）
- Status 属性: playing/paused/stopped

设备连接后，MediaPlayer1 对象出现在 /org/bluez/hci0/dev_XX/player0。
"""

import asyncio
import logging
import time
from typing import Optional, Callable
from dataclasses import dataclass, field

from dbus_next.aio import MessageBus
from dbus_next.constants import BusType

logger = logging.getLogger(__name__)


def _unwrap(variant):
    """解开 dbus-next Variant 包装"""
    if hasattr(variant, 'value'):
        return variant.value
    return variant


def _unwrap_dict(d):
    """解开 dict 中所有 Variant 包装的值（Track 属性是 a{sv}，每个值都是 Variant）"""
    return {k: _unwrap(v) for k, v in d.items()}


@dataclass
class TrackInfo:
    """当前曲目信息"""
    title: str = ''
    artist: str = ''
    album: str = ''
    duration: int = 0  # 毫秒

    @property
    def is_valid(self) -> bool:
        return bool(self.title)

    def same_song(self, other: 'TrackInfo') -> bool:
        """判断是否同一首歌（标题+歌手相同）"""
        return self.title == other.title and self.artist == other.artist


@dataclass
class PlayerState:
    """播放器状态快照"""
    track: TrackInfo = field(default_factory=TrackInfo)
    position_ms: int = 0
    status: str = ''  # playing / paused / stopped
    position_at: float = 0.0  # 最近一次进度上报的 monotonic 时间


class AVRCPController:
    """AVRCP 控制器：监听 BlueZ 媒体播放器"""

    def __init__(
        self,
        on_track_changed: Optional[Callable[[TrackInfo], None]] = None,
        on_position_changed: Optional[Callable[[int], None]] = None,
        on_status_changed: Optional[Callable[[str], None]] = None,
    ):
        self.on_track_changed = on_track_changed
        self.on_position_changed = on_position_changed
        self.on_status_changed = on_status_changed

        self.bus: Optional[MessageBus] = None
        self.player_path: Optional[str] = None
        self.state = PlayerState()
        self._running = False
        self._poll_interval = 1.0  # 进度轮询间隔（秒）

    async def start(self):
        """启动 AVRCP 监听（带自动重试）"""
        self._running = True
        retry = 0

        while self._running:
            try:
                await self._run()
            except asyncio.CancelledError:
                break
            except Exception as e:
                retry += 1
                logger.warning(f"AVRCP 异常: {e}，5 秒后重试 (第 {retry} 次)")
                await asyncio.sleep(5)

        await self._cleanup()
        logger.info("AVRCP 控制器已停止")

    async def _run(self):
        """连接 D-Bus 系统总线并监听媒体播放器"""
        self.bus = await MessageBus(bus_type=BusType.SYSTEM).connect()
        logger.info("AVRCP 已连接到 D-Bus 系统总线")

        # 获取 ObjectManager 查找已连接的播放器
        intr = await self.bus.introspect('org.bluez', '/')
        root = self.bus.get_proxy_object('org.bluez', '/', intr)
        om = root.get_interface('org.freedesktop.DBus.ObjectManager')

        objects = await om.call_get_managed_objects()
        await self._find_player(objects)

        if self.player_path:
            logger.info(f"找到媒体播放器: {self.player_path}")
            await self._read_all_props()
        else:
            logger.info("暂无已连接的媒体播放器，等待设备连接...")

        # 监听新接口出现
        om.on_interfaces_added(self._on_interfaces_added)

        # 轮询播放进度
        poll_task = asyncio.create_task(self._poll_position())

        try:
            while self._running:
                await asyncio.sleep(1)
        finally:
            poll_task.cancel()
            try:
                await poll_task
            except asyncio.CancelledError:
                pass

    async def _find_player(self, objects: dict):
        """从 GetManagedObjects 结果中查找 MediaPlayer1"""
        for path, interfaces in objects.items():
            if 'org.bluez.MediaPlayer1' in interfaces:
                self.player_path = path
                await self._subscribe_props(path)
                return

    async def _subscribe_props(self, path: str):
        """订阅媒体播放器属性变更信号"""
        if not self.bus:
            return
        try:
            intr = await self.bus.introspect('org.bluez', path)
            proxy = self.bus.get_proxy_object('org.bluez', path, intr)
            props = proxy.get_interface('org.freedesktop.DBus.Properties')
            props.on_properties_changed(self._on_properties_changed)
            logger.debug(f"已订阅属性变更: {path}")
        except Exception as e:
            logger.warning(f"订阅属性变更失败: {e}")

    def _on_interfaces_added(self, path: str, interfaces: dict):
        """新接口出现回调（设备连接/播放器创建）"""
        if 'org.bluez.MediaPlayer1' in interfaces:
            logger.info(f"媒体播放器出现: {path}")
            self.player_path = path
            asyncio.create_task(self._on_player_appeared(path))

    async def _on_player_appeared(self, path: str):
        """设备连接后：先订阅属性变更，再读取当前状态（避免漏掉中间变更）"""
        await self._subscribe_props(path)
        await self._read_all_props()

    def _on_properties_changed(self, interface: str, changed: dict, invalidated: list):
        """属性变更回调"""
        if interface != 'org.bluez.MediaPlayer1':
            return

        if 'Track' in changed:
            track_dict = _unwrap(changed['Track'])
            if isinstance(track_dict, dict):
                track_dict = _unwrap_dict(track_dict)
                new_track = TrackInfo(
                    title=track_dict.get('Title', ''),
                    artist=track_dict.get('Artist', ''),
                    album=track_dict.get('Album', ''),
                    duration=int(track_dict.get('Duration', 0)),
                )
                if new_track.is_valid and not new_track.same_song(self.state.track):
                    logger.info(f"曲目变更: {new_track.title} - {new_track.artist}")
                    self.state.track = new_track
                    self.state.position_ms = 0
                    self.state.position_at = time.monotonic()
                    self._notify_track(new_track)

        if 'Position' in changed:
            pos = _unwrap(changed['Position'])
            if isinstance(pos, (int, float)):
                self.state.position_ms = int(pos)
                self.state.position_at = time.monotonic()
                self._notify_position(self.state.position_ms)

        if 'Status' in changed:
            status = _unwrap(changed['Status'])
            if isinstance(status, str):
                self.state.status = status
                logger.info(f"播放状态: {status}")
                self._notify_status(status)

    async def _read_all_props(self):
        """主动读取当前播放器所有属性"""
        if not self.bus or not self.player_path:
            return

        try:
            intr = await self.bus.introspect('org.bluez', self.player_path)
            proxy = self.bus.get_proxy_object('org.bluez', self.player_path, intr)
            props = proxy.get_interface('org.freedesktop.DBus.Properties')

            # Track
            try:
                track_dict = _unwrap(await props.call_get('org.bluez.MediaPlayer1', 'Track'))
                if isinstance(track_dict, dict):
                    track_dict = _unwrap_dict(track_dict)
                    track = TrackInfo(
                        title=track_dict.get('Title', ''),
                        artist=track_dict.get('Artist', ''),
                        album=track_dict.get('Album', ''),
                        duration=int(track_dict.get('Duration', 0)),
                    )
                    if track.is_valid:
                        self.state.track = track
                        self._notify_track(track)
                        logger.info(f"当前曲目: {track.title} - {track.artist}")
            except Exception as e:
                logger.debug(f"读取 Track 失败: {e}")

            # Position
            try:
                pos = _unwrap(await props.call_get('org.bluez.MediaPlayer1', 'Position'))
                if isinstance(pos, (int, float)):
                    self.state.position_ms = int(pos)
                    self.state.position_at = time.monotonic()
                    self._notify_position(self.state.position_ms)
            except Exception as e:
                logger.debug(f"读取 Position 失败: {e}")

            # Status
            try:
                status = _unwrap(await props.call_get('org.bluez.MediaPlayer1', 'Status'))
                if isinstance(status, str):
                    self.state.status = status
                    self._notify_status(status)
            except Exception as e:
                logger.debug(f"读取 Status 失败: {e}")

        except Exception as e:
            logger.error(f"读取播放器属性失败: {e}")

    async def _poll_position(self):
        """轮询播放进度（补充 PropertiesChanged 信号，部分设备不上报 Position 变更）"""
        while self._running:
            await asyncio.sleep(self._poll_interval)
            if not self.bus or not self.player_path:
                continue

            try:
                intr = await self.bus.introspect('org.bluez', self.player_path)
                proxy = self.bus.get_proxy_object('org.bluez', self.player_path, intr)
                props = proxy.get_interface('org.freedesktop.DBus.Properties')

                pos = _unwrap(await props.call_get('org.bluez.MediaPlayer1', 'Position'))
                if isinstance(pos, (int, float)):
                    self.state.position_ms = int(pos)
                    self.state.position_at = time.monotonic()
                    self._notify_position(self.state.position_ms)

            except Exception:
                pass  # 设备断开等情况，静默处理

    def get_estimated_position(self) -> int:
        """用本地时钟插值估算当前进度"""
        if self.state.status != 'playing':
            return self.state.position_ms
        elapsed = time.monotonic() - self.state.position_at
        return int(self.state.position_ms + elapsed * 1000)

    def _notify_track(self, track: TrackInfo):
        if self.on_track_changed:
            try:
                self.on_track_changed(track)
            except Exception as e:
                logger.error(f"on_track_changed 回调错误: {e}")

    def _notify_position(self, pos: int):
        if self.on_position_changed:
            try:
                self.on_position_changed(pos)
            except Exception as e:
                logger.error(f"on_position_changed 回调错误: {e}")

    def _notify_status(self, status: str):
        if self.on_status_changed:
            try:
                self.on_status_changed(status)
            except Exception as e:
                logger.error(f"on_status_changed 回调错误: {e}")

    async def _cleanup(self):
        if self.bus:
            try:
                self.bus.disconnect()
            except Exception:
                pass
            self.bus = None
        self.player_path = None

    async def stop(self):
        self._running = False
        await self._cleanup()
