from telethon import TelegramClient

# Укажите ваши API_ID и API_HASH (можно взять с my.telegram.org)
API_ID = 33417557  # Замените на ваш API ID (число)
API_HASH = "0be459e9cc934817b6f217ad41c378ae"  # Замените на ваш API Hash (строка)

# "my_session" — это имя файла, который создастся (my_session.session)
client = TelegramClient("my_session", API_ID, API_HASH)


async def main():
    print("Авторизация прошла успешно!")


with client:
    client.loop.run_until_complete(main())