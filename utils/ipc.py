"""
IPC 通信模块 - Unix Domain Socket 服务端/客户端封装 (优化版)

优化特性：
- 心跳检测
- 流量统计
- 更好的错误处理
- 消息队列
"""

import asyncio
import json
import logging
import time
from typing import Callable, Dict, List, Optional, Set, Any
from dataclasses import dataclass, field
from collections import deque

logger = logging.getLogger(__name__)


@dataclass
class IPCStats:
    """IPC 统计信息"""
    messages_sent: int = 0
    messages_received: int = 0
    bytes_sent: int = 0
    bytes_received: int = 0
    connections_total: int = 0
    connections_active: int = 0
    errors: int = 0
    last_message_time: float = 0


@dataclass
class ClientInfo:
    """客户端信息"""
    writer: asyncio.StreamWriter
    connected_at: float = field(default_factory=time.time)
    last_activity: float = field(default_factory=time.time)
    messages_sent: int = 0
    messages_received: int = 0


class IPCServer:
    """Unix Socket 服务端（优化版）"""

    def __init__(
        self,
        sock_path: str,
        on_data: Optional[Callable[[str, str], None]] = None,  # (client_id, data)
        heartbeat_interval: float = 30.0,
        client_timeout: float = 60.0,
    ):
        self.sock_path = sock_path
        self.on_data = on_data
        self.heartbeat_interval = heartbeat_interval
        self.client_timeout = client_timeout

        self.server: Optional[asyncio.AbstractServer] = None
        self.clients: Dict[str, ClientInfo] = {}
        self._lock = asyncio.Lock()
        self._stats = IPCStats()
        self._running = False
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._client_counter = 0

    @property
    def stats(self) -> IPCStats:
        return self._stats

    async def start(self):
        """启动 Socket 服务端"""
        import os
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

        self.server = await asyncio.start_unix_server(
            self._handle_client, path=self.sock_path
        )

        self._running = True

        # 启动心跳检测
        self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

        logger.info(f"IPC 服务端已启动: {self.sock_path}")

    async def stop(self):
        """停止服务端并清理"""
        self._running = False

        # 停止心跳任务
        if self._heartbeat_task:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass

        if self.server:
            self.server.close()
            await self.server.wait_closed()

        async with self._lock:
            for client_id, info in self.clients.items():
                info.writer.close()
                try:
                    await info.writer.wait_closed()
                except Exception:
                    pass
            self.clients.clear()

        import os
        if os.path.exists(self.sock_path):
            os.unlink(self.sock_path)

        logger.info("IPC 服务端已停止")

    async def _handle_client(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """处理客户端连接"""
        self._client_counter += 1
        client_id = f"client_{self._client_counter}"

        client_info = ClientInfo(writer=writer)

        async with self._lock:
            self.clients[client_id] = client_info
            self._stats.connections_total += 1
            self._stats.connections_active = len(self.clients)

        logger.info(f"客户端已连接: {client_id}")

        try:
            while self._running:
                try:
                    data = await asyncio.wait_for(reader.readline(), timeout=self.client_timeout)
                except asyncio.TimeoutError:
                    logger.warning(f"客户端超时: {client_id}")
                    break

                if not data:
                    break

                line = data.decode('utf-8').rstrip('\n')
                client_info.last_activity = time.time()
                client_info.messages_received += 1
                self._stats.messages_received += 1
                self._stats.bytes_received += len(data)
                self._stats.last_message_time = time.time()

                if line and self.on_data:
                    try:
                        self.on_data(client_id, line)
                    except Exception as e:
                        logger.error(f"处理数据时出错: {e}")
                        self._stats.errors += 1
        except asyncio.CancelledError:
            pass
        except ConnectionError:
            logger.info(f"客户端断开连接: {client_id}")
        except Exception as e:
            logger.error(f"客户端处理错误: {e}")
            self._stats.errors += 1
        finally:
            async with self._lock:
                del self.clients[client_id]
                self._stats.connections_active = len(self.clients)
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass
            logger.info(f"客户端已断开: {client_id}")

    async def _heartbeat_loop(self):
        """心跳检测循环"""
        while self._running:
            try:
                await asyncio.sleep(self.heartbeat_interval)
                await self._check_clients()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"心跳检测错误: {e}")

    async def _check_clients(self):
        """检查客户端状态"""
        current_time = time.time()
        timeout_clients = []

        async with self._lock:
            for client_id, info in self.clients.items():
                if current_time - info.last_activity > self.client_timeout:
                    timeout_clients.append(client_id)

        # 关闭超时客户端（在锁外等待 writer 关闭，避免死锁）
        for client_id in timeout_clients:
            logger.warning(f"移除超时客户端: {client_id}")
            info = None
            async with self._lock:
                if client_id in self.clients:
                    info = self.clients.pop(client_id)
                    self._stats.connections_active = len(self.clients)
            if info:
                info.writer.close()
                try:
                    await info.writer.wait_closed()
                except Exception:
                    pass

    async def send_to_client(self, client_id: str, message: str) -> bool:
        """发送消息到指定客户端"""
        async with self._lock:
            info = self.clients.get(client_id)
            if not info:
                return False
            # 复制引用，释放锁后安全使用
            writer = info.writer

        try:
            data = (message + '\n').encode('utf-8')
            writer.write(data)
            await writer.drain()
            async with self._lock:
                if client_id in self.clients:
                    self.clients[client_id].messages_sent += 1
            self._stats.messages_sent += 1
            self._stats.bytes_sent += len(data)
            return True
        except Exception as e:
            logger.error(f"发送到 {client_id} 失败: {e}")
            self._stats.errors += 1
            return False

    async def broadcast(self, message: str, exclude: Optional[str] = None):
        """向所有已连接的客户端广播消息"""
        data = (message + '\n').encode('utf-8')
        disconnected = set()

        async with self._lock:
            clients_copy = dict(self.clients)

        for client_id, info in clients_copy.items():
            if client_id == exclude:
                continue
            try:
                info.writer.write(data)
                await info.writer.drain()
                info.messages_sent += 1
                self._stats.messages_sent += 1
                self._stats.bytes_sent += len(data)
            except Exception:
                disconnected.add(client_id)
                self._stats.errors += 1

        # 清理断开的连接
        if disconnected:
            async with self._lock:
                for client_id in disconnected:
                    if client_id in self.clients:
                        del self.clients[client_id]
                self._stats.connections_active = len(self.clients)

    def get_client_list(self) -> List[str]:
        """获取所有客户端 ID"""
        return list(self.clients.keys())

    def get_stats_dict(self) -> Dict[str, Any]:
        """获取统计信息字典"""
        return {
            'messages_sent': self._stats.messages_sent,
            'messages_received': self._stats.messages_received,
            'bytes_sent': self._stats.bytes_sent,
            'bytes_received': self._stats.bytes_received,
            'connections_total': self._stats.connections_total,
            'connections_active': self._stats.connections_active,
            'errors': self._stats.errors,
        }


class IPCClient:
    """Unix Socket 客户端（优化版）"""

    def __init__(
        self,
        sock_path: str,
        on_data: Optional[Callable[[str], None]] = None,
        reconnect_delay: float = 2.0,
        max_reconnect_delay: float = 30.0,
    ):
        self.sock_path = sock_path
        self.on_data = on_data
        self.reconnect_delay = reconnect_delay
        self.max_reconnect_delay = max_reconnect_delay

        self.reader: Optional[asyncio.StreamReader] = None
        self.writer: Optional[asyncio.StreamWriter] = None
        self._running = False
        self._connected = False
        self._stats = IPCStats()
        self._send_queue: asyncio.Queue = asyncio.Queue(maxsize=1000)
        self._send_task: Optional[asyncio.Task] = None

    @property
    def connected(self) -> bool:
        return self._connected

    @property
    def stats(self) -> IPCStats:
        return self._stats

    async def connect(self):
        """连接到服务端"""
        self._running = True
        await self._connect_with_retry()

    async def _connect_with_retry(self):
        """带重试的连接"""
        current_delay = self.reconnect_delay

        while self._running:
            try:
                await self._do_connect()
                current_delay = self.reconnect_delay  # 重置延迟
            except asyncio.CancelledError:
                break
            except Exception as e:
                if self._running:
                    logger.warning(f"连接失败: {e}，{current_delay}秒后重试...")
                    await asyncio.sleep(current_delay)
                    # 指数退避
                    current_delay = min(current_delay * 1.5, self.max_reconnect_delay)
                else:
                    break

    async def _do_connect(self):
        """执行连接"""
        self.reader, self.writer = await asyncio.open_unix_connection(self.sock_path)
        self._connected = True
        logger.info(f"已连接到 IPC 服务端: {self.sock_path}")

        # 启动发送任务
        self._send_task = asyncio.create_task(self._send_loop())

        try:
            await self._listen()
        finally:
            self._connected = False
            if self._send_task:
                self._send_task.cancel()
                try:
                    await self._send_task
                except asyncio.CancelledError:
                    pass

    async def _listen(self):
        """监听服务端数据"""
        try:
            while self._running:
                data = await self.reader.readline()
                if not data:
                    logger.info("服务端断开连接")
                    break

                line = data.decode('utf-8').rstrip('\n')
                self._stats.messages_received += 1
                self._stats.bytes_received += len(data)
                self._stats.last_message_time = time.time()

                if line and self.on_data:
                    try:
                        self.on_data(line)
                    except Exception as e:
                        logger.error(f"处理数据时出错: {e}")
                        self._stats.errors += 1
        except asyncio.CancelledError:
            pass
        except ConnectionError:
            logger.info("连接已断开")
        except Exception as e:
            logger.error(f"监听错误: {e}")
            self._stats.errors += 1

    async def _send_loop(self):
        """发送消息循环"""
        while self._running:
            try:
                message = await asyncio.wait_for(self._send_queue.get(), timeout=1.0)
                await self._do_send(message)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"发送循环错误: {e}")
                self._stats.errors += 1

    async def _do_send(self, message: str):
        """执行发送"""
        if not self.writer or not self._connected:
            return False

        try:
            data = (message + '\n').encode('utf-8')
            self.writer.write(data)
            await self.writer.drain()
            self._stats.messages_sent += 1
            self._stats.bytes_sent += len(data)
            return True
        except Exception as e:
            logger.error(f"发送失败: {e}")
            self._stats.errors += 1
            return False

    async def send(self, message: str) -> bool:
        """发送消息（异步队列）"""
        if not self._connected:
            logger.warning("未连接，无法发送消息")
            return False

        try:
            self._send_queue.put_nowait(message)
            return True
        except asyncio.QueueFull:
            logger.warning("发送队列已满")
            return False

    async def disconnect(self):
        """断开连接"""
        self._running = False
        self._connected = False

        if self.writer:
            self.writer.close()
            try:
                await self.writer.wait_closed()
            except Exception:
                pass

        logger.info("已断开 IPC 连接")

    def get_stats_dict(self) -> Dict[str, Any]:
        """获取统计信息字典"""
        return {
            'connected': self._connected,
            'messages_sent': self._stats.messages_sent,
            'messages_received': self._stats.messages_received,
            'bytes_sent': self._stats.bytes_sent,
            'bytes_received': self._stats.bytes_received,
            'errors': self._stats.errors,
        }
