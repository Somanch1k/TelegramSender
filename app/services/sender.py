import asyncio

from telethon.errors import FloodWaitError

from app.config import get_now


class RepeatingSender:
    """Sends messages concurrently to each selected group at fixed intervals, supporting multiple parallel slots."""

    def __init__(self, telegram, logger):
        self.telegram = telegram
        self.logger = logger
        self._slots = {}

    @property
    def is_running(self):
        return any(self.is_slot_running(slot_id) for slot_id in list(self._slots.keys()))

    def is_slot_running(self, slot_id=1):
        slot = self._slots.get(slot_id)
        return slot is not None and slot.get("task") is not None and not slot["task"].done()

    def get_active_chat_ids(self, exclude_slot=None):
        active = set()
        for slot_id, slot in list(self._slots.items()):
            if slot_id != exclude_slot and self.is_slot_running(slot_id):
                active.update(slot["chat_ids"])
        return active

    def start(self, chat_ids, text, interval_seconds, group_titles, slot_id=1):
        if self.is_slot_running(slot_id):
            raise RuntimeError(f"Рассылка {slot_id} уже запущена. Сначала выполните её остановку.")

        active_elsewhere = self.get_active_chat_ids(exclude_slot=slot_id)
        overlapping = set(chat_ids) & active_elsewhere
        if overlapping:
            overlapping_names = [str(group_titles.get(cid, cid)) for cid in overlapping]
            names_str = ", ".join(overlapping_names)
            raise ValueError(
                f"Нельзя запускать параллельную рассылку в одни и те же группы в одно и то же время.\n"
                f"Группы уже участвуют в другой активной рассылке: {names_str}"
            )

        stats = {
            "started_at": get_now(),
            "finished_at": None,
            "interval": interval_seconds,
            "sent": {chat_id: 0 for chat_id in chat_ids},
            "titles": group_titles,
            "text": text,
        }
        task = asyncio.create_task(self._send_loop(slot_id, chat_ids, text, interval_seconds))
        self._slots[slot_id] = {
            "task": task,
            "stats": stats,
            "chat_ids": chat_ids,
        }

    async def stop(self, slot_id=None):
        if slot_id is not None:
            return await self._stop_slot(slot_id)

        all_stats = {}
        for sid in list(self._slots.keys()):
            stats = await self._stop_slot(sid)
            if stats:
                all_stats[sid] = stats
        return all_stats

    async def _stop_slot(self, slot_id):
        if not self.is_slot_running(slot_id):
            return None

        slot = self._slots[slot_id]
        task = slot["task"]
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        finally:
            slot["stats"]["finished_at"] = get_now()
            stats = slot["stats"]
            del self._slots[slot_id]
        return stats

    async def _send_loop(self, slot_id, chat_ids, text, interval_seconds):
        try:
            while True:
                await asyncio.gather(
                    *(self._send_to_group(slot_id, chat_id, text) for chat_id in chat_ids)
                )
                await asyncio.sleep(interval_seconds)
        except asyncio.CancelledError:
            self.logger.info(f"Рассылка {slot_id} остановлена.")
            raise
        except Exception:
            self.logger.exception(f"Рассылка {slot_id} остановлена из-за ошибки.")
            if slot_id in self._slots and self._slots[slot_id]["stats"]:
                self._slots[slot_id]["stats"]["finished_at"] = get_now()


    async def _send_to_group(self, slot_id, chat_id, text):
        try:
            await self.telegram.send_message(chat_id, text)
            if slot_id in self._slots:
                self._slots[slot_id]["stats"]["sent"][chat_id] += 1
            self.logger.info("Рассылка %s: Сообщение отправлено в группу %s", slot_id, chat_id)
        except FloodWaitError as error:
            self.logger.warning("Telegram ограничил отправку в %s на %s сек.", chat_id, error.seconds)
        except Exception:
            self.logger.exception("Не удалось отправить сообщение в группу %s.", chat_id)

    @staticmethod
    def format_stats(stats, slot_id=1):
        started = stats["started_at"].strftime("%d.%m.%Y %H:%M:%S")
        finished = stats["finished_at"].strftime("%d.%m.%Y %H:%M:%S")
        duration = str(stats["finished_at"] - stats["started_at"]).split(".")[0]
        lines = [
            f"⏹ Рассылка {slot_id} завершена.",
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

