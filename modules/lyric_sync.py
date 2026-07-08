"""
歌词同步引擎 - 匹配播放进度到 LRC 歌词行

工作原理：
1. AVRCP 上报播放进度时调用 update_position()
2. 用本地时钟在两次上报之间插值估算进度
3. 二分查找当前进度对应的 LRC 行索引
4. 行索引变化时触发回调通知前端
"""

import asyncio
import logging
import time
from typing import Optional, Callable, List

from modules.lrc_parser import ParsedLrc

logger = logging.getLogger(__name__)


class LyricSync:
    """歌词同步引擎"""

    def __init__(self, on_line_changed: Optional[Callable[[int, str], None]] = None):
        self.on_line_changed = on_line_changed

        self._parsed: Optional[ParsedLrc] = None
        self._lines: List = []  # ParsedLrc.lines 引用
        self._current_index: int = -1

        self._position_ms: int = 0
        self._position_at: float = 0.0  # monotonic
        self._is_playing: bool = False
        self._running: bool = False

    @property
    def current_index(self) -> int:
        return self._current_index

    @property
    def has_lyrics(self) -> bool:
        return self._parsed is not None and not self._parsed.is_empty

    def set_lyrics(self, parsed: ParsedLrc):
        """设置新歌词（切歌时调用）"""
        self._parsed = parsed
        self._lines = parsed.lines
        self._current_index = -1
        logger.info(f"歌词已加载: {len(self._lines)} 行")

    def clear(self):
        """清除歌词"""
        self._parsed = None
        self._lines = []
        self._current_index = -1

    def get_all_lines(self) -> List[str]:
        """返回所有歌词文本列表（供前端一次性渲染）"""
        if not self._parsed:
            return []
        return self._parsed.line_texts

    def update_position(self, position_ms: int):
        """AVRCP 上报播放进度时调用"""
        self._position_ms = position_ms
        self._position_at = time.monotonic()
        self._check_line()

    def update_status(self, status: str):
        """AVRCP 上报播放状态时调用"""
        self._is_playing = (status == 'playing')
        if status == 'stopped':
            self._position_ms = 0
        self._position_at = time.monotonic()

    def get_estimated_position(self) -> int:
        """用本地时钟插值估算当前进度"""
        if not self._is_playing:
            return self._position_ms
        elapsed = time.monotonic() - self._position_at
        return int(self._position_ms + elapsed * 1000)

    def _check_line(self):
        """检查当前行是否变化，变化则触发回调"""
        if not self._lines:
            return

        pos = self.get_estimated_position()
        new_index = self._find_line_index(pos)

        if new_index != self._current_index:
            old = self._current_index
            self._current_index = new_index

            if new_index >= 0:
                text = self._lines[new_index].text
                logger.debug(f"歌词行切换: [{old}→{new_index}] {text}")
                if self.on_line_changed:
                    try:
                        self.on_line_changed(new_index, text)
                    except Exception as e:
                        logger.error(f"on_line_changed 回调错误: {e}")
            elif old >= 0:
                # 从有歌词行进入前奏/间奏区域
                logger.debug(f"歌词行清空: [{old}→-1]")

    def _find_line_index(self, position_ms: int) -> int:
        """二分查找：找到 <= position_ms 的最后一行"""
        lines = self._lines
        if not lines:
            return -1

        # 在第一行之前（前奏）
        if position_ms < lines[0].time_ms:
            return -1

        lo, hi = 0, len(lines) - 1
        while lo < hi:
            mid = (lo + hi + 1) // 2
            if lines[mid].time_ms <= position_ms:
                lo = mid
            else:
                hi = mid - 1
        return lo

    async def start_polling(self, interval: float = 0.2):
        """启动本地时钟轮询，在 AVRCP 进度上报之间插值检测行切换"""
        self._running = True
        logger.info(f"歌词同步轮询已启动 (间隔 {interval}s)")
        while self._running:
            self._check_line()
            await asyncio.sleep(interval)

    def stop_polling(self):
        self._running = False
