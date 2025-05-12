import asyncio
import json
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.types import Message
from aiogram.enums import ParseMode
from aiogram.filters import Command
from aiogram.filters import CommandObject
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from news_db import NewsDatabase
from news_config import DB_DSN, API_TOKEN

bot = Bot(
    token=API_TOKEN,
    default=DefaultBotProperties(parse_mode=ParseMode.HTML)
)

dp = Dispatcher()
db = NewsDatabase(DB_DSN)

news_buffer = {
    "content_id": None,
    "title": None,
    "text": None,
    "file_id": None,
    "file_type": None,
    "button_str": None,
    "bot_name": None,
    "business_type": None,
    "id": None
}



def parse_button_str(button_str: str) -> InlineKeyboardMarkup:
    """
    解析格式为：
    按钮1 - http://t.me/Sssvip && 按钮2 - http://t.me/Sssvip
    按钮3 - http://t.me/Sssvip
    """
    if not button_str:
        return None

    keyboard = []
    lines = button_str.strip().split("\n")
    for line in lines:
        buttons = []
        parts = line.split("&&")
        for part in parts:
            part = part.strip()
            if " - " in part:
                text, url = part.split(" - ", 1)
                buttons.append(InlineKeyboardButton(text=text.strip(), url=url.strip()))
        if buttons:
            keyboard.append(buttons)

    if keyboard:
        return InlineKeyboardMarkup(inline_keyboard=keyboard)
    return None


@dp.message(Command("start"))
async def start_handler(message: Message):
    await message.answer("🤖 哥哥您好，我是鲁仔")


@dp.message(Command("show"))
async def show_news_handler(message: Message, command: CommandObject):
    try:
        news_id = int(command.args.strip())
    except (ValueError, AttributeError):
        await message.reply("⚠️ 请输入正确的新闻 ID，例如 /show 1")
        return

    await db.init()
    record = await db.pool.fetchrow("""
        SELECT file_id, text, file_type, button_str
        FROM news_content
        WHERE id = $1
    """, news_id)

    if not record:
        await message.reply("⚠️ 未找到指定 ID 的新闻")
        return

    keyboard = parse_button_str(record["button_str"])

    if record["file_type"] == "photo" and record["file_id"]:
        await message.bot.send_photo(
            chat_id=message.chat.id,
            photo=record["file_id"],
            caption=record["text"],
            parse_mode=ParseMode.HTML,
            reply_markup=keyboard
        )
    else:
        await message.reply("⚠️ 该新闻没有有效的照片或不支持的媒体类型")

@dp.message(Command("push"))
async def push_news_handler(message: Message, command: CommandObject):
    try:
        news_id = int(command.args.strip())
    except (ValueError, AttributeError):
        await message.reply("⚠️ 请输入正确的新闻 ID，例如 /push 1")
        return

    await db.init()
    record = await db.pool.fetchrow("""
        SELECT business_type FROM news_content WHERE id = $1
    """, news_id)

    if not record:
        await message.reply("⚠️ 未找到指定 ID 的新闻")
        return

    business_type = record["business_type"] or "news"

    await db.create_send_tasks(news_id, business_type)
    await message.reply(f"✅ 已将新闻 ID = {news_id} 加入 {business_type} 业务类型的推送任务队列")



@dp.message(lambda msg: msg.photo or msg.video or msg.document)
async def receive_media(message: Message):
    caption = message.caption or ""

    try:
        result = json.loads(caption)
    except Exception:
        await message.reply("⚠️ Caption 不是合法的 JSON。")
        return

    if not isinstance(result, dict) or "caption" not in result:
        await message.reply("⚠️ JSON 缺少必要字段 caption。")
        return

    if message.photo:
        file_id = message.photo[-1].file_id
        file_type = "photo"
    elif message.video:
        file_id = message.video.file_id
        file_type = "video"
    elif message.document:
        file_id = message.document.file_id
        file_type = "document"
    else:
        return

    me = await message.bot.get_me()

    content_id_raw = result.get("content_id")
    try:
        content_id = int(content_id_raw) if content_id_raw is not None else None
    except (ValueError, TypeError):
        await message.reply("⚠️ content_id 不是合法的数字或缺失")
        return

    # 统一写入 news_buffer
    news_buffer.update({
        "id": result.get("id"),
        "content_id": content_id,
        "file_id": file_id,
        "file_type": file_type,
        "text": result.get("caption", ""),
        "button_str": result.get("button_str"),
        "title": result.get("title", ""),
        "bot_name": me.username,
        "business_type": result.get("business_type")
    })

    await db.init()

    payload = {k: news_buffer.get(k) for k in ["content_id","text", "file_id", "file_type", "button_str", "bot_name", "business_type"]}

    # 先查询是否存在 content_id + bot_name
    existing_news_id = await db.pool.fetchval(
        "SELECT id FROM news_content WHERE content_id = $1 AND bot_name = $2 LIMIT 1",
        news_buffer["content_id"],
        news_buffer["bot_name"]
    )

    if existing_news_id:
        await db.update_news_by_id(news_id=existing_news_id, **payload)
        await message.reply(f"🔁 已更新新闻 ID = {existing_news_id}")
    else:
        news_id = await db.insert_news(title=news_buffer["title"] or "Untitled", **payload)
        await message.reply(f"✅ 已新增新闻并建立任务，新闻 ID = {news_id}")

async def periodic_sender():
    from news_sender import send_news_batch
    while True:
        await send_news_batch()
        await asyncio.sleep(10)

async def main():
    await db.init()
    loop = asyncio.get_event_loop()
    loop.create_task(periodic_sender())
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
