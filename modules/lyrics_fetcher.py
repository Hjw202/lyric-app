"""
歌词查询模块 - 联网搜索并获取 LRC 歌词

使用网易云 API 搜索歌曲并获取歌词，支持内存+磁盘缓存。
"""

import asyncio
import json
import logging
import time
from pathlib import Path
from typing import Optional

try:
    import aiohttp
    AIOHTTP_AVAILABLE = True
except ImportError:
    AIOHTTP_AVAILABLE = False

logger = logging.getLogger(__name__)


class LyricsFetcher:
    """歌词查询器：搜索歌曲 → 获取 LRC → 缓存"""

    def __init__(self, config: dict):
        lyrics_config = config.get('lyrics', {})
        self.api_base = lyrics_config.get('api_base', 'https://music.163.com')
        self.cache_dir = Path(lyrics_config.get('cache_dir', '/var/cache/lyric-app/lyrics'))
        self.cache_ttl = lyrics_config.get('cache_ttl', 86400 * 30)  # 30 天
        self.request_timeout = lyrics_config.get('request_timeout', 10)
        self._min_interval = 0.5  # 最小请求间隔 500ms

        self._session: Optional[aiohttp.ClientSession] = None
        self._memory_cache: dict = {}  # key → {lrc, ts, song_id}
        self._last_request_time = 0.0

    async def _get_session(self) -> aiohttp.ClientSession:
        if self._session is None or self._session.closed:
            self._session = aiohttp.ClientSession(
                headers={'User-Agent': 'Mozilla/5.0 (Linux; Android 10) AppleWebKit/537.36'},
                timeout=aiohttp.ClientTimeout(total=self.request_timeout),
            )
        return self._session

    async def _throttle(self):
        """请求限流，避免触发 API 频率限制"""
        now = time.monotonic()
        elapsed = now - self._last_request_time
        if elapsed < self._min_interval:
            await asyncio.sleep(self._min_interval - elapsed)
        self._last_request_time = time.monotonic()

    def _cache_key(self, title: str, artist: str) -> str:
        key = f"{artist}_{title}" if artist else title
        return key.lower().replace(' ', '_').replace('/', '_').replace('\\', '_')[:100]

    def _disk_path(self, key: str) -> Path:
        return self.cache_dir / f"{key}.json"

    def _get_cached(self, key: str) -> Optional[str]:
        # 内存缓存
        entry = self._memory_cache.get(key)
        if entry and time.time() - entry['ts'] < self.cache_ttl:
            return entry['lrc']

        # 磁盘缓存
        path = self._disk_path(key)
        if path.exists():
            try:
                data = json.loads(path.read_text(encoding='utf-8'))
                if time.time() - data.get('ts', 0) < self.cache_ttl:
                    self._memory_cache[key] = data
                    return data['lrc']
            except Exception:
                pass
        return None

    def _save_cached(self, key: str, lrc: str, song_id: int = 0):
        entry = {'lrc': lrc, 'ts': time.time(), 'song_id': song_id}
        self._memory_cache[key] = entry
        try:
            self.cache_dir.mkdir(parents=True, exist_ok=True)
            self._disk_path(key).write_text(
                json.dumps(entry, ensure_ascii=False), encoding='utf-8'
            )
        except Exception as e:
            logger.warning(f"写入歌词缓存失败: {e}")

    async def fetch_lyrics(self, title: str, artist: str = '') -> Optional[str]:
        """获取歌词 LRC 文本，返回 None 表示未找到"""
        if not title:
            return None

        key = self._cache_key(title, artist)

        # 查缓存
        cached = self._get_cached(key)
        if cached is not None:
            logger.debug(f"歌词命中缓存: {title} - {artist}")
            return cached

        try:
            session = await self._get_session()

            # 步骤 1: 搜索歌曲
            await self._throttle()
            search_query = f"{title} {artist}".strip()
            async with session.get(
                f"{self.api_base}/api/search/get",
                params={'s': search_query, 'limit': 5, 'type': 1},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"搜索歌曲失败: HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)

            songs = data.get('result', {}).get('songs', [])
            if not songs:
                logger.info(f"未找到歌曲: {search_query}")
                return None

            # 模糊匹配最佳结果
            song = self._best_match(songs, title, artist)
            song_id = song['id']
            matched_title = song.get('name', '')
            matched_artist = ', '.join(
                ar.get('name', '') for ar in song.get('artists', [])
            ) if song.get('artists') else ''
            logger.info(f"匹配歌曲: {matched_title} - {matched_artist} (id={song_id})")

            # 步骤 2: 获取歌词
            await self._throttle()
            async with session.get(
                f"{self.api_base}/api/song/lyric",
                params={'id': song_id, 'lv': 1},
            ) as resp:
                if resp.status != 200:
                    logger.warning(f"获取歌词失败: HTTP {resp.status}")
                    return None
                data = await resp.json(content_type=None)

            lrc = data.get('lrc', {}).get('lyric', '')
            if not lrc:
                logger.info(f"歌曲无歌词: {matched_title} - {matched_artist}")
                return None

            self._save_cached(key, lrc, song_id)
            logger.info(f"歌词已获取并缓存: {matched_title} - {matched_artist}")
            return lrc

        except asyncio.TimeoutError:
            logger.warning(f"获取歌词超时: {title} - {artist}")
        except Exception as e:
            logger.error(f"获取歌词错误: {e}")

        return None

    @staticmethod
    def _best_match(songs: list, title: str, artist: str) -> dict:
        """从搜索结果中选最匹配的歌曲"""
        title_lower = title.lower().strip()
        artist_lower = artist.lower().strip() if artist else ''

        best = songs[0]
        best_score = 0

        for song in songs:
            song_title = song.get('name', '').lower().strip()
            song_artists = ' '.join(
                a.get('name', '').lower() for a in song.get('artists', [])
            )

            score = 0
            if title_lower in song_title or song_title in title_lower:
                score += 10
            if title_lower == song_title:
                score += 5
            if artist_lower and artist_lower in song_artists:
                score += 5
            if artist_lower and artist_lower == song_artists.strip():
                score += 3

            if score > best_score:
                best_score = score
                best = song

        return best

    async def close(self):
        if self._session and not self._session.closed:
            await self._session.close()
            self._session = None
