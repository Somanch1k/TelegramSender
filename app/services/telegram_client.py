from telethon import TelegramClient, events

from app.config import API_ID, API_HASH, SESSION_FILE


class TelegramClientManager:
    def __init__(self):
        if not API_ID or not API_HASH:
            raise ValueError("API_ID или API_HASH не указаны в .env")

        self.client = TelegramClient(
            str(SESSION_FILE),
            int(API_ID),
            API_HASH,
        )

    async def start(self):
        await self.client.start()

    async def stop(self):
        await self.client.disconnect()

    async def get_me(self):
        return await self.client.get_me()

    async def get_dialogs(self):
        return await self.client.get_dialogs()

    async def send_message(self, entity, text):
        return await self.client.send_message(entity, text)

    def on_new_message(self, callback, chats=None):
        self.client.add_event_handler(
            callback,
            events.NewMessage(chats=chats)
        )

    async def run_forever(self):
        await self.client.run_until_disconnected()