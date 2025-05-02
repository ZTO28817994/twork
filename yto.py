#!/usr/bin/env python
# pylint: disable=unused-argument

import asyncio
import time
import os
import random
import re
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import MessageMediaWebPage
from telethon.tl.types import InputMessagesFilterEmpty
from peewee import DoesNotExist

from model.scrap_progress import ScrapProgress
from database import db

from handlers.HandlerBJIClass import HandlerBJIClass
from handlers.HandlerNoAction import HandlerNoAction
from handlers.HandlerPrivateMessageClass import HandlerPrivateMessageClass



# 加载环境变量
if not os.getenv('GITHUB_ACTIONS'):
    from dotenv import load_dotenv
    load_dotenv()

# 配置参数
config = {
    'api_id': os.getenv('API_ID'),
    'api_hash': os.getenv('API_HASH'),
    'phone_number': os.getenv('PHONE_NUMBER'),
    'session_name': os.getenv('API_ID') + 'session_name',
    'setting_chat_id': int(os.getenv('SETTING_CHAT_ID', '0')),
    'setting_thread_id': int(os.getenv('SETTING_THREAD_ID', '0'))
}

# 在模块顶部初始化全局缓存
local_scrap_progress = {}  # key = (chat_id, api_id), value = message_id

# 初始化 Telegram 客户端
client = TelegramClient(config['session_name'], config['api_id'], config['api_hash'])

# 常量
MAX_PROCESS_TIME = 20 * 60  # 最大运行时间 20 分钟

async def keep_db_alive():
    if db.is_closed():
        db.connect()
    else:
        try:
            db.execute_sql('SELECT 1')
        except Exception as e:
            print(f"数据库连接保持错误: {e}")

async def send_completion_message():
    try:
        print(f"发送完成消息到 {config['setting_chat_id']} 线程 {config['setting_thread_id']}")
        if config['setting_chat_id'] == 0 or config['setting_thread_id'] == 0:
            print("未设置配置线程 ID，无法发送完成消息。")
            return
        async with client.conversation(config['setting_chat_id']) as conv:
            await conv.send_message('ok', reply_to=config['setting_thread_id'])
    except Exception as e:
        print("未设置配置线程 ID，无法发送完成消息。")
        pass

async def get_max_source_message_id(source_chat_id):
    key = (source_chat_id, config['api_id'])

    if key in local_scrap_progress:
        return local_scrap_progress[key]

    try:
        record = ScrapProgress.select().where(
            (ScrapProgress.chat_id == source_chat_id) &
            (ScrapProgress.api_id == config['api_id'])
        ).order_by(ScrapProgress.update_datetime.desc()).limit(1).get()

        local_scrap_progress[key] = record.message_id
        return record.message_id

    except DoesNotExist:
        new_record = ScrapProgress.create(
            chat_id=source_chat_id,
            api_id=config['api_id'],
            message_id=0,
            update_datetime=datetime.now()
        )
        local_scrap_progress[key] = new_record.message_id
        return new_record.message_id

    except Exception as e:
        print(f"Error fetching max source_message_id: {e}")
        return None
    
async def save_scrap_progress(entity_id, message_id):
    key = (entity_id, config['api_id'])
    record, _ = ScrapProgress.get_or_create(
        chat_id=entity_id,
        api_id=config['api_id'],
    )
    record.message_id = message_id
    record.update_datetime = datetime.now()
    record.save()

    local_scrap_progress[key] = message_id  # ✅ 同步更新缓存

async def process_user_message(client, entity, message):

    botname = None
    try:
        if message.text:
            match = re.search(r'\|_kick_\|\s*(.*?)\s*(bot)', message.text, re.IGNORECASE)
            if match:
                botname = match.group(1) + match.group(2)
                await client.send_message(botname, "/start")
                await client.send_message(botname, "[~bot~]")
    except Exception as e:
        print(f"Error kicking bot: {e} {botname}", flush=True)

    extra_data = {'app_id': config['api_id']}

    entity_title = getattr(entity, 'title', f"Unknown entity {entity.id}")

    # 实现：根据 entity.id 映射到不同处理类
    class_map = {
        777000: HandlerNoAction   # 替换为真实 entity.id 和处理类
    }

    handler_class = class_map.get(entity.id)
    if handler_class:
        handler = handler_class(client, entity, message, extra_data)
        await handler.handle()
    else:
        handler = HandlerPrivateMessageClass(client, entity, message, extra_data)
        await handler.handle()
        # print(f"[Group] Message from {entity_title} ({entity.id}): {message.text}")
       

async def process_group_message(client, entity, message):

    extra_data = {'app_id': config['api_id']}

    entity_title = getattr(entity, 'title', f"Unknown entity {entity.id}")

    # 实现：根据 entity.id 映射到不同处理类
    class_map = {
        2210941198: HandlerBJIClass   # 替换为真实 entity.id 和处理类
    }

    handler_class = class_map.get(entity.id)
    if handler_class:
        handler = handler_class(client, entity, message, extra_data)
        await handler.handle()
    else:
        # print(f"[Group] Message from {entity_title} ({entity.id}): {message.text}")
        pass

async def man_bot_loop(client):
    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        if dialog.unread_count >= 0:
            if dialog.is_user:
                
                current_message = None
                max_message_id = await get_max_source_message_id(entity.id)
                min_id = max_message_id if max_message_id else 1
                async for message in client.iter_messages(
                    entity, min_id=min_id, limit=10, reverse=True, filter=InputMessagesFilterEmpty()
                ):
                    current_message = message
                    await process_user_message(client, entity, message)
                if current_message:
                    await save_scrap_progress(entity.id, current_message.id)

                
                
                # await asyncio.sleep(0.5)
                # async for message in client.iter_messages(
                #     entity, min_id=0, limit=1, reverse=True, filter=InputMessagesFilterEmpty()
                # ):
                #     await process_user_message(client, entity, message)
            else:
                # if entity.id != 2488472597:
                #     return
                current_message = None
                max_message_id = await get_max_source_message_id(entity.id)
                min_id = max_message_id if max_message_id else 1
                async for message in client.iter_messages(
                    entity, min_id=min_id, limit=10, reverse=True, filter=InputMessagesFilterEmpty()
                ):
                    current_message = message
                    await process_group_message(client, entity, message)
                if current_message:
                    await save_scrap_progress(entity.id, current_message.id)

async def join(invite_hash):
    from telethon.tl.functions.messages import ImportChatInviteRequest
    try:
        await client(ImportChatInviteRequest(invite_hash))
        print("已成功加入群组")
    except Exception as e:
        if 'InviteRequestSentError' in str(e):
            print("加入请求已发送，等待审批")
        else:
            print(f"加入群组失败: {e}")



async def main():
    await client.start(config['phone_number'])
    # await join("xbY8S-04jnEzYWE0")   
    # await join("7-HhTojcPCYyMjk0")    #Coniguration
    # exit()
    start_time = time.time()
    # 显示现在时间
    now = datetime.now()
    print(f"Current: {now.strftime('%Y-%m-%d %H:%M:%S')}",flush=True)

    while (time.time() - start_time) < MAX_PROCESS_TIME:
        await man_bot_loop(client)
        # await keep_db_alive()
        # print("--- Cycle End ---")
        await asyncio.sleep(random.randint(4, 6))

    await send_completion_message()

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())
