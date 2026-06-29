"""
配置管理模块 - 支持热重载

功能：
- 配置文件监听
- 自动重载
- 配置变更通知
"""

import json
import logging
import threading
import time
from pathlib import Path
from typing import Callable, Dict, List, Optional, Any
from dataclasses import dataclass
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler, FileModifiedEvent

logger = logging.getLogger(__name__)


@dataclass
class ConfigChangeEvent:
    """配置变更事件"""
    key: str
    old_value: Any
    new_value: Any
    timestamp: float


class ConfigManager:
    """配置管理器"""

    def __init__(self, config_path: str, auto_reload: bool = True):
        self.config_path = Path(config_path)
        self._config: Dict = {}
        self._lock = threading.RLock()
        self._listeners: List[Callable[[ConfigChangeEvent], None]] = []
        self._observer: Optional[Observer] = None
        self._auto_reload = auto_reload

        # 初始加载
        self._load_config()

        # 启动文件监听
        if auto_reload:
            self._start_watching()

    def _load_config(self):
        """加载配置文件"""
        try:
            if self.config_path.exists():
                with open(self.config_path, 'r', encoding='utf-8') as f:
                    new_config = json.load(f)

                with self._lock:
                    old_config = self._config.copy()
                    self._config = new_config

                # 通知变更
                if old_config:
                    self._notify_changes(old_config, new_config)

                logger.info(f"配置已加载: {self.config_path}")
            else:
                logger.warning(f"配置文件不存在: {self.config_path}")
        except Exception as e:
            logger.error(f"加载配置文件失败: {e}")

    def _notify_changes(self, old_config: Dict, new_config: Dict, prefix: str = ""):
        """递归通知配置变更"""
        for key in set(list(old_config.keys()) + list(new_config.keys())):
            full_key = f"{prefix}.{key}" if prefix else key
            old_val = old_config.get(key)
            new_val = new_config.get(key)

            if old_val != new_val:
                event = ConfigChangeEvent(
                    key=full_key,
                    old_value=old_val,
                    new_value=new_val,
                    timestamp=time.time(),
                )

                # 如果是嵌套字典，递归通知
                if isinstance(old_val, dict) and isinstance(new_val, dict):
                    self._notify_changes(old_val, new_val, full_key)
                else:
                    self._notify_listeners(event)

    def _notify_listeners(self, event: ConfigChangeEvent):
        """通知所有监听器"""
        for listener in self._listeners:
            try:
                listener(event)
            except Exception as e:
                logger.error(f"配置监听器错误: {e}")

    def _start_watching(self):
        """启动文件监听"""
        try:
            self._observer = Observer()
            handler = ConfigFileHandler(self)
            self._observer.schedule(
                handler,
                str(self.config_path.parent),
                recursive=False,
            )
            self._observer.start()
            logger.info(f"配置文件监听已启动: {self.config_path}")
        except Exception as e:
            logger.warning(f"启动配置文件监听失败: {e}")

    def stop_watching(self):
        """停止文件监听"""
        if self._observer:
            self._observer.stop()
            self._observer.join()
            self._observer = None

    def reload(self):
        """手动重载配置"""
        self._load_config()

    def get(self, key: str, default: Any = None) -> Any:
        """获取配置值（支持点号分隔的路径）"""
        with self._lock:
            keys = key.split('.')
            value = self._config
            for k in keys:
                if isinstance(value, dict) and k in value:
                    value = value[k]
                else:
                    return default
            return value

    def get_section(self, section: str) -> Dict:
        """获取配置段"""
        with self._lock:
            return self._config.get(section, {}).copy()

    def add_listener(self, listener: Callable[[ConfigChangeEvent], None]):
        """添加配置变更监听器"""
        self._listeners.append(listener)

    def remove_listener(self, listener: Callable[[ConfigChangeEvent], None]):
        """移除配置变更监听器"""
        if listener in self._listeners:
            self._listeners.remove(listener)

    @property
    def config(self) -> Dict:
        """获取完整配置（只读副本）"""
        with self._lock:
            return self._config.copy()


class ConfigFileHandler(FileSystemEventHandler):
    """配置文件变更处理器"""

    def __init__(self, manager: ConfigManager):
        self.manager = manager
        self._last_modified = 0

    def on_modified(self, event):
        if event.is_directory:
            return

        # 只处理配置文件
        if Path(event.src_path).name == self.manager.config_path.name:
            # 防止重复触发
            current_time = time.time()
            if current_time - self._last_modified < 1.0:
                return
            self._last_modified = current_time

            logger.info("检测到配置文件变更，重新加载...")
            self.manager.reload()


# 全局配置管理器实例
_config_manager: Optional[ConfigManager] = None


def get_config_manager() -> Optional[ConfigManager]:
    """获取全局配置管理器"""
    return _config_manager


def init_config_manager(config_path: str, auto_reload: bool = True) -> ConfigManager:
    """初始化全局配置管理器"""
    global _config_manager
    _config_manager = ConfigManager(config_path, auto_reload)
    return _config_manager


def cleanup_config_manager():
    """清理全局配置管理器"""
    global _config_manager
    if _config_manager:
        _config_manager.stop_watching()
        _config_manager = None
