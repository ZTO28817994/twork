import asyncpg
from datetime import datetime

class NewsDatabase:
    def __init__(self, dsn):
        self.dsn = dsn
        self.pool = None

    async def init(self):
        if not self.pool:
            self.pool = await asyncpg.create_pool(dsn=self.dsn)

    async def insert_news(self, title, text, content_id=None, file_id=None, file_type=None, button_str=None, bot_name=None, business_type=None):
        print(f"{content_id}")
        async with self.pool.acquire() as conn:
            return await conn.fetchval("""
                INSERT INTO news_content (title, text, content_id, file_id, file_type, button_str, bot_name, business_type)
                VALUES ($1, $2, CAST($3 AS BIGINT), $4, $5, $6, $7, $8)
                RETURNING id
            """, title, text, content_id, file_id, file_type, button_str, bot_name, business_type)

    async def update_news_by_id(self, news_id: int, text=None, content_id=None, file_id=None, file_type=None, button_str=None, bot_name=None, business_type=None ):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE news_content
                SET text = $2,
                    content_id = CAST($3 AS BIGINT),
                    file_id = $4,
                    file_type = $5,
                    button_str = $6,
                    bot_name = $7,
                    business_type = $8
                WHERE id = $1
            """, news_id, text, content_id, file_id, file_type, button_str, bot_name, business_type)

    async def get_active_user_refs(self, business_type: str):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT id FROM news_user
                WHERE business_type = $1
                  AND (expire_at IS NULL OR expire_at > NOW())
            """, business_type)

    async def create_send_tasks(self, news_id: int, business_type: str):
        users = await self.get_active_user_refs(business_type)
        async with self.pool.acquire() as conn:
            for u in users:
                await conn.execute("""
                    INSERT INTO news_send_queue (user_ref_id, news_id)
                    VALUES ($1, $2)
                    ON CONFLICT DO NOTHING
                """, u["id"], news_id)

    async def get_pending_tasks(self, limit=10):
        async with self.pool.acquire() as conn:
            return await conn.fetch("""
                SELECT q.id AS task_id, q.user_ref_id, u.user_id,
                       c.text, c.file_id, c.file_type, c.button_str
                FROM news_send_queue q
                JOIN news_user u ON q.user_ref_id = u.id
                JOIN news_content c ON q.news_id = c.id
                WHERE q.state = 'pending'
                ORDER BY q.created_at
                LIMIT $1
            """, limit)

    async def mark_sent(self, task_id: int):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE news_send_queue
                SET state='sent', sent_at=NOW()
                WHERE id = $1
            """, task_id)

    async def mark_failed(self, task_id: int, reason: str):
        async with self.pool.acquire() as conn:
            await conn.execute("""
                UPDATE news_send_queue
                SET state='failed',
                    fail_reason=$2,
                    last_try_at=NOW()
                WHERE id = $1
            """, task_id, reason)
