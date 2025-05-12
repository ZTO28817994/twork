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
from handlers.HandlerRelayClass import HandlerRelayClass

from handlers.HandlerPrivateMessageClass import HandlerPrivateMessageClass
from telethon.errors import ChannelPrivateError


from telethon.tl.functions.photos import DeletePhotosRequest
from telethon.tl.types import InputPhoto
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.account import UpdateUsernameRequest
from telethon.errors import ChannelPrivateError

# 加载环境变量
if not os.getenv('GITHUB_ACTIONS'):
    from dotenv import load_dotenv
    load_dotenv(dotenv_path='.25254811.env')

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

last_message_id = 0

# 初始化 Telegram 客户端
client = TelegramClient(config['session_name'], config['api_id'], config['api_hash'])

# 常量
MAX_PROCESS_TIME = 20 * 60  # 最大运行时间 20 分钟



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


async def delete_my_profile_photos(client):
    photos = await client.get_profile_photos('me')

    if not photos:
        print("你没有设置头像。")
        return

    input_photos = []
    for photo in photos:
        if hasattr(photo, 'id') and hasattr(photo, 'access_hash') and hasattr(photo, 'file_reference'):
            input_photos.append(InputPhoto(
                id=photo.id,
                access_hash=photo.access_hash,
                file_reference=photo.file_reference
            ))

    await client(DeletePhotosRequest(id=input_photos))
    print("头像已删除。")

async def update_my_name(client, first_name, last_name=''):
    await client(UpdateProfileRequest(first_name=first_name, last_name=last_name))
    print(f"已更新用户姓名为：{first_name} {last_name}")

async def update_username(client,username):
    try:
        await client(UpdateUsernameRequest(username))  # 设置空字符串即为移除
        print("用户名已成功变更。")
    except Exception as e:
        print(f"变更失败：{e}")

async def safe_delete_message(message):
    try:
        await client.delete_messages(message.chat_id, [message.id], revoke=True)
        print(f"🧹 成功刪除訊息 {message.id}（雙方）", flush=True)
    except Exception as e:
        print(f"⚠️ 刪除訊息失敗 {message.id}：{e}", flush=True)







async def keep_db_alive():
    if db.is_closed():
        db.connect()
    else:
        try:
            db.execute_sql('SELECT 1')
        except Exception as e:
            print(f"数据库连接保持错误: {e}")

async def send_completion_message(last_message_id):
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
    record = ScrapProgress.get_or_none(
        chat_id=entity_id,
        api_id=config['api_id'],
    )

    if record is None:
        # 不存在时新增
        ScrapProgress.create(
            chat_id=entity_id,
            api_id=config['api_id'],
            message_id=message_id,
            update_datetime=datetime.now()
        )
    elif message_id > record.message_id:
        # 存在且 message_id 更大时才更新
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

   

    # 实现：根据 entity.id 映射到不同处理类
    class_map = {
        777000: HandlerNoAction,   # 替换为真实 entity.id 和处理类
        7419440827: HandlerNoAction,    #萨莱
        8076535891: HandlerNoAction    #岩仔

    }

    handler_class = class_map.get(entity.id)
    if handler_class:
        handler = handler_class(client, entity, message, extra_data)
        await handler.handle()
    else:
        
        handler = HandlerPrivateMessageClass(client, entity, message, extra_data)
        # handler = HandlerNoAction(client, entity, message, extra_data)
        handler.delete_after_process = True
        await handler.handle()
        # print(f"[Group] Message from {entity_title} ({entity.id}): {message.text}")
       

async def process_group_message(client, entity, message):
    
    extra_data = {'app_id': config['api_id']}

   

    # 实现：根据 entity.id 映射到不同处理类
    class_map = {
        2210941198: HandlerBJIClass,   # 替换为真实 entity.id 和处理类
        2054963513: HandlerRelayClass
    }

    
    

    handler_class = class_map.get(entity.id)
    if handler_class:
        handler = handler_class(client, entity, message, extra_data)
        handler.accept_duplicate = True
        await handler.handle()
    else:
        pass

async def man_bot_loop(client):
    last_message_id = 0  # 提前定义，避免 UnboundLocalError
    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        if dialog.unread_count >= 0:
            if dialog.is_user:
                current_message = None
                max_message_id = await get_max_source_message_id(entity.id)
                min_id = max_message_id if max_message_id else 1
                async for message in client.iter_messages(
                    entity, min_id=min_id, limit=1, reverse=True, filter=InputMessagesFilterEmpty()
                ):
                    current_message = message
                    await process_user_message(client, entity, message)

                if current_message:
                    await save_scrap_progress(entity.id, current_message.id)

                
                last_message_id = current_message.id if current_message else 0
                
                
            else:
               
                current_message = None
                max_message_id = await get_max_source_message_id(entity.id)
                min_id = max_message_id if max_message_id else 1

                try:
                    async for message in client.iter_messages(
                        entity, min_id=min_id, limit=100, reverse=True, filter=InputMessagesFilterEmpty()
                    ):
                        
                        if message.sticker:
                            continue
                        current_message = message
                        await process_group_message(client, entity, message)
                except ChannelPrivateError as e:
                    print(f"目标 entity: {entity} 类型：{type(entity)}")
                    print(f"❌ 无法访问频道：{e}")
                except Exception as e:
                    print(f"{e}", flush=True)
                    # print(f"{message}", flush=True)



              
                if current_message:
                    await save_scrap_progress(entity.id, current_message.id)
                    return last_message_id




async def main():
    await client.start(config['phone_number'])
    # await update_username(client,"usesrnddzzzame")
   
    # await join("Dya4zqIBXtIxMWZk") #6874-01 2017145941
    # await join("fTMvarjGSckxZmI8") #7258-02 2091886937 v
    # await join("aLUZCCIiKhM5ZWNk") #7275-03 2063167161
    # await join("cr_hRjB_dRtkODdk") #7287-04 2108982395
    # await join("AeW96FZ9pmZTdk") #6376-05 1997235289
    # await join("li2wwjC6vEc5Mzdk") #6659-06   2000730581
    # await join("YfssBV1GmsgzMWQ0")  #7350-07 2145325974
    # await join("AWkBJsoFUc81MWE1")  #5891-08 2062860209
    # await join("_nPFKXIaMns1OTQ0")  #7338-09 2015918658
    # await join("Y7KzLjhksH82ZmM8")  #06315-10 2116379337 @shunfeng807
    # await join("5vQRdy9O4AxhZWQ8")  #06393-11 2064531407    @shunfeng807
    # await join("JP4ToOui4FcyMzM0")  #6463-12   1843229948
    # await join("PsKjngKmHXtlNTM0")  #7246-13   2021739085

    # await join("fRCAnbinkG1hYjU0")  #封面备份群   2086579883
    # await join("6gAolpGeQq8wYmM0")  #封面图中转站 2054963513


    
    
    
    
  
  
    # await join("xbY8S-04jnEzYWE0")   
    # await join("7-HhTojcPCYyMjk0")    #Coniguration

    start_time = time.time()
    # 显示现在时间
    now = datetime.now()
    print(f"Current: {now.strftime('%Y-%m-%d %H:%M:%S')}",flush=True)

    while (time.time() - start_time) < MAX_PROCESS_TIME:
        last_message_id = await man_bot_loop(client)
        # await keep_db_alive()
        # print("--- Cycle End ---")
        await asyncio.sleep(random.randint(14, 30))

    await send_completion_message(last_message_id)

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())


