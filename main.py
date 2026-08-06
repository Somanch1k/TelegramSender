import asyncio

from app.application import Application
from app.handlers.command_handler import CommandHandler
from app.services.telegram_client import TelegramClientManager
from app.services.sender import RepeatingSender
from app.scheduler.scheduler import BroadcastScheduler
from app.config import BOT_TOKEN, CONTROL_GROUP_ID
from app.services.interface_bot import InterfaceBot


async def main():

    app = Application()

    telegram = TelegramClientManager()

    await telegram.start()

    me = await telegram.get_me()

    if not me.username:
        raise ValueError(
            "У подключённого Telegram-аккаунта должен быть username (@имя) для управления доступом."
        )

    username = me.username.lower()

    if app.admins.setup_owner(username):
        app.logger.info(f"{username} назначен владельцем проекта.")

    app.logger.info(f"Авторизован как {me.first_name}")

    from app.services.campaign_engine import CampaignEngine

    app.sender = RepeatingSender(telegram, app.logger)
    app.scheduler = BroadcastScheduler(telegram, app.sender, app.logger, CONTROL_GROUP_ID)
    app.scheduler.start()

    app.campaign_engine = CampaignEngine(telegram, app.database, app.logger, CONTROL_GROUP_ID, app.scheduler)
    app.campaign_engine.reload_all()

    app.interface_bot = InterfaceBot(
        BOT_TOKEN, CONTROL_GROUP_ID, app.admins, app.scheduler,
        app.groups, app.sender, telegram, app.logger, campaign_engine=app.campaign_engine,
        database=app.database,
    )
    await app.interface_bot.initialize()

    commands = CommandHandler(telegram, app, app.interface_bot.username)


    commands.register()
    await app.interface_bot.start()

    app.logger.info("Ожидание команд...")

    try:
        await telegram.run_forever()
    finally:
        await app.sender.stop()
        await app.interface_bot.stop()
        app.scheduler.shutdown()


if __name__ == "__main__":
    asyncio.run(main())
