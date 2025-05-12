import random
import re
from telethon.tl.types import MessageMediaPhoto, MessageMediaDocument, MessageMediaWebPage
from utils.media_utils import safe_forward_or_send
from model.scrap_config import ScrapConfig  # ✅ Peewee ORM model
from model.media_index import MediaIndex  # ✅ Peewee ORM model
from peewee import DoesNotExist
from utils.media_utils import generate_media_key
from utils.send_safe import wait_for_send_slot

class HandlerPrivateMessageClass:
    def __init__(self, client, entity, message, extra_data):
        self.client = client
        self.entity = entity
        self.message = message
        self.extra_data = extra_data
        self.delete_after_process = False
        self.forward_pattern = re.compile(r'\|_forward_\|\@(-?\d+|[a-zA-Z0-9_]+)')

    async def handle(self):
        fallback_chat_ids = self.get_fallback_chat_ids()
        forwared_success = True

        # 打印来源
        first_name = getattr(self.entity, "first_name", "") or ""
        last_name = getattr(self.entity, "last_name", "") or ""
        entity_title = f"{first_name} {last_name}".strip()
        # print(f"[User] Message from {entity_title} ({self.entity.id}): {self.message.text}")
        print(f"\r\n[User] Message from {entity_title} ({self.entity.id}): {self.message.id}")

        if self.message.media and not isinstance(self.message.media, MessageMediaWebPage):
            grouped_id = getattr(self.message, 'grouped_id', None)

            if grouped_id:
                album_messages = await self.client.get_messages(self.message.peer_id, limit=15)
                album = [msg for msg in album_messages if msg.grouped_id == grouped_id]
                if not album:
                    print("⚠️ 无法取得相册消息")
                    return

                caption = album[0].message or ""
                match = self.forward_pattern.search(caption)
                if match:
                    target_raw = match.group(1)
                    if target_raw.isdigit():
                        target_chat_id = int(target_raw)
                    else:
                        target_chat_id = target_raw.strip('@')  # 可留可不留 @
                    print(f"📌 指定转发 x chat_id={target_chat_id}")
                elif fallback_chat_ids:
                    target_chat_id = random.choice(fallback_chat_ids)
                    # print(f"🌟 無轉發標記，相簿改轉發至 chat_id={target_chat_id}", flush=True)
                else:
                    # print("⚠️ 無 chat_id 可用，跳過相簿", flush=True)
                    return

                await wait_for_send_slot(target_chat_id)
                print("\r\n")
                forwared_success = await safe_forward_or_send(
                    self.client,
                    self.message.id,
                    self.message.chat_id,
                    target_chat_id,
                    album,
                    caption
                )

                if(self.delete_after_process and forwared_success):
                    await self.safe_delete_message()

            else:
                caption = self.message.text or ""
                match = self.forward_pattern.search(caption)
                back_target_chat_id = None
                if match:
                    

                    target_raw = match.group(1)
                    if target_raw.isdigit():
                        target_chat_id = int(target_raw)
                    else:
                        target_chat_id = target_raw.strip('@')  # 可留可不留 @
                    back_target_chat_id = random.choice(fallback_chat_ids)
                    print(f"📌 指定转发 x chat_id={target_chat_id}")

                elif fallback_chat_ids:
                    target_chat_id = random.choice(fallback_chat_ids)
                    # print(f"🌟 無轉發標記，改转发至 chat_id={target_chat_id}", flush=True)
                else:
                    print("⚠️ 無 chat_id 可用，跳过消息", flush=True)
                    return

                media = self.message.media.document if isinstance(self.message.media, MessageMediaDocument) else self.message.media.photo

                media_key = generate_media_key(self.message)
                if media_key:
                    media_type, media_id, access_hash = media_key
                    exists = MediaIndex.select().where(
                        (MediaIndex.media_type == media_type) &
                        (MediaIndex.media_id == media_id) &
                        (MediaIndex.access_hash == access_hash)
                    ).exists()

                    if not exists:
                        
                        await wait_for_send_slot(target_chat_id)
                       
                        forwared_success = await safe_forward_or_send(
                            self.client,
                            self.message.id,
                            self.message.chat_id,
                            target_chat_id,
                            media,
                            caption
                        )

                        


                        if not forwared_success and back_target_chat_id != None:
                            await wait_for_send_slot(back_target_chat_id)
                            print("Try again:")
                            forwared_success = await safe_forward_or_send(
                                self.client,
                                self.message.id,
                                self.message.chat_id,
                                back_target_chat_id,
                                media,
                                caption
                            )


                        if forwared_success:
                            MediaIndex.create(
                            media_type=media_type,
                            media_id=media_id,
                            access_hash=access_hash
                        )

                    else:
                        print("⚠️ 已接收过该媒体，跳过处理")
                        pass

                    if(self.delete_after_process and forwared_success):
                        await self.safe_delete_message()

        elif self.message.text and self.message.text != '[~bot~]':
            await self.safe_delete_message()
        else:
            await self.safe_delete_message()
        
    def get_fallback_chat_ids(self):
        try:
            # print(f"🔍 正在查找 FORWARD_TARGETS {self.extra_data['app_id']}", flush=True)
            record = ScrapConfig.get(
                (ScrapConfig.api_id == self.extra_data['app_id']) &
                (ScrapConfig.title == 'FORWARD_TARGETS')
            )
            raw = record.value or ''
            return [int(x.strip()) for x in raw.split(',') if x.strip().isdigit()]
        except DoesNotExist:
            print("⚠️ scrap_config 中找不到 FORWARD_TARGETS")
            return []

    async def safe_delete_message(self):
        try:
            await self.client.delete_messages(self.message.chat_id, [self.message.id], revoke=True)
            print(f"🧹 成功刪除訊息C {self.message.id}（雙方）", flush=True)
        except Exception as e:
            print(f"⚠️ 刪除訊息失敗C {self.message.id}：{e}", flush=True)
