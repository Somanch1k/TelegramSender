import asyncio
from datetime import datetime

from telethon.errors import FloodWaitError


class RepeatingSender:
    """Sends a message concurrently to each selected group at a fixed interval."""

    def __init__(self, telegram, logger):
        self.telegram = telegram
        self.logger = logger
        self._task = None
        self.stats = None

    @property
    def is_running(self):
        return self._task is not None and not self._task.done()

    def start(self, chat_ids, text, interval_seconds, group_titles):
        if self.is_running:
            raise RuntimeError("Рассылка уже запущена. Сначала выполните /stop.")

        self.stats = {
            "started_at": datetime.now().astimezone(),
            "finished_at": None,
            "interval": interval_seconds,
            "sent": {chat_id: 0 for chat_id in chat_ids},
            "titles": group_titles,
        }
        self._task = asyncio.create_task(self._send_loop(chat_ids, text, interval_seconds))

    async def stop(self):
        if not self.is_running:
            return None

        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        finally:
            self._task = None
            self.stats["finished_at"] = datetime.now().astimezone()
        return self.stats

    async def _send_loop(self, chat_ids, text, interval_seconds):
        try:
            while True:
                await asyncio.gather(
                    *(self._send_to_group(chat_id, text) for chat_id in chat_ids)
                )
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            self.logger.info("Рассылка остановлена.")
            raise
        except Exception:
            self.logger.exception("Рассылка остановлена из-за ошибки.")
            if self.stats:
                self.stats["finished_at"] = datetime.now().astimezone()

    async def _send_to_group(self, chat_id, text):
        try:
            await self.telegram.send_message(chat_id, text)
            self.stats["sent"][chat_id] += 1
            self.logger.info("Сообщение отправлено в группу %s", chat_id)
        except FloodWaitError as error:
            self.logger.warning("Telegram ограничил отправку в %s на %s сек.", chat_id, error.seconds)
        except Exception:
            self.logger.exception("Не удалось отправить сообщение в группу %s.", chat_id)

    @staticmethod
    def format_stats(stats):
        started = stats["started_at"].strftime("%d.%m.%Y %H:%M:%S")
        finished = stats["finished_at"].strftime("%d.%m.%Y %H:%M:%S")
        duration = str(stats["finished_at"] - stats["started_at"]).split(".")[0]
        lines = [
            "⏹ Рассылка завершена.",
            f"Начало: {started}",
            f"Конец: {finished}",
            f"Длительность: {duration}",
            "",
            "Отправлено:",
        ]
        lines.extend(
            f"• {stats['titles'].get(chat_id, chat_id)}: {count}"
            for chat_id, count in stats["sent"].items()
        )
        return "\n".join(lines)
