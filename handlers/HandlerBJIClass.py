import asyncio
import json
import re
from collections import defaultdict, namedtuple
from handlers.QuietQuoteGenerator import QuietQuoteGenerator
from telethon.tl.types import PeerUser, PeerChannel, KeyboardButtonCallback
from telethon import types
from telethon.errors import ChatForwardsRestrictedError,FloodWaitError
from telethon.tl.functions.messages import GetBotCallbackAnswerRequest

class HandlerBJIClass:
    def __init__(self, client, entity, message):
        self.client = client
        self.entity = entity
        self.message = message

    async def handle(self):
        quote_gen = QuietQuoteGenerator()

        if self.message.id % 237 == 0:
            await self.client.send_message(self.entity.id, quote_gen.random_quote())
            await asyncio.sleep(30)
        print(f"Message from {self.entity.title} ({self.message.id}): {self.message.text}")
        pattern = r"https://t\.me/FileDepotBot\?start=([^\s]+)"
        message_text_str = self.message.text

        if message_text_str:
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

            # //new_caption = caption_json2+ "\r\n\r\n" + "#Protect"

            # if "闪照模式5秒后此消息自动销毁" in new_caption:
                # new_caption = new_caption+ " " + "#Flash"

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

    # async def fetch_and_send(self, client, from_chat_id, message_id, to_chat_id, material, caption_json):
    #     new_material = []  # 存储下载后的文件路径
        
    #     """如果消息被保护，就下载再发送"""
    #     message = await client.get_messages(from_chat_id, ids=message_id)
        parsed_json = json.loads(caption_json)
        parsed_json["protect"]="1"
        caption_json = json.dumps(parsed_json, ensure_ascii=False, indent=4)
    #     if message.media:  # 如果消息包含媒体（图片、视频、文件）
    #         file_path = await message.download_media()  # 先下载
    #         await client.send_file(to_chat_id, file_path, caption=caption_json)  # 重新发送
    #         print("✅ 重新发送媒体成功！")
    #     elif message.text:  # 如果是纯文本
    #         await client.send_message(to_chat_id, message.text)
    #         print("✅ 重新发送文本成功！")
    #     else:
    #         print("❌ 该消息既无媒体，也无文本，无法发送")

