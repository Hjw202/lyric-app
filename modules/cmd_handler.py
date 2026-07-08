"""
命令处理模块 - 解析和分发 JSON 命令

支持的命令：
- style: 修改显示样式（通过回调推送到浏览器）
- effect: 切换音效预设
- volume: 调节音量
"""

import json
import logging
from typing import Optional, Callable, Dict, Any

logger = logging.getLogger(__name__)


class CommandHandler:
    """命令处理器"""

    def __init__(self, config: dict, audio_effects=None):
        self.config = config
        self.audio_effects = audio_effects

        # 命令处理器映射（effect/volume 直接执行，style 通过回调）
        self._handlers: Dict[str, Callable] = {
            'effect': self._handle_effect,
            'volume': self._handle_volume,
        }

    def process_command(self, json_str: str, on_style: Callable = None) -> bool:
        """
        处理 JSON 命令

        style 命令通过 on_style 回调推送到浏览器，
        effect/volume 命令直接执行。

        Args:
            json_str: JSON 字符串
            on_style: 样式回调函数，接收 style dict

        Returns:
            bool: 是否成功处理
        """
        json_str = json_str.strip()
        if not json_str.startswith('{'):
            return False

        try:
            data = json.loads(json_str)
        except json.JSONDecodeError as e:
            logger.debug(f"JSON 解析失败: {e}")
            return False

        cmd = data.get('cmd')
        if not cmd:
            logger.debug("缺少 cmd 字段")
            return False

        if cmd == 'style':
            # style 命令：提取样式后通过回调推送
            style = self._extract_style(data)
            if style:
                if on_style:
                    on_style(style)
                logger.info(f"样式已更新: {style}")
            else:
                logger.debug("没有有效的样式参数")
            return True

        # effect/volume 命令：直接执行
        handler = self._handlers.get(cmd)
        if not handler:
            logger.warning(f"未知命令: {cmd}")
            return False

        try:
            handler(data)
            return True
        except Exception as e:
            logger.error(f"执行命令 {cmd} 失败: {e}")
            return False

    def _extract_style(self, data: dict) -> dict:
        """从命令数据中提取样式参数"""
        style = {}

        if 'color' in data:
            color = data['color']
            if isinstance(color, list) and len(color) >= 3:
                style['color'] = color[:3]
            elif isinstance(color, str):
                style['color'] = self._hex_to_rgb(color)

        if 'bg_color' in data:
            bg_color = data['bg_color']
            if isinstance(bg_color, list) and len(bg_color) >= 3:
                style['bg_color'] = bg_color[:3]
            elif isinstance(bg_color, str):
                style['bg_color'] = self._hex_to_rgb(bg_color)

        if 'font_size' in data:
            font_size = data['font_size']
            if isinstance(font_size, (int, float)) and 10 <= font_size <= 200:
                style['font_size'] = int(font_size)

        if 'line_spacing' in data:
            line_spacing = data['line_spacing']
            if isinstance(line_spacing, (int, float)) and 0 <= line_spacing <= 100:
                style['line_spacing'] = int(line_spacing)

        if 'padding' in data:
            padding = data['padding']
            if isinstance(padding, (int, float)) and 0 <= padding <= 200:
                style['padding'] = int(padding)

        if 'char_interval' in data:
            char_interval = data['char_interval']
            if isinstance(char_interval, (int, float)) and 50 <= char_interval <= 2000:
                style['char_interval'] = int(char_interval)

        return style

    def _handle_effect(self, data: dict):
        """处理音效命令"""
        if not self.audio_effects:
            logger.warning("音效模块未初始化，无法切换音效")
            return

        effect_name = data.get('name', '').lower()
        if not effect_name:
            logger.warning("缺少音效名称")
            return

        self.audio_effects.set_effect(effect_name)
        logger.info(f"音效已切换: {effect_name}")

    def _handle_volume(self, data: dict):
        """处理音量命令"""
        if not self.audio_effects:
            logger.warning("音效模块未初始化，无法调节音量")
            return

        level = data.get('level')
        if level is None:
            logger.warning("缺少音量级别")
            return

        if isinstance(level, (int, float)):
            level = max(0, min(100, int(level)))
            self.audio_effects.set_volume(level)
            logger.info(f"音量已设置: {level}")
        else:
            logger.warning(f"无效的音量值: {level}")

    @staticmethod
    def _hex_to_rgb(hex_color: str) -> list:
        """将十六进制颜色转换为 RGB 列表"""
        hex_color = hex_color.lstrip('#')
        if len(hex_color) == 6:
            try:
                r = int(hex_color[0:2], 16)
                g = int(hex_color[2:4], 16)
                b = int(hex_color[4:6], 16)
                return [r, g, b]
            except ValueError:
                pass
        return [0, 255, 0]  # 默认绿色
