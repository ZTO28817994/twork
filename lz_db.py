# lz_db.py
import asyncpg
from lz_config import POSTGRES_DSN
from lz_memory_cache import MemoryCache

class DB:
    def __init__(self):
        self.dsn = POSTGRES_DSN
        self.pool = None
        self.cache = MemoryCache()

    async def connect(self):
        self.pool = await asyncpg.create_pool(dsn=self.dsn)

    def _normalize_query(self, keyword_str: str) -> str:
        return " ".join(keyword_str.strip().lower().split())

    async def search_keyword_page_highlighted(self, keyword_str: str, last_id: int = 0, limit: int = 10):
        query = self._normalize_query(keyword_str)
        cache_key = f"highlighted:{query}:{last_id}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT id, source_id, file_type,
                       ts_headline('simple', content, plainto_tsquery('simple', $1)) AS highlighted_content
                FROM sora_content
                WHERE content_seg_tsv @@ plainto_tsquery('simple', $1)
                  AND id > $2
                ORDER BY id ASC
                LIMIT $3
                ''',
                query, last_id, limit
            )
            result = [dict(r) for r in rows]
            self.cache.set(cache_key, result, ttl=60)  # 缓存 60 秒
            return result

    async def search_keyword_page_plain(self, keyword_str: str, last_id: int = 0, limit: int = None):
        query = self._normalize_query(keyword_str)
        cache_key = f"plain:{query}:{last_id}:{limit}"
        cached = self.cache.get(cache_key)
        if cached:
            return cached

        async with self.pool.acquire() as conn:
            rows = await conn.fetch(
                '''
                SELECT id, source_id, file_type, content
                FROM sora_content
                WHERE content_seg_tsv @@ plainto_tsquery('simple', $1)
                AND id > $2
                ORDER BY id ASC
                LIMIT $3
                ''',
                query, last_id, limit
            )
            result = [dict(r) for r in rows]
            self.cache.set(cache_key, result, ttl=60)
            return result



db = DB()