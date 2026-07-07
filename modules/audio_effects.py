"""
音效控制模块 - PulseAudio 音效预设管理

使用 pulsectl 控制音量和均衡器预设
"""

import logging
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

try:
    import pulsectl
    PULSECTL_AVAILABLE = True
except ImportError:
    PULSECTL_AVAILABLE = False
    logger.warning("pulsectl 未安装，音效控制功能不可用")


class AudioEffects:
    """音效控制器"""

    def __init__(self, config: dict):
        self.config = config.get('audio', {})
        self.presets = self.config.get('presets', {})
        self.default_volume = self.config.get('default_volume', 70)
        self.pulse: Optional[Any] = None
        self._current_effect: Optional[str] = None
        self._loaded_modules: list = []

        if PULSECTL_AVAILABLE:
            self._connect()

    def _connect(self):
        """连接到 PulseAudio"""
        try:
            self.pulse = pulsectl.Pulse('lyric-app')
            logger.info("已连接到 PulseAudio")
        except Exception as e:
            logger.error(f"连接 PulseAudio 失败: {e}")
            self.pulse = None

    def _get_default_sink(self):
        """获取默认音频输出"""
        if not self.pulse:
            return None
        try:
            return self.pulse.server_info().default_sink_name
        except Exception as e:
            logger.error(f"获取默认 sink 失败: {e}")
            return None

    def _ensure_connection(self):
        """确保 PulseAudio 连接有效，断开则自动重连"""
        if not PULSECTL_AVAILABLE:
            return False
        if self.pulse is None:
            self._connect()
        if self.pulse:
            try:
                self.pulse.server_info()
                return True
            except Exception:
                logger.warning("PulseAudio 连接已断开，尝试重连...")
                self._connect()
                return self.pulse is not None
        return False

    def set_effect(self, name: str):
        """
        设置音效预设

        Args:
            name: 预设名称 (rock, pop, classical, flat/none)
        """
        if not self._ensure_connection():
            logger.warning("PulseAudio 不可用")
            return

        name = name.lower()

        # 检查是否是 "flat" 或 "none"（卸载所有均衡器）
        if name in ('flat', 'none'):
            self._unload_all_effects()
            self._current_effect = None
            logger.info("已恢复原始音效")
            return

        # 检查预设是否存在
        preset = self.presets.get(name)
        if not preset:
            logger.warning(f"未知音效预设: {name}")
            return

        # 卸载当前效果
        self._unload_all_effects()

        # 加载新效果
        try:
            module_name = preset.get('module')
            if module_name:
                # 这里简化处理，实际实现需要根据具体的 PulseAudio 模块来配置
                # 例如 module-ladspa-sink 需要指定插件路径和参数
                logger.info(f"加载音效模块: {module_name} (预设: {name})")
                # TODO: 实际加载均衡器模块
                # self._load_equalizer_module(preset)
                self._current_effect = name
        except Exception as e:
            logger.error(f"加载音效失败: {e}")

    def _unload_all_effects(self):
        """卸载所有已加载的音效模块"""
        if not self.pulse:
            return

        for module_index in self._loaded_modules:
            try:
                self.pulse.module_unload(module_index)
                logger.debug(f"卸载模块: {module_index}")
            except Exception as e:
                logger.warning(f"卸载模块失败: {e}")

        self._loaded_modules.clear()

    def _load_equalizer_module(self, preset: dict):
        """加载均衡器模块（需要根据实际硬件配置）"""
        # 这是一个示例实现，实际使用时需要根据硬件调整
        module_name = preset.get('module')
        label = preset.get('label')

        if module_name == 'module-ladspa-sink':
            # LADSPA 均衡器示例配置
            # 实际使用需要指定插件路径、控制端口等参数
            args = f"sink_name=eq plugin=??? label=??? control=???"
            try:
                module_index = self.pulse.module_load(module_name, args)
                self._loaded_modules.append(module_index)
            except Exception as e:
                logger.error(f"加载 LADSPA 模块失败: {e}")

    def set_volume(self, level: int):
        """
        设置音量

        Args:
            level: 音量级别 (0-100)
        """
        if not self._ensure_connection():
            logger.warning("PulseAudio 不可用")
            return

        # 限制范围
        level = max(0, min(100, level))

        # 转换为 PulseAudio 音量 (0.0-1.0)
        volume = level / 100.0

        try:
            sink_name = self._get_default_sink()
            if not sink_name:
                logger.warning("未找到默认音频输出")
                return

            sink = self.pulse.get_sink_by_name(sink_name)
            # 设置音量
            self.pulse.volume_set_all_chans(sink, volume)
            logger.info(f"音量已设置为: {level}%")
        except Exception as e:
            logger.error(f"设置音量失败: {e}")

    def get_volume(self) -> int:
        """获取当前音量"""
        if not self._ensure_connection():
            return self.default_volume

        try:
            sink_name = self._get_default_sink()
            if not sink_name:
                return self.default_volume

            sink = self.pulse.get_sink_by_name(sink_name)
            # 获取当前音量（取第一个声道）
            volume = sink.volume.value_flat
            return int(volume * 100)
        except Exception as e:
            logger.error(f"获取音量失败: {e}")
            return self.default_volume

    def get_current_effect(self) -> Optional[str]:
        """获取当前音效预设名称"""
        return self._current_effect

    def close(self):
        """关闭连接"""
        if self.pulse:
            try:
                self.pulse.close()
            except Exception:
                pass
            self.pulse = None
