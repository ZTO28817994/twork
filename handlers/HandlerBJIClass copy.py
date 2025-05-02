import asyncio
import json
import re
import random
import unicodedata
import os
from collections import defaultdict, namedtuple
from handlers.QuietQuoteGenerator import QuietQuoteGenerator
from telethon.tl.types import PeerUser, PeerChannel, KeyboardButtonCallback
from telethon import types
from telethon.tl.types import KeyboardButtonUrl
from telethon.errors import ChatForwardsRestrictedError,FloodWaitError
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest
import imagehash
from datetime import datetime
from PIL import Image as PILImage
from model.scrap import Scrap  # 确保你有对应 Peewee Model
from model.scrap_progress import ScrapProgress
from database import ensure_connection

from collections import namedtuple

class HandlerBJIClass:
    def __init__(self, client, entity, message, extra_data):
        self.client = client
        self.entity = entity
        self.message = message
        self.extra_data = extra_data

    async def handle(self):
        quote_gen = QuietQuoteGenerator()

        
        # await self.check_me()
        # await self.client.send_message(2210941198, "求救，我的当前发言量一直只有5")
        # exit(0)

        if self.message.id % 102930 == 0:
            await self.client.send_message(self.entity.id, quote_gen.random_quote())
            await asyncio.sleep(30)
        print(f"Message from {self.entity.title} ({self.message.id}): {self.message.text}")
        pattern = r"https://t\.me/FileDepotBot\?start=([^\s]+)"
        message_text_str = self.message.text

        if self.message.from_id and isinstance(self.message.from_id, PeerUser):
            if self.message.from_id.user_id == 7294369541:
                await self.process_shellbot_chat_message()
                pass

        elif message_text_str:
            pass
            matches = re.findall(pattern, message_text_str)
            for match in matches:
                FileDepotMessage = namedtuple("FileDepotMessage", ["text", "id", "user_id", "channel_id"])
                message_text = 'FileDepotBot_' + match
                print(f"Message: {message_text}\r\n\r\n")

                user_id = None
                channel_id = None
                if self.message.from_id and isinstance(self.message.from_id, PeerUser):
                    user_id = self.message.from_id.user_id
                if isinstance(self.message.peer_id, PeerChannel):
                    channel_id = self.message.peer_id.channel_id

                filedepotmessage = FileDepotMessage(
                    text=message_text, id=self.message.id, user_id=user_id, channel_id=channel_id
                )
                await self.fdbot(self.client, filedepotmessage)


    async def fdbot(self, client, message):
        async with client.conversation("FileDepotBot") as conv:
            forwarded_message = await conv.send_message(message.text)
            try:
                response = await asyncio.wait_for(conv.get_response(forwarded_message.id), timeout=30)
            except asyncio.TimeoutError:
                print("Response timeout.")
                return

            print(f"Response: {response}\r\n\r\n")

            caption_json = json.dumps({
                "text": message.text,
                "content": response.text,
                "user_id": message.user_id,
                "message_id": message.id,
                "chat_id": message.channel_id,
            }, ensure_ascii=False, indent=4)

            if response.media:
                if hasattr(response, 'grouped_id') and response.grouped_id:
                    if isinstance(response.peer_id, PeerUser):
                        chat_id = response.peer_id.user_id

                    album_messages = await client.get_messages(response.peer_id, limit=15)
                    album = []
                    total_items = 0
                    button_data = None
                    current_button = None
                    button_message_id = 0

                    for msg in album_messages:
                        if msg.text:
                            match = re.search(r'共(\d+)个', msg.text)
                            if match:
                                total_items = int(match.group(1))
                                print(f"总数: {total_items}")

                        if msg.reply_markup:
                            for row in msg.reply_markup.rows:
                                for button in row.buttons:
                                    if isinstance(button, KeyboardButtonCallback) and button.text == "加载更多":
                                        button_data = button.data.decode()
                                        current_button = button
                                        button_message_id = msg.id
                                        print(f"按钮数据: {button_data}")

                        if msg.grouped_id == response.grouped_id:
                            album.append(msg)

                    if album:
                        await asyncio.sleep(0.5)
                        result_send = await self.safe_forward_or_send(
                            client, response.id, response.chat_id, 2008008502, album, caption_json
                        )

                    if total_items != 0 and button_data:
                        await self.send_fake_callback(client, chat_id, button_message_id, button_data, 2)
                        times = (total_items // 10) - 2
                        for i in range(times):
                            await self.fetch_messages_and_load_more(
                                client, chat_id, button_data, caption_json, i + 3
                            )
                            await asyncio.sleep(7)

                    if album:
                        return result_send

                elif isinstance(response.media, types.MessageMediaPhoto):
                    await self.safe_forward_or_send(
                        client, response.id, response.chat_id, 2008008502, response.media.photo, caption_json
                    )

                elif isinstance(response.media, types.MessageMediaDocument):
                    doc = response.media.document
                    if doc.mime_type.startswith('video/'):
                        return await self.safe_forward_or_send(
                            client, response.id, response.chat_id, 2008008502, doc, caption_json
                        )
                    else:
                        return await self.safe_forward_or_send(
                            client, response.id, response.chat_id, 2008008502, doc, caption_json
                        )
            else:
                print("Received non-media and non-text response")

    async def process_shellbot_chat_message(self):
        ensure_connection()  # ✅ 保证数据库连接活着

        if not self.message.reply_markup:
            return

        for row in self.message.reply_markup.rows:
            for button in row.buttons:
                if isinstance(button, KeyboardButtonUrl) and button.text in {'👀查看', '👀邮局查看'}:
                    match = re.search(r"(?i)start=([a-zA-Z0-9_]+)", button.url)
                    if match:
                        start_key = match.group(1)
                        source_chat_id = getattr(self.message.peer_id, "channel_id", 0)

                        ShellMessage = namedtuple("ShellMessage", [
                            "text", "id", "start_key", "user_id", 
                            "source_chat_id", "source_message_id", "source_bot_id"
                        ])
                        
                        shell_message = ShellMessage(
                            text=f"/start {start_key}",
                            id=self.message.id,
                            start_key=start_key,
                            user_id=None,
                            source_chat_id=source_chat_id,
                            source_message_id=self.message.id,
                            source_bot_id=7294369541,
                        )

                        print(f"Shell message: {shell_message}")

                        scrap = Scrap.select().where(
                            (Scrap.start_key == shell_message.start_key)
                        ).first()

                        if scrap:
                            scrap.source_chat_id = shell_message.source_chat_id
                            scrap.source_message_id = shell_message.source_message_id
                            scrap.save()
                            print("----- Record updated")
                        else:
                            Scrap.create(
                                start_key=shell_message.start_key,
                                source_bot_id=shell_message.source_bot_id,
                                source_chat_id=shell_message.source_chat_id,
                                source_message_id=shell_message.source_message_id,
                            )
                            print("----- NEW : Record created")

                        await self.shellbot(shell_message)

    async def check_me(self):
        bot_title = "She11PostBot"
            
        async with self.client.conversation(bot_title) as conv:
            # 根据bot_username 找到 wp_bot 中对应的 bot_name = bot_username 的字典
            
            # 发送消息到机器人
            forwarded_message = await conv.send_message("/s")
            
            response =  None
            updateNoneDate = True

            # print(f"Forwarded message: {forwarded_message}")
            try:
                # 获取机器人的响应，等待30秒
                response = await asyncio.wait_for(conv.get_response(forwarded_message.id), timeout=random.randint(5, 10))

                # print(f"Response: {response}")
            except asyncio.TimeoutError:
                # 如果超时，发送超时消息
                # await self.client.send_message(forwarded_message.chat_id, "the bot was timeout", reply_to=message.id)
                print("Response timeout.")
                #return
            print(f"Response: {response}\r\n\r\n")

           
                     
            
            
        
    async def shellbot(self,message):
        
        bot_title = "She11PostBot"
        try:
           
            if message.source_bot_id == '7294369541':
                bot_title = "She11PostBot"
            elif message.source_bot_id == '7717423153':
                bot_title = "bujidaobot"
        except Exception as e:
            print(f"Error: {e}")
            

        print(f"Processing Shell Fetch --- botTitle: {bot_title} {message.text}")
            
        async with self.client.conversation(bot_title) as conv:
            # 根据bot_username 找到 wp_bot 中对应的 bot_name = bot_username 的字典
            
            # 发送消息到机器人
            forwarded_message = await conv.send_message(message.text)
            bj_file_id = None
            bj_file_id = message.text.replace("/start file_", "")

            response =  None
            updateNoneDate = True

            # print(f"Forwarded message: {forwarded_message}")
            try:
                # 获取机器人的响应，等待30秒
                response = await asyncio.wait_for(conv.get_response(forwarded_message.id), timeout=random.randint(5, 10))

                # print(f"Response: {response}")
            except asyncio.TimeoutError:
                # 如果超时，发送超时消息
                # await self.client.send_message(forwarded_message.chat_id, "the bot was timeout", reply_to=message.id)
                print("Response timeout.")
                #return
            # print(f"Response: {response}\r\n\r\n")

            if not response:
                updateNoneDate = True
            elif "请求的文件不存在或已下架" in response.text:
                updateNoneDate = True
                     
            elif response.media:
                
                if isinstance(response.media, types.MessageMediaPhoto):
                    updateNoneDate = False
                    # 处理图片
                    photo = response.media.photo

                    # **Step 1: 取得 content1 和 user_name**
                    content1 = response.text
                    user_name = None
                    user_fullname = None

                    if "Posted by" in response.text:
                        print("response.text:", response.text)

                        parts = response.text.split("Posted by", 1)  # 只分割一次
                        # content1 = parts[0].replace("\n", "").strip()  # 去掉所有换行符
                        content1 = self.limit_visible_chars(parts[0].replace("__", "").strip(),200) # 去掉所有换行符

                        # 获取 "Posted by" 之后的文本
                        after_posted_by = parts[1].strip()

                        # 将after_posted_by 以 /n 分割
                        after_posted_by_parts = after_posted_by.split("\n")
                        print("after_posted_by_parts:", after_posted_by_parts)


                        # 提取 Markdown 链接文本内容（去除超链接）
                        match = re.search(r"\[__(.*?)__\]", after_posted_by_parts[0])
                        print("match:", match)
                        if match:
                            user_fullname = match.group(1)  # 取得用户名
                    else:
                        content1 = self.limit_visible_chars(content1,200)
                            

                    # **Step 2: 取得 enc_user_id**
                    enc_user_id = None
                    for entity in response.entities or []:
                        if isinstance(entity, types.MessageEntityTextUrl):
                            url = entity.url
                            if url.startswith("https://t.me/She11PostBot?start=up_"):
                                enc_user_id = url.split("up_")[1]  # 取得 up_ 后的字串
                                break

                    # **Step 3: 取得 fee & bj_file_id**
                    fee = None
                    
                    if response.reply_markup:
                        for row in response.reply_markup.rows:
                            for button in row.buttons:
                                if isinstance(button, types.KeyboardButtonCallback) and "💎" in button.text:
                                    fee = button.text.split("💎")[1].strip()  # 获取💎后的数字
                                    callback_data = button.data.decode()
                                    if callback_data.startswith("buy@file@"):
                                        bj_file_id = callback_data.split("buy@file@")[1]
                                    break

                    # **Step 4: 提取 file_size, duration, buy_time**
                    file_size, duration, buy_time = None, None, None
                    size_match = re.search(r"💾([\d.]+ (KB|MB|GB))", response.text)
                    duration_match = re.search(r"🕐([\d:]+)", response.text)
                    buy_time_match = re.search(r"🛒(\d+)", response.text)

                    if size_match:
                        file_size = size_match.group(1)  # 提取 MB 数字
                    if duration_match:
                        duration = self.convert_duration_to_seconds(duration_match.group(1))
                    if buy_time_match:
                        buy_time = buy_time_match.group(1)  # 提取购买次数

                    # **Tag**
                    

                    # 输入的字符串
                    
                    # 使用正则表达式查找所有的 hashtag
                    hashtags = re.findall(r'#\S+', response.text)

                    # 输出结果为一个字串
                    tag_result = ' '.join(hashtags)
                    
                    # print(f"{message}")
                    print(f"4---file_size: {file_size}")

                    # 确保目录存在
                    os.makedirs('./matrial', exist_ok=True)

                    # 指定文件路径（使用原文件名或自定义命名）
                    photo_filename = f"{bot_title}_{bj_file_id}.jpg"  # 你也可以用其他命名方式
                    photo_path = os.path.join('./matrial', photo_filename)
                    
                    photo_path = await self.client.download_media(photo, file=photo_path)
                    # photo_path = await self.client.download_media(photo)
                    
                    print(f"5.2---Photo path: {photo_path}\r\n")
                    # 计算图片的感知哈希值
                    image_hash = await self.get_image_hash(photo_path)
                    print(f"Image hash: {image_hash}")

                    # **Step 5: 组装 JSON**
                    caption_json = json.dumps({
                        "content": content1,
                        'enc_user_id': enc_user_id,
                        "user_id": message.user_id,
                        "user_fullname": user_fullname,
                        "fee": fee,
                        "bj_file_id": bj_file_id,
                        "estimated_file_size": int(self.convert_to_bytes(file_size)),
                        "duration": duration,
                        "number_of_times_sold": buy_time,
                        "tag": tag_result,
                        "source_bot_id": message.source_bot_id,
                        "source_chat_id": message.source_chat_id,
                        "source_message_id": message.source_message_id,
                        "thumb_hash": image_hash
                    }, ensure_ascii=False, indent=4)

                    print("caption_json:", caption_json)

                    # self.scrap_count += 1

                    await self.save_scrap(self.message, caption_json, response)
                    
                    # **Step 7: 发送图片到用户 6941890966**
                    if response.media and isinstance(response.media, types.MessageMediaPhoto):
                        
                        to_chat_id = 2008008502
                        try:
                            await self.client.send_file(
                                to_chat_id,  # 发送到爬略图
                                photo,  # 发送最大尺寸图片
                                disable_notification=False,  # 禁用通知
                                parse_mode='html',
                                caption=caption_json  # 发送 JSON 作为 caption
                            )
                           
                           
                           
                        except ChatForwardsRestrictedError:
                            await self.client.send_file(
                                to_chat_id,
                                photo_path,
                                disable_notification=False,
                                parse_mode='html',
                                caption=caption_json
                            )
                            


                            

      
                    
              
            else:
                print(f"Received non-media and non-text response {message.source_bot_id} / {message.text}")


            if updateNoneDate:
                start_key = message.text.replace("/start ", "")

                scrap = Scrap.select().where(
                    (Scrap.start_key == start_key)
                    & (Scrap.source_bot_id == message.source_bot_id)
                ).first()

                if scrap:
                    if scrap.thumb_hash != "NOEXISTS":
                        scrap.thumb_hash = "NOEXISTS" 
                        scrap.save()
                        print(f"1请求的文件不存在或已下架 {message.text} - {start_key}")
                    else:
                        print(f"2请求的文件不存在或已下架 {message.text} - {start_key}")
                        pass       
            
        





    async def safe_forward_or_send(self, client, message_id, from_chat_id, to_chat_id, material, caption_json):
        try:
            # 处理单个媒体和多个媒体（album）
            if isinstance(material, list):  # 如果是列表（album）
                print(f"📤 发送 Album，共 {len(material)} 个媒体")
            else:  # 如果是单个媒体
                print("📤 发送单个媒体")


            # 直接尝试转发消息

            await client.send_file(
                to_chat_id,  # 发送到爬略图
                material,  # 发送最大尺寸图片
                disable_notification=False,  # 禁用通知
                parse_mode='html',
                caption=caption_json  # 发送 JSON 作为 caption
            )
#135622

            # await client.forward_messages(to_chat_id, message_id, from_chat_id)
            print("✅ 成功转发消息！")
        except ChatForwardsRestrictedError:
            print(f"⚠️ 该消息禁止转发，尝试重新发送...{message_id}")
            await self.fetch_and_send(client, from_chat_id, message_id, to_chat_id, material, caption_json)

    async def send_fake_callback(self, client, chat_id, message_id, button_data, times):
        # 模拟按钮数据
        # fake_data = "get_file_set@401@3".encode()  # 转换为 bytes
        fake_data_str = await self.modify_button_data(button_data, times)
        fake_data  = fake_data_str.encode()  # 转换为 bytes
        print(f"模拟发送回调请求，数据: {fake_data.decode()}")

        try:
            # 发送回调请求，模拟点击按钮
            await client(GetBotCallbackAnswerRequest(
                peer=chat_id,       # 聊天 ID
                msg_id=message_id,  # 关联的消息 ID
                data=fake_data      # 模拟的按钮数据
            ))
            print("✅ 成功发送回调请求")
        except Exception as e:
            print(f"⚠️ 发送回调请求失败: {e}")


    async def fetch_messages_and_load_more(self, client, chat_id, base_button_data, caption_json, times):
        album = []
        button_message_id = 0
        choose_button_data = await self.modify_button_data(base_button_data, times)
        album_messages = await client.get_messages(chat_id, limit=15)
        for msg in album_messages:
            # 检查当前消息的 grouped_id 是否与目标消息相同
            if msg.reply_markup:
                for row in msg.reply_markup.rows:
                    for button in row.buttons:
                        if isinstance(button, KeyboardButtonCallback) and button.text == "加载更多":
                            button_data = button.data.decode()
                            if choose_button_data in button_data:
                                print(f"按钮数据: {button_data}")
                                current_button = button
                                button_message_id = msg.id
                            break
            if msg.media:
                new_group = None
                if hasattr(msg, 'grouped_id') and msg.grouped_id:
                    if new_group == None:
                        new_group = msg.grouped_id


                    if msg.grouped_id == new_group:
                        # 如果相同，则将该消息添加到相册列表中
                        album.append(msg)
        
        # print(f"\r\nAlbum: {album}",flush=True)
        if album:
            await asyncio.sleep(0.5)  # 间隔80秒
            last_message_id = max(row.id for row in album)
            # await client.send_file(self.setting['warehouse_chat_id'], album, reply_to=message.id, caption=caption_text, parse_mode='html')
            try:
                result_send = await client.send_file(
                    2038577446, 
                    album, 
                    disable_notification=False,  # 禁用通知
                    parse_mode='html',
                    caption=caption_json  # 发送 JSON 作为 caption
                    )
                
                await self.send_fake_callback(client, chat_id, button_message_id, button_data, times)
            except Exception as e:
                pass
    
    async def fetch_and_send(self, client, from_chat_id, message_id, to_chat_id, material, caption_json):
        """如果消息被保护，就先下载后重新发送"""

        new_material = []  # 存储下载后的文件路径
        message_single = await client.get_messages(from_chat_id, ids=message_id)
        # 处理单个文件和 album
        if isinstance(material, list):  # Album
            for message in material:
                if message.media:
                    file_path = await message.download_media()
                    new_material.append(file_path)  # 追加到列表
        elif message_single.media:  # 单个文件
            file_path = await message_single.download_media()
            new_material = file_path  # 直接赋值为字符串路径

        # 重新发送
        if new_material:
            parsed_json = json.loads(caption_json)
            parsed_json["protect"]="1"

            if "闪照模式5秒后此消息自动销毁" in parsed_json:
                parsed_json["flash"]="1"


            caption_json2 = json.dumps(parsed_json, ensure_ascii=False, indent=4)

            await client.send_file(
                to_chat_id,
                new_material,
                disable_notification=False,
                parse_mode='html',
                caption=caption_json2
            )
            print("✅ 重新发送成功！")
        else:
            print("❌ 无法发送，未找到可用媒体")


    def limit_visible_chars(self,text: str, max_chars: int = 300) -> str:
        count = 0
        result = ''
        for char in text:
            # 跳过控制字符（如换行、回车等）
            if unicodedata.category(char)[0] == 'C':
                result += char
                continue
            count += 1
            result += char
            if count >= max_chars:
                break
        return result

    def convert_duration_to_seconds(self,duration):
        parts = list(map(int, duration.split(":")))
        return sum(x * 60 ** i for i, x in enumerate(reversed(parts)))
    
    async def get_image_hash(self,image_path):
        """计算图片的感知哈希值"""
        img = PILImage.open(image_path)
        return str(imagehash.phash(img))  # 使用感知哈希值
    

    def convert_to_bytes(self,size_str):
        # 定义单位转换字典
        unit_to_bytes = {
            'B': 1,
            'KB': 1024,
            'MB': 1024 ** 2,
            'GB': 1024 ** 3,
            'TB': 1024 ** 4
        }

        try:
            # 匹配数字和单位
            size, unit = size_str.split()

            # 转换为数字并查找单位对应的字节数
            size = float(size)
            bytes_value = size * unit_to_bytes[unit.upper()]
        except Exception as e:
            print(f"Error: {e}")
            bytes_value = 0
            
        return bytes_value
    

    async def save_scrap(self, message, caption_json, response):
        # 查找是否已经存在相应 chat_id 的记录

       

        # 确保 message 是 Telethon Message 对象
        if message and hasattr(message, 'peer_id'):
            chat_id = message.peer_id.channel_id
        else:
            return  # 如果没有 channel_id 属性，退出

      
       
        record, created = ScrapProgress.get_or_create(
            chat_id=message.peer_id.channel_id,  # 使用 channel_id 作为 chat_id
            api_id=self.extra_data['app_id']
        )

        # 更新 message_id 和 caption_json
        record.message_id = message.id
        #  record.update_datetime 当前时间
        record.update_datetime = datetime.now()
        record.save()

        # if created:
        #     self.logger.info(f"New record created for chat_id: {message.peer_id.channel_id}")
        # else:
        #     self.logger.info(f"Record updated for chat_id: {message.peer_id.channel_id}")
