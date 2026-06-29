"""
结构化日志模块

功能：
- JSON 格式日志
- 日志轮转
- 性能指标记录
"""

import json
import logging
import logging.handlers
import sys
import time
from pathlib import Path
from typing import Any, Dict, Optional


class StructuredFormatter(logging.Formatter):
    """结构化 JSON 日志格式化器"""

    def __init__(self, service_name: str = "lyric-app"):
        super().__init__()
        self.service_name = service_name

    def format(self, record: logging.LogRecord) -> str:
        log_data = {
            "timestamp": self.formatTime(record, self.datefmt),
            "level": record.levelname,
            "service": self.service_name,
            "logger": record.name,
            "message": record.getMessage(),
        }

        # 添加额外字段
        if hasattr(record, 'extra_data'):
            log_data['data'] = record.extra_data

        # 添加异常信息
        if record.exc_info and record.exc_info[0]:
            log_data['exception'] = {
                'type': record.exc_info[0].__name__,
                'message': str(record.exc_info[1]),
                'traceback': self.formatException(record.exc_info),
            }

        # 添加性能指标
        if hasattr(record, 'metrics'):
            log_data['metrics'] = record.metrics

        return json.dumps(log_data, ensure_ascii=False)


class MetricsLogger:
    """性能指标日志记录器"""

    def __init__(self, logger: logging.Logger):
        self.logger = logger
        self._metrics: Dict[str, Any] = {}

    def set_metric(self, key: str, value: Any):
        """设置指标"""
        self._metrics[key] = value

    def increment(self, key: str, value: int = 1):
        """递增指标"""
        self._metrics[key] = self._metrics.get(key, 0) + value

    def log_metrics(self, message: str = "性能指标"):
        """记录指标"""
        if self._metrics:
            record = self.logger.makeRecord(
                self.logger.name,
                logging.INFO,
                "",
                0,
                message,
                (),
                None,
            )
            record.metrics = self._metrics.copy()
            self.logger.handle(record)

    def reset(self):
        """重置指标"""
        self._metrics.clear()


def setup_logger(
    name: str,
    log_file: Optional[str] = None,
    level: int = logging.INFO,
    service_name: str = "lyric-app",
    structured: bool = True,
    max_bytes: int = 10 * 1024 * 1024,  # 10MB
    backup_count: int = 5,
) -> logging.Logger:
    """
    配置日志记录器

    Args:
        name: 日志记录器名称
        log_file: 日志文件路径
        level: 日志级别
        service_name: 服务名称
        structured: 是否使用结构化格式
        max_bytes: 日志文件最大大小
        backup_count: 保留的备份文件数
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)

    # 清除现有处理器
    logger.handlers.clear()

    # 控制台处理器
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(level)

    if structured:
        console_formatter = StructuredFormatter(service_name)
    else:
        console_formatter = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
        )

    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)

    # 文件处理器（如果指定了日志文件）
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)

        file_handler = logging.handlers.RotatingFileHandler(
            log_file,
            maxBytes=max_bytes,
            backupCount=backup_count,
            encoding='utf-8',
        )
        file_handler.setLevel(level)
        file_handler.setFormatter(StructuredFormatter(service_name))
        logger.addHandler(file_handler)

    return logger


def get_logger(name: str, **kwargs) -> logging.Logger:
    """获取日志记录器（简化接口）"""
    return logging.getLogger(name)


class LogContext:
    """日志上下文管理器"""

    def __init__(self, logger: logging.Logger, operation: str, **extra):
        self.logger = logger
        self.operation = operation
        self.extra = extra
        self.start_time = 0

    def __enter__(self):
        self.start_time = time.time()
        self.logger.info(f"开始: {self.operation}", extra={'extra_data': self.extra})
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = time.time() - self.start_time
        if exc_type:
            self.logger.error(
                f"失败: {self.operation} ({duration:.3f}s)",
                extra={'extra_data': {**self.extra, 'error': str(exc_val)}}
            )
        else:
            self.logger.info(
                f"完成: {self.operation} ({duration:.3f}s)",
                extra={'extra_data': {**self.extra, 'duration': duration}}
            )
        return False
