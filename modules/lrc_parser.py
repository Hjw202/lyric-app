"""
LRC 歌词解析模块

解析标准 LRC 格式，支持：
- 行时间标签 [mm:ss.xx]
- 多时间标签行 [00:01.23][00:15.67]同一句
- 元信息头 [ti:][ar:][al:][by:][offset:]
"""

import re
import logging
from typing import List, Optional

logger = logging.getLogger(__name__)

# 时间标签: [01:23.45] 或 [1:23.456] 或 [01:23]
_TIME_RE = re.compile(r'\[(\d{1,2}):(\d{1,2})(?:\.(\d{1,3}))?\]')
# 元信息标签: [ti:title] [ar:artist] [al:album] [by:author] [offset:ms]
_META_RE = re.compile(r'\[(ti|ar|al|by|offset):([^\]]*)\]', re.IGNORECASE)


class LrcLine:
    """单行歌词"""
    __slots__ = ('time_ms', 'text')

    def __init__(self, time_ms: int, text: str):
        self.time_ms = time_ms
        self.text = text

    def __repr__(self):
        return f"LrcLine({self.time_ms}ms, {self.text!r})"


class ParsedLrc:
    """解析后的 LRC 歌词"""

    def __init__(self):
        self.lines: List[LrcLine] = []
        self.title: str = ''
        self.artist: str = ''
        self.album: str = ''
        self.offset_ms: int = 0

    @property
    def is_empty(self) -> bool:
        return len(self.lines) == 0

    @property
    def line_texts(self) -> List[str]:
        return [line.text for line in self.lines]


def parse_lrc(lrc_text: str) -> ParsedLrc:
    """解析 LRC 文本，返回按时间排序的歌词行列表"""
    result = ParsedLrc()

    for raw_line in lrc_text.splitlines():
        raw_line = raw_line.strip()
        if not raw_line:
            continue

        # 检查元信息
        meta_match = _META_RE.match(raw_line)
        if meta_match:
            key = meta_match.group(1).lower()
            value = meta_match.group(2).strip()
            if key == 'ti':
                result.title = value
            elif key == 'ar':
                result.artist = value
            elif key == 'al':
                result.album = value
            elif key == 'offset':
                try:
                    result.offset_ms = int(value)
                except ValueError:
                    pass
            continue

        # 提取所有时间标签
        times = []
        last_end = 0
        for m in _TIME_RE.finditer(raw_line):
            mm = int(m.group(1))
            ss = int(m.group(2))
            xx_str = m.group(3)
            if xx_str:
                xx = int(xx_str)
                # 两位小数 [01:23.45] → 450ms，三位 [01:23.456] → 456ms
                if len(xx_str) == 2:
                    xx *= 10
            else:
                xx = 0
            times.append(mm * 60000 + ss * 1000 + xx)
            last_end = m.end()

        if not times:
            continue

        text = raw_line[last_end:].strip()
        for t in times:
            result.lines.append(LrcLine(t + result.offset_ms, text))

    result.lines.sort(key=lambda l: l.time_ms)

    # 去除空行歌词（时间戳正确但文本为空）
    result.lines = [l for l in result.lines if l.text]

    logger.debug(f"LRC 解析完成: {len(result.lines)} 行, title={result.title}, artist={result.artist}")
    return result
