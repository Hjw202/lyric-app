"""
BLE 服务模块 - 蓝牙低功耗外设服务 (优化版)

优化特性：
- 自动错误恢复和重启
- 连接状态监控
- 优雅的断开处理
"""

import asyncio
import json
import logging
from typing import Optional, Callable, Set
from dataclasses import dataclass
from enum import Enum

from dbus_next.aio import MessageBus
from bluez_peripheral.advert import Advertisement
from bluez_peripheral.gatt import Service, Characteristic, CharacteristicWriteMethod
from bluez_peripheral.service import ServiceManager

# Characteristic write flags (兼容不同版本)
WRITE_FLAG = "write"
WRITE_NO_RESPONSE_FLAG = "write-without-response"

logger = logging.getLogger(__name__)


class BLEState(Enum):
    """BLE 服务状态"""
    IDLE = "idle"
    STARTING = "starting"
    RUNNING = "running"
    ERROR = "error"
    STOPPING = "stopping"


@dataclass
class BLEStats:
    """BLE 统计信息"""
    connections_total: int = 0
    connections_active: int = 0
    lyrics_received: int = 0
    commands_received: int = 0
    errors: int = 0
    restarts: int = 0


class LyricCharacteristic(Characteristic):
    """歌词写入特征"""

    def __init__(self, uuid: str, on_receive: Optional[Callable] = None, stats: Optional[BLEStats] = None):
        super().__init__(
            uuid=uuid,
            flags=[CharacteristicWriteMethod.WRITE, CharacteristicWriteMethod.WRITE_WITHOUT_RESPONSE],
        )
        self.on_receive = on_receive
        self.stats = stats

    def WriteValue(self, value: bytes, options: dict):
        """接收歌词数据"""
        try:
            text = value.decode('utf-8').rstrip('\n')
            if text and self.on_receive:
                if self.stats:
                    self.stats.lyrics_received += 1
                self.on_receive(text)
        except Exception as e:
            logger.error(f"歌词特征写入错误: {e}")
            if self.stats:
                self.stats.errors += 1


class ControlCharacteristic(Characteristic):
    """控制命令写入特征"""

    def __init__(self, uuid: str, on_receive: Optional[Callable] = None, stats: Optional[BLEStats] = None):
        super().__init__(
            uuid=uuid,
            flags=[CharacteristicWriteMethod.WRITE, CharacteristicWriteMethod.WRITE_WITHOUT_RESPONSE],
        )
        self.on_receive = on_receive
        self.stats = stats

    def WriteValue(self, value: bytes, options: dict):
        """接收控制命令"""
        try:
            text = value.decode('utf-8').rstrip('\n')
            if text and self.on_receive:
                if self.stats:
                    self.stats.commands_received += 1
                self.on_receive(text)
        except Exception as e:
            logger.error(f"控制特征写入错误: {e}")
            if self.stats:
                self.stats.errors += 1


class BLEServer:
    """BLE 服务器（优化版）"""

    def __init__(
        self,
        config: dict,
        on_lyric: Optional[Callable[[str], None]] = None,
        on_command: Optional[Callable[[str], None]] = None,
        max_retries: int = -1,  # -1 表示无限重试
        retry_delay: float = 5.0,
    ):
        self.config = config
        self.on_lyric = on_lyric
        self.on_command = on_command
        self.max_retries = max_retries
        self.retry_delay = retry_delay

        self.bus: Optional[MessageBus] = None
        self.manager: Optional[ServiceManager] = None
        self.advertisement: Optional[Advertisement] = None

        self._state = BLEState.IDLE
        self._running = False
        self._stats = BLEStats()
        self._connected_devices: Set[str] = set()

    @property
    def state(self) -> BLEState:
        return self._state

    @property
    def stats(self) -> BLEStats:
        return self._stats

    async def start(self):
        """启动 BLE 服务（带自动重试）"""
        self._running = True
        retry_count = 0

        while self._running:
            try:
                self._state = BLEState.STARTING
                await self._run_ble_service()
            except asyncio.CancelledError:
                logger.info("BLE 服务收到取消信号")
                break
            except Exception as e:
                self._state = BLEState.ERROR
                self._stats.errors += 1
                retry_count += 1

                if self.max_retries > 0 and retry_count >= self.max_retries:
                    logger.error(f"BLE 服务达到最大重试次数 ({self.max_retries})，停止服务")
                    break

                self._stats.restarts += 1
                logger.warning(f"BLE 服务异常: {e}，{self.retry_delay}秒后重启 (第{retry_count}次)")
                await asyncio.sleep(self.retry_delay)
            finally:
                await self._cleanup()

        self._state = BLEState.IDLE

    async def _run_ble_service(self):
        """运行 BLE 服务"""
        try:
            # 连接到系统总线
            self.bus = await MessageBus().connect()
            logger.info("已连接到 D-Bus 系统总线")

            # 创建歌词服务
            lyric_service_uuid = self.config.get('lyric_service_uuid')
            if not lyric_service_uuid:
                raise ValueError("配置缺少 ble.lyric_service_uuid")
            lyric_char_uuid = self.config.get('lyric_char_uuid')
            if not lyric_char_uuid:
                raise ValueError("配置缺少 ble.lyric_char_uuid")
            control_service_uuid = self.config.get('control_service_uuid')
            if not control_service_uuid:
                raise ValueError("配置缺少 ble.control_service_uuid")
            control_char_uuid = self.config.get('control_char_uuid')
            if not control_char_uuid:
                raise ValueError("配置缺少 ble.control_char_uuid")

            lyric_service = Service(
                uuid=lyric_service_uuid,
                primary=True,
            )
            lyric_char = LyricCharacteristic(
                uuid=lyric_char_uuid,
                on_receive=self._handle_lyric,
                stats=self._stats,
            )
            lyric_service.addCharacteristic(lyric_char)

            # 创建控制服务
            control_service = Service(
                uuid=control_service_uuid,
                primary=True,
            )
            control_char = ControlCharacteristic(
                uuid=control_char_uuid,
                on_receive=self._handle_command,
                stats=self._stats,
            )
            control_service.addCharacteristic(control_char)

            # 注册服务
            self.manager = await ServiceManager(self.bus).register()
            self.manager.registerService(lyric_service)
            self.manager.registerService(control_service)

            # 创建并注册广播
            adapter = self.config.get('adapter', '/org/bluez/hci0')
            device_name = self.config.get('device_name', 'LyricSpeaker')

            self.advertisement = Advertisement(
                localName=device_name,
                serviceUUIDs=[
                    lyric_service_uuid,
                    control_service_uuid,
                ],
            )

            await self.advertisement.register(adapter)

            self._state = BLEState.RUNNING
            logger.info(f"BLE 服务已启动，设备名称: {device_name}")

            # 保持运行
            while self._running:
                await asyncio.sleep(1)

        except asyncio.CancelledError:
            raise
        except Exception as e:
            logger.error(f"BLE 服务运行错误: {e}")
            raise

    async def _cleanup(self):
        """清理资源"""
        if self.advertisement:
            try:
                await self.advertisement.unregister()
                self.advertisement = None
            except Exception as e:
                logger.warning(f"注销广播失败: {e}")

        if self.manager:
            try:
                # ServiceManager 可能没有 unregister 方法
                self.manager = None
            except Exception:
                pass

        if self.bus:
            try:
                self.bus.disconnect()
                self.bus = None
            except Exception:
                pass

    async def stop(self):
        """停止 BLE 服务"""
        self._running = False
        self._state = BLEState.STOPPING
        logger.info("正在停止 BLE 服务...")

        # 等待当前操作完成
        await asyncio.sleep(0.5)

        await self._cleanup()
        self._state = BLEState.IDLE
        logger.info("BLE 服务已停止")

    def _handle_lyric(self, text: str):
        """处理接收到的歌词"""
        logger.debug(f"收到歌词: {text[:50]}...")
        if self.on_lyric:
            try:
                self.on_lyric(text)
            except Exception as e:
                logger.error(f"歌词回调错误: {e}")
                self._stats.errors += 1

    def _handle_command(self, text: str):
        """处理接收到的命令"""
        logger.debug(f"收到命令: {text}")
        if self.on_command:
            try:
                self.on_command(text)
            except Exception as e:
                logger.error(f"命令回调错误: {e}")
                self._stats.errors += 1

    def get_status(self) -> dict:
        """获取服务状态"""
        return {
            'state': self._state.value,
            'stats': {
                'connections_total': self._stats.connections_total,
                'connections_active': self._stats.connections_active,
                'lyrics_received': self._stats.lyrics_received,
                'commands_received': self._stats.commands_received,
                'errors': self._stats.errors,
                'restarts': self._stats.restarts,
            }
        }


async def run_ble_server(config: dict, on_lyric: Callable, on_command: Callable) -> BLEServer:
    """运行 BLE 服务的便捷函数"""
    server = BLEServer(config, on_lyric, on_command)
    await server.start()
    return server
