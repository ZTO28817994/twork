import asyncio
import json
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

from news_db import NewsDatabase
from news_config import API_TOKEN, DB_DSN

from news_main import parse_button_str 

# 校验 token 是否加载成功
if not API_TOKEN or "YOUR_BOT_TOKEN" in API_TOKEN:
    raise ValueError("❌ 请在 .news.env 中正确设置 API_TOKEN。")

bot = Bot(token=API_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
db = NewsDatabase(DB_DSN)

RATE_LIMIT = 20
MAX_RETRIES = 3



async def send_news_batch():
    await db.init()
    tasks = await db.get_pending_tasks(limit=RATE_LIMIT)

    for task in tasks:
        await asyncio.sleep(1 / RATE_LIMIT)
        user_id = task["user_id"]
        try:
            keyboard = parse_button_str(task["button_str"])

            send_kwargs = {
                "chat_id": user_id,
                "caption": task["text"],
                "reply_markup": keyboard,
                "protect_content": True
            }

            if task["file_id"]:
                if task["file_type"] == "photo":
                    await bot.send_photo(photo=task["file_id"], **send_kwargs)
                elif task["file_type"] == "video":
                    await bot.send_video(video=task["file_id"], **send_kwargs)
                else:
                    await bot.send_document(document=task["file_id"], **send_kwargs)
            else:
                await bot.send_message(chat_id=user_id, text=task["text"], reply_markup=keyboard, protect_content=True)


            await db.mark_sent(task["task_id"])

        except Exception as e:
            await db.mark_failed(task["task_id"], str(e))

async def main_loop(interval_seconds=10):
    while True:
        try:
            await send_news_batch()
        except Exception as e:
            print(f"❌ 执行错误: {e}")
        await asyncio.sleep(interval_seconds)

if __name__ == "__main__":
    asyncio.run(main_loop())
