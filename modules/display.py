"""
歌词显示模块 - Pygame 全屏歌词渲染 (优化版)

优化特性：
- 双缓冲和硬件加速
- 脏矩形更新
- 字体渲染缓存
- 自适应分辨率
"""

import os
import logging
import threading
from typing import Dict, Optional, Tuple, List
from queue import Queue, Empty

import pygame

logger = logging.getLogger(__name__)


class TextCache:
    """文本渲染缓存（线程安全）"""

    def __init__(self, max_size: int = 200):
        self._cache: Dict[str, pygame.Surface] = {}
        self._max_size = max_size
        self._access_order: List[str] = []
        self._lock = threading.Lock()

    def get(self, key: str) -> Optional[pygame.Surface]:
        with self._lock:
            if key in self._cache:
                self._access_order.remove(key)
                self._access_order.append(key)
                return self._cache[key]
            return None

    def put(self, key: str, surface: pygame.Surface):
        with self._lock:
            if len(self._cache) >= self._max_size:
                oldest = self._access_order.pop(0)
                del self._cache[oldest]
            self._cache[key] = surface
            self._access_order.append(key)

    def clear(self):
        with self._lock:
            self._cache.clear()
            self._access_order.clear()


class Display:
    """歌词显示器 (优化版)"""

    def __init__(self, config: dict):
        self.config = config
        self.display_config = config.get('display', {})
        self.style = self.display_config.get('default_style', {}).copy()
        self.screen: Optional[pygame.Surface] = None
        self.font: Optional[pygame.font.Font] = None
        self.clock: Optional[pygame.time.Clock] = None

        # 歌词状态
        self._lyrics = ""
        self._last_lyrics = ""
        self._lyric_queue: Queue = Queue()
        self._style_lock = threading.Lock()
        self._running = False
        self._display_info = None

        # 渲染缓存
        self._text_cache = TextCache(max_size=200)
        self._last_rendered_lines: List[Tuple[str, pygame.Surface, pygame.Rect]] = []

        # 脏矩形区域
        self._dirty_rects: List[pygame.Rect] = []
        self._need_full_redraw = True

    @staticmethod
    def _check_x11_running() -> bool:
        """检测 X11 服务器是否在运行"""
        import subprocess
        try:
            result = subprocess.run(
                ['pgrep', '-x', 'Xorg'],
                capture_output=True, timeout=2
            )
            if result.returncode == 0:
                return True
            result = subprocess.run(
                ['pgrep', '-x', 'Xwayland'],
                capture_output=True, timeout=2
            )
            if result.returncode == 0:
                return True
        except Exception:
            pass
        # 检查常见 X11 socket
        return os.path.exists('/tmp/.X11-unix')

    def _setup_display(self):
        """初始化 Pygame 显示（优化版）"""
        driver = self.display_config.get('driver', 'auto')

        if driver == 'auto':
            # 自动检测：优先 X11，回退 fbcon
            if os.environ.get('DISPLAY') or self._check_x11_running():
                driver = 'x11'
            else:
                driver = 'fbcon'
            logger.info(f"自动检测显示驱动: {driver}")

        if driver == 'fbcon':
            fb_device = self.display_config.get('fb_device', '/dev/fb0')
            os.environ['SDL_VIDEODRIVER'] = 'fbcon'
            os.environ['SDL_FBDEV'] = fb_device
            os.environ['SDL_NOMOUSE'] = '1'
            logger.info(f"使用 Framebuffer 显示: {fb_device}")
        else:
            x11_display = self.display_config.get('x11_display', ':0')
            os.environ['SDL_VIDEODRIVER'] = 'x11'
            os.environ.setdefault('DISPLAY', x11_display)
            logger.info(f"使用 X11 显示: {os.environ['DISPLAY']}")

        # 初始化 Pygame
        pygame.init()
        pygame.mouse.set_visible(False)

        # 获取显示信息
        self._display_info = pygame.display.Info()
        width = self._display_info.current_w or 800
        height = self._display_info.current_h or 480

        # 创建全屏显示 - 启用双缓冲和硬件加速
        flags = pygame.FULLSCREEN | pygame.DOUBLEBUF | pygame.HWSURFACE
        self.screen = pygame.display.set_mode((width, height), flags)
        pygame.display.set_caption("Lyric Speaker")

        # 加载字体
        self._load_font()

        # 创建时钟
        self.clock = pygame.time.Clock()

        # 标记需要全屏重绘
        self._need_full_redraw = True

        logger.info(f"显示初始化完成: {width}x{height}, 双缓冲已启用")

    def _load_font(self):
        """加载字体"""
        font_size = self.style.get('font_size', 48)
        font_name = self.style.get('font_name')

        try:
            if font_name and os.path.exists(font_name):
                self.font = pygame.font.Font(font_name, font_size)
            else:
                # 优先使用支持中文的字体
                chinese_fonts = [
                    '/usr/share/fonts/truetype/wqy/wqy-microhei.ttc',
                    '/usr/share/fonts/truetype/droid/DroidSansFallbackFull.ttf',
                    '/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc',
                ]
                self.font = None
                for font_path in chinese_fonts:
                    if os.path.exists(font_path):
                        self.font = pygame.font.Font(font_path, font_size)
                        break
                if not self.font:
                    self.font = pygame.font.SysFont(None, font_size)
        except Exception as e:
            logger.warning(f"加载字体失败: {e}，使用默认字体")
            self.font = pygame.font.SysFont(None, font_size)

        # 清除缓存（字体变化后）
        self._text_cache.clear()

    def _wrap_text(self, text: str, max_width: int, font: Optional[pygame.font.Font] = None) -> List[str]:
        """自动换行处理"""
        if not text:
            return [""]

        font = font or self.font
        lines = text.split('\n')
        wrapped_lines = []

        for line in lines:
            if not line:
                wrapped_lines.append("")
                continue

            current_line = ""
            for char in line:
                test_line = current_line + char
                if font.size(test_line)[0] <= max_width:
                    current_line = test_line
                else:
                    if current_line:
                        wrapped_lines.append(current_line)
                    current_line = char
            if current_line:
                wrapped_lines.append(current_line)

        return wrapped_lines if wrapped_lines else [""]

    def update_lyrics(self, text: str):
        """更新歌词文本（线程安全）"""
        self._lyric_queue.put(text)

    def apply_style(self, style_dict: dict):
        """应用新样式（线程安全）"""
        with self._style_lock:
            self.style.update(style_dict)
            self._load_font()
            self._need_full_redraw = True  # 样式变化需要全屏重绘
            logger.info(f"样式已更新: {style_dict}")

    def get_current_style(self) -> dict:
        """获取当前样式"""
        with self._style_lock:
            return self.style.copy()

    def _get_text_color(self) -> Tuple[int, int, int]:
        color = self.style.get('color', [0, 255, 0])
        return tuple(color[:3])

    def _get_bg_color(self) -> Tuple[int, int, int]:
        color = self.style.get('bg_color', [0, 0, 0])
        return tuple(color[:3])

    def _render_text_cached(self, text: str, color: Tuple[int, int, int], font: Optional[pygame.font.Font] = None, font_size: int = 48) -> pygame.Surface:
        """带缓存的文本渲染"""
        font = font or self.font
        cache_key = f"{text}_{color}_{font_size}"
        cached = self._text_cache.get(cache_key)
        if cached:
            return cached

        surface = font.render(text, True, color)
        # 转换为显示格式以加速 blit
        surface = surface.convert()
        self._text_cache.put(cache_key, surface)
        return surface

    def _render_frame(self):
        """渲染一帧（优化版）"""
        # 检查是否有新歌词
        try:
            while True:
                new_lyric = self._lyric_queue.get_nowait()
                if new_lyric != self._lyrics:
                    self._lyrics = new_lyric
                    self._need_full_redraw = True
        except Empty:
            pass

        # 如果不需要重绘，直接返回
        if not self._need_full_redraw and not self._dirty_rects:
            return

        # 获取样式和字体（在锁内读取，避免与 watchdog 线程竞态）
        with self._style_lock:
            style = self.style.copy()
            current_font = self.font

        bg_color = tuple(style.get('bg_color', [0, 0, 0]))
        text_color = tuple(style.get('color', [0, 255, 0]))
        padding = style.get('padding', 40)
        line_spacing = style.get('line_spacing', 10)
        font_size = style.get('font_size', 48)

        screen_width = self.screen.get_width()
        screen_height = self.screen.get_height()

        # 计算歌词变化的区域
        if self._need_full_redraw:
            # 全屏重绘
            self.screen.fill(bg_color)
        else:
            # 只清除旧歌词区域
            for _, _, rect in self._last_rendered_lines:
                self.screen.fill(bg_color, rect)

        self._last_rendered_lines = []

        if self._lyrics:
            max_text_width = screen_width - 2 * padding
            lines = self._wrap_text(self._lyrics, max_text_width, current_font)

            line_height = current_font.get_linesize()
            total_height = len(lines) * (line_height + line_spacing) - line_spacing
            start_y = max(padding, (screen_height - total_height) // 2)

            # 渲染每一行
            for i, line in enumerate(lines):
                if line:
                    text_surface = self._render_text_cached(line, text_color, current_font, font_size)
                    text_rect = text_surface.get_rect()
                    text_rect.centerx = screen_width // 2
                    text_rect.top = start_y + i * (line_height + line_spacing)

                    self.screen.blit(text_surface, text_rect)
                    self._last_rendered_lines.append((line, text_surface, text_rect))
                    self._dirty_rects.append(text_rect)

        else:
            # 无歌词时显示提示
            hint_text = "等待连接..."
            hint_color = (128, 128, 128)
            hint_surface = self._render_text_cached(hint_text, hint_color, current_font, font_size)
            hint_rect = hint_surface.get_rect(center=self.screen.get_rect().center)
            self.screen.blit(hint_surface, hint_rect)
            self._last_rendered_lines.append((hint_text, hint_surface, hint_rect))
            self._dirty_rects.append(hint_rect)

        # 更新显示
        if self._need_full_redraw:
            pygame.display.flip()
            self._need_full_redraw = False
            self._dirty_rects.clear()
        else:
            # 只更新变化的区域
            if self._dirty_rects:
                pygame.display.update(self._dirty_rects)
                self._dirty_rects.clear()

    def main_loop(self):
        """主循环（应在主线程中调用）"""
        self._setup_display()
        self._running = True

        try:
            while self._running:
                # 处理 Pygame 事件
                for event in pygame.event.get():
                    if event.type == pygame.QUIT:
                        self._running = False
                    elif event.type == pygame.KEYDOWN:
                        if event.key == pygame.K_ESCAPE:
                            self._running = False

                # 渲染帧
                self._render_frame()

                # 控制帧率
                self.clock.tick(10)

        except KeyboardInterrupt:
            logger.info("收到中断信号")
        except Exception as e:
            logger.error(f"显示循环错误: {e}")
        finally:
            self.stop()

    def stop(self):
        """停止显示"""
        self._running = False
        self._text_cache.clear()
        pygame.quit()
        logger.info("显示已停止")
