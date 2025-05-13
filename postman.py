#!/usr/bin/env python
# pylint: disable=unused-argument

import asyncio
import time
import os

# 加载环境变量
if not os.getenv('GITHUB_ACTIONS'):
    from dotenv import load_dotenv
    load_dotenv(dotenv_path='.29614663.env')


import random
import re
from datetime import datetime
from telethon import TelegramClient
from telethon.tl.types import MessageMediaWebPage
from telethon.tl.types import InputMessagesFilterEmpty
from peewee import DoesNotExist

from model.scrap_progress import ScrapProgress
from model.scrap_config import ScrapConfig
from database import db



from handlers.HandlerBJIClass import HandlerBJIClass
from handlers.HandlerBJILiteClass import HandlerBJILiteClass
from handlers.HandlerNoAction import HandlerNoAction
from handlers.HandlerRelayClass import HandlerRelayClass

from handlers.HandlerPrivateMessageClass import HandlerPrivateMessageClass
from telethon.errors import ChannelPrivateError


from telethon.tl.functions.photos import DeletePhotosRequest
from telethon.tl.types import InputPhoto
from telethon.tl.functions.account import UpdateProfileRequest
from telethon.tl.functions.account import UpdateUsernameRequest
from telethon.tl.functions.channels import InviteToChannelRequest, TogglePreHistoryHiddenRequest,LeaveChannelRequest
from telethon.errors import ChannelPrivateError






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

# 黑名单缓存
blacklist_entity_ids = set()

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

async def leave_group(entity):
    try:
        await client(LeaveChannelRequest(channel=entity))
        print(f'✅ 已退出群组/频道: {getattr(entity, "title", entity.id)}')
    except Exception as e:
        print(f'❌ 退出失败: {e}')

async def open_chat_history(entity):
    try:
        result = await client(TogglePreHistoryHiddenRequest(
            channel=entity,
            enabled=False  # False = 允许新成员查看历史记录
        ))
        print(f'✅ 已开启历史记录可见: {result}')
    except Exception as e:
        print(f'❌ 操作失败: {e}')

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


async def invite_bot(bot_username, entity):
# 获取 Bot 实体
    bot_entity = await client.get_entity(bot_username)
    # 邀请 Bot 到超级群
    try:
        await client.send_message(bot_username, '/start')
        await client.send_message(bot_username, 'Hello')
        await client(InviteToChannelRequest(
            channel=entity,
            users=[bot_entity]
        ))
        print(f'已邀请 @{bot_username} 进入本群')

        # 检查是否真的在群里
        participants = await client.get_participants(entity)
        if any(p.username and p.username.lower() == bot_username.lower() for p in participants):
            print(f'✅ 确认 @{bot_username} 已经加入')
        else:
            print(f'⚠️ @{bot_username} 似乎没有加入，可能已被踢出或受限')

    except Exception as e:
        print(f'邀请失败: {e}')



async def safe_delete_message(message):
    try:
        await client.delete_messages(message.chat_id, [message.id], revoke=True)
        print(f"🧹 成功刪除訊息A {message.id}（雙方）", flush=True)
    except Exception as e:
        print(f"⚠️ 刪除訊息失敗A {message.id}：{e}", flush=True)

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

async def is_blacklisted(entity_id):
    global blacklist_entity_ids

    # ✅ 先查缓存
    if entity_id in blacklist_entity_ids:
        return True

    # ✅ 先尝试从 ScrapConfig 取黑名单
    try:
        record = ScrapConfig.get(
            (ScrapConfig.api_id == config['api_id']) &
            (ScrapConfig.title == 'BLACKLIST_IDS')
        )
        raw = record.value or ''
        
        ids = {int(x.strip()) for x in raw.split(',') if x.strip().isdigit()}
        blacklist_entity_ids.update(ids)  # 缓存

        return entity_id in blacklist_entity_ids
    except DoesNotExist:
        print("⚠️ scrap_config 中找不到 BLACKLIST_IDS")
        return False
    except Exception as e:
        print(f"⚠️ 加载黑名单失败: {e}")
        return False


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

async def process_user_message(entity, message):

    botname = None

    if message.text:
        try:
            match = re.search(r'\|_kick_\|\s*(.*?)\s*(bot)', message.text, re.IGNORECASE)
            if match:
                botname = match.group(1) + match.group(2)
                await client.send_message(botname, "/start")
                await client.send_message(botname, "[~bot~]")

        except Exception as e:
                print(f"Error kicking bot: {e} {botname}", flush=True)

        #  |_join_|QQCyh1N2sMU5ZGQ0

        try:
            inviteurl = None
            match2 = re.search(r'\|_join_\|(.*)', message.text, re.IGNORECASE)
            if match2:
                inviteurl = match2.group(1) 
                print(f"邀请链接: {inviteurl}")
                await join(inviteurl)    #Coniguration
                
        except Exception as e:
                print(f"Error livite: {e} {inviteurl}", flush=True)
   

    extra_data = {'app_id': config['api_id'],'config': config}

   

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
       
       

async def process_group_message(entity, message):
    
    extra_data = {'app_id': config['api_id']}


    # 检测是否是 |_init_|
    if message.text == '|_init_|':
        await invite_bot('luzai01bot', entity)  # 替换为实际的 Bot 用户名
        await invite_bot('has_no_access_bot', entity)  # 替换为实际的 Bot 用户名
        await invite_bot('DeletedAcconutBot', entity)  # 替换为实际的 Bot 用户名
        await invite_bot('freebsd66bot', entity)  # 替换为实际的 Bot 用户名
        await safe_delete_message(message)
        await open_chat_history(entity)
        await client.send_message(entity.id, f"entity.id: {str(entity.id)}"  )
        await leave_group(entity)

        return
            
    # 实现：根据 entity.id 映射到不同处理类
    class_map = {
        # 2210941198: HandlerBJIClass,   # 替换为真实 entity.id 和处理类
        2210941198: HandlerBJILiteClass,   # 替换为真实 entity.id 和处理类
        2054963513: HandlerRelayClass,
        # 2030683460: HandlerNoAction,        #Configuration
       
    }

   

    

    handler_class = class_map.get(entity.id)
    if handler_class:

        entity_title = getattr(entity, 'title', f"Unknown entity {entity.id}")
        print(f"[Group-X] Message from {entity_title} ({entity.id}): {message.text}")

        handler = handler_class(client, entity, message, extra_data)
        handler.accept_duplicate = True
        await handler.handle()


    else:
        pass



async def man_bot_loop():
    last_message_id = 0  # 提前定义，避免 UnboundLocalError
    async for dialog in client.iter_dialogs():
        entity = dialog.entity

        # ✅ 跳过黑名单
        if await is_blacklisted(entity.id):
            print(f"🚫 已屏蔽 entity: {entity.id}，跳过处理")
            continue

        entity_title = getattr(entity, 'title', None)
        if not entity_title:
            first_name = getattr(entity, 'first_name', '') or ''
            last_name = getattr(entity, 'last_name', '') or ''
            entity_title = f"{first_name} {last_name}".strip() or "Unknown"

        print(f"当前对话: {entity_title} ({entity.id})", flush=True)

        if dialog.unread_count >= 0:
            if dialog.is_user:
                current_message = None
                max_message_id = await get_max_source_message_id(entity.id)
                min_id = max_message_id if max_message_id else 1
                async for message in client.iter_messages(
                    entity, min_id=min_id, limit=10, reverse=True, filter=InputMessagesFilterEmpty()
                ):
                    current_message = message
                    
                    await process_user_message(entity, message)

                if current_message:
                    await save_scrap_progress(entity.id, current_message.id)

                
                last_message_id = current_message.id if current_message else 0
                
                
            else:
               
                current_message = None
                max_message_id = await get_max_source_message_id(entity.id)
                min_id = max_message_id if max_message_id else 1

                try:
                    async for message in client.iter_messages(
                        entity, min_id=min_id, limit=500, reverse=True, filter=InputMessagesFilterEmpty()
                    ):
                        
                        if message.sticker:
                            continue
                        current_message = message
                        # print(f"当前消息ID(G): {current_message.id}")
                        await process_group_message(entity, message)
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
    await keep_db_alive()

    me = await client.get_me()
    print(f'你的用户名: {me.username}')
    print(f'你的ID: {me.id}')
    print(f'你的名字: {me.first_name} {me.last_name or ""}')
    print(f'是否是Bot: {me.bot}')


    # await delete_my_profile_photos(client)
    # await update_username(client,"gunndd8kdhdj")
    # exit()

    # await join("Dya4zqIBXtIxMWZk") #6874-01 2017145941    - 22329346  / 20100034
    # await join("fTMvarjGSckxZmI8") #7258-02 2091886937 ok
    # await join("aLUZCCIiKhM5ZWNk") #7275-03 2063167161    -22329346   / 20100034
    # await join("cr_hRjB_dRtkODdk") #7287-04 2108982395 - 20100034
    # await join("AeW96FZ9pmZTdk") #6376-05 1997235289  - 22329346  / 20100034
    # await join("li2wwjC6vEc5Mzdk") #6659-06   2000730581 - 22329346   / 20100034
    # await join("YfssBV1GmsgzMWQ0")  #7350-07 2145325974 / 20100034
    # await join("AWkBJsoFUc81MWE1")  #5891-08 2062860209 / 20100034
    # await join("_nPFKXIaMns1OTQ0")  #7338-09 2015918658 / 20100034
    # await join("3eDZvSPvkVgyNmY0")  #06315-10 2047726819 v ok shunfeng807
    # await join("3eDZvSPvkVgyNmY0")  #06393-11 2003243227 v   @shunfeng807
    # await join("JP4ToOui4FcyMzM0")  #6463-12   1843229948
    # await join("PsKjngKmHXtlNTM0")  #7246-13   2021739085 v

    # await join("fRCAnbinkG1hYjU0")  #封面备份群   2086579883
    # await join("6gAolpGeQq8wYmM0")  #封面图中转站 2054963513


    # |_join_|3eDZvSPvkVgyNmY0

    
    
    
  
  
    # await join("xbY8S-04jnEzYWE0")   
    
    
    start_time = time.time()
    # 显示现在时间
    now = datetime.now()
    print(f"Current: {now.strftime('%Y-%m-%d %H:%M:%S')}",flush=True)

    while (time.time() - start_time) < MAX_PROCESS_TIME:
        try:
            last_message_id = await asyncio.wait_for(man_bot_loop(), timeout=300)  # 5分钟超时
        except asyncio.TimeoutError:
            print("⚠️ 任务超时，跳过本轮", flush=True)
        # await asyncio.sleep(random.randint(5, 10))
       

    await send_completion_message(last_message_id)

if __name__ == "__main__":
    with client:
        client.loop.run_until_complete(main())


