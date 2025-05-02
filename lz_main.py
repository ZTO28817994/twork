import asyncio
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode

from lz_config import API_TOKEN
from lz_db import db
from handlers import lz_search_highlighted



async def main():

    bot = Bot(
        token=API_TOKEN,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
        request_timeout=10.0  # 原本是 10 秒，可降至 3~5 秒
    )

   
    # dp = Dispatcher()
   

    dp = Dispatcher()
    

    
    dp.include_router(lz_search_highlighted.router)
    await db.connect()
   
    await dp.start_polling(bot, polling_timeout=10.0)

if __name__ == "__main__":
    asyncio.run(main())
