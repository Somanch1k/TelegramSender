import asyncio
from datetime import datetime, timedelta

from telethon import events

from app.config import CONTROL_GROUP_ID, TIMEZONE_NAME, get_now


class CommandHandler:
    def __init__(self, telegram, app, trusted_bot_username=None):
        self.telegram = telegram
        self.app = app
        self.logger = app.logger
        self._groups_by_number = {}
        self.trusted_bot_username = (trusted_bot_username or "").lower()

    def register(self):
        @self.telegram.client.on(events.NewMessage(chats=CONTROL_GROUP_ID))
        async def commands(event):
            text = event.raw_text.strip()
            sender = await event.get_sender()
            username = (getattr(sender, "username", None) or "").lower()
            is_interface_bot = username == self.trusted_bot_username
            if not username or (not is_interface_bot and not self.app.admins.has_access(username)):
                await event.reply("У вас нет доступа к командам отправки.")
                return

            if text == "/ping":
                await event.reply("🏓 Pong!")
            elif text == "/time":
                now = get_now()
                await event.reply(
                    f"🕒 Время программы: {now.strftime('%H:%M:%S')}\n"
                    f"📅 Дата: {now.strftime('%d.%m.%Y')}\n"
                    f"🌍 Часовой пояс: {TIMEZONE_NAME}"
                )
            elif text == "/status":
                selected = self.app.groups.get_selected_groups()
                s1 = "запущена" if self.app.sender.is_slot_running(1) else "не запущена"
                s2 = "запущена" if self.app.sender.is_slot_running(2) else "не запущена"
                await event.reply(
                    f"🟢 Приложение работает.\nВыбрано групп: {len(selected)}\n"
                    f"Интервал: {self.app.groups.get_interval()} сек.\n"
                    f"Рассылка 1: {s1}\n"
                    f"Рассылка 2: {s2}"
                )
            elif text == "/groups":
                await self._show_groups(event)
            elif text.startswith("/select "):
                await self._select_groups(event, text)
            elif text == "/selected":
                await self._show_selected(event)
            elif text.startswith("/interval "):
                await self._set_interval(event, text.removeprefix("/interval ").strip())
            elif text.startswith("/schedule "):
                await self._schedule(event, text)
            elif text == "/schedule_status":
                await self._schedule_status(event)
            elif text.startswith("/schedule_cancel"):
                await self._schedule_cancel(event, text)
            elif text.startswith("/send "):
                await self._send_once(event, text.removeprefix("/send ").strip())
            elif text.startswith("/start2 "):
                await self._start(event, text.removeprefix("/start2 ").strip(), slot_id=2)
            elif text.startswith("/start "):
                await self._start(event, text.removeprefix("/start ").strip(), slot_id=1)
            elif text in {"/stop", "/stop1"}:
                self.app.scheduler.forget_running_plan(slot_id=1)
                stats = await self.app.sender.stop(slot_id=1)
                await event.reply(self.app.sender.format_stats(stats, slot_id=1) if stats else "Рассылка 1 сейчас не запущена.")
            elif text == "/stop2":
                self.app.scheduler.forget_running_plan(slot_id=2)
                stats = await self.app.sender.stop(slot_id=2)
                await event.reply(self.app.sender.format_stats(stats, slot_id=2) if stats else "Рассылка 2 сейчас не запущена.")
            elif text == "/stop_all":
                self.app.scheduler.forget_running_plan(slot_id=1)
                self.app.scheduler.forget_running_plan(slot_id=2)
                all_stats = await self.app.sender.stop(slot_id=None)
                if not all_stats:
                    await event.reply("Активных рассылок сейчас нет.")
                else:
                    lines = [self.app.sender.format_stats(st, slot_id=sid) for sid, st in all_stats.items()]
                    await event.reply("\n\n".join(lines))
            elif text == "/admins":
                await self._show_admins(event)
            elif text.startswith("/admin_add "):
                await self._add_admin(event, username, text.removeprefix("/admin_add ").strip())
            elif text.startswith("/admin_remove "):
                await self._remove_admin(event, username, text.removeprefix("/admin_remove ").strip())
            elif text == "/help":
                await event.reply(
                    "📋 Команды\n\n/groups — показать группы\n/select 1 3 — выбрать группы\n"
                    "/selected — выбранные группы\n/interval 10 — интервал между рассылками\n"
                    "/send ТЕКСТ — отправить один раз\n/start ТЕКСТ — начать рассылку 1\n"
                    "/start2 ТЕКСТ — начать паралельную рассылку 2\n"
                    "/stop (или /stop1) — остановить рассылку 1\n"
                    "/stop2 — остановить рассылку 2\n"
                    "/stop_all — остановить все рассылки\n/status\n/time — время, которое видит программа\n\n"
                    "/cancel — отменить текущий ввод в меню\n\n"
                    "/schedule 18:30 300 10 ТЕКСТ — запланировать рассылку\n"
                    "/schedule_status — показать планы\n"
                    "/schedule_cancel ID — отменить план\n\n"
                    "Только для владельца:\n/admins\n/admin_add @username\n/admin_remove @username"
                )

    async def _show_groups(self, event):
        dialogs = await self.telegram.get_dialogs()
        groups = [dialog for dialog in dialogs if dialog.is_group]
        self._groups_by_number = {number: dialog for number, dialog in enumerate(groups, 1)}
        selected = set(self.app.groups.get_selected_groups())
        if not groups:
            await event.reply("Группы не найдены.")
            return
        lines = ["Выберите несколько групп: /select 1 2 3"]
        lines.extend(f"{'✅' if dialog.id in selected else '▫️'} {number}. {dialog.name}" for number, dialog in self._groups_by_number.items())
        await event.reply("\n".join(lines))

    async def _select_groups(self, event, text):
        try:
            numbers = [int(value) for value in text.split()[1:]]
            dialogs = [self._groups_by_number[number] for number in dict.fromkeys(numbers)]
        except (KeyError, ValueError):
            await event.reply("Сначала выполните /groups, затем укажите номера: /select 1 2 3")
            return
        if not dialogs:
            await event.reply("Укажите хотя бы один номер группы.")
            return
        self.app.groups.set_selected_groups(dialogs)
        await event.reply("✅ Выбраны группы:\n" + "\n".join(f"• {dialog.name}" for dialog in dialogs))

    async def _show_selected(self, event):
        ids = self.app.groups.get_selected_groups()
        if not ids:
            await event.reply("Группы ещё не выбраны. Используйте /groups.")
            return
        saved_groups = {group["chat_id"]: group["title"] for group in self.app.groups.get_groups()}
        await event.reply("Выбраны:\n" + "\n".join(f"• {saved_groups.get(chat_id, chat_id)}" for chat_id in ids))

    async def _set_interval(self, event, value):
        try:
            seconds = int(value)
        except ValueError:
            await event.reply("Укажите целое число секунд: /interval 10")
            return
        if seconds < 1:
            await event.reply("Интервал должен быть не меньше 1 секунды.")
            return
        self.app.groups.set_interval(seconds)
        await event.reply(f"✅ Интервал между рассылками: {seconds} сек.")

    async def _schedule(self, event, text):
        parts = text.split(maxsplit=4)
        if len(parts) != 5:
            await event.reply("Формат: /schedule ЧЧ:ММ ДЛИТЕЛЬНОСТЬ_СЕК ИНТЕРВАЛ_СЕК ТЕКСТ")
            return
        try:
            start_time = datetime.strptime(parts[1], "%H:%M").time()
            duration_seconds = int(parts[2])
            interval_seconds = int(parts[3])
        except ValueError:
            await event.reply("Время укажите как ЧЧ:ММ, а длительность и интервал — целыми секундами.")
            return
        if duration_seconds < 1 or interval_seconds < 1:
            await event.reply("Длительность и интервал должны быть не меньше 1 секунды.")
            return
        chat_ids = self.app.groups.get_selected_groups()
        if not chat_ids:
            await event.reply("Сначала выберите группы: /groups, затем /select 1 2.")
            return

        now = get_now()
        start_at = now.replace(hour=start_time.hour, minute=start_time.minute, second=0, microsecond=0)

        if start_at <= now:
            start_at += timedelta(days=1)
        titles = {group["chat_id"]: group["title"] for group in self.app.groups.get_groups()}
        try:
            plan = self.app.scheduler.schedule(start_at, duration_seconds, chat_ids, parts[4], interval_seconds, titles)
        except ValueError as error:
            await event.reply(f"Невозможно добавить план: {error}.")
            return
        await event.reply(
            f"✅ План {plan['id']}: {start_at.strftime('%d.%m.%Y %H:%M')}–{plan['end_at'].strftime('%H:%M')}.\n"
            f"Групп: {len(chat_ids)}, длительность: {duration_seconds} сек., интервал: {interval_seconds} сек."
        )

    async def _schedule_status(self, event):
        plans = self.app.scheduler.get_plans()
        if not plans:
            await event.reply("Запланированных рассылок нет.")
            return
        lines = ["Запланированные рассылки:"]
        lines.extend(
            f"• {plan['id']}: {plan['start_at'].strftime('%d.%m.%Y %H:%M')}–{plan['end_at'].strftime('%H:%M')} "
            f"({len(plan['chat_ids'])} групп)"
            for plan in plans
        )
        await event.reply("\n".join(lines))

    async def _schedule_cancel(self, event, text):
        parts = text.split(maxsplit=1)
        if len(parts) != 2:
            await event.reply("Укажите ID плана из /schedule_status: /schedule_cancel ABC123")
            return
        if self.app.scheduler.cancel(parts[1].strip()):
            await event.reply("✅ Запланированная рассылка отменена.")
        else:
            await event.reply("План не найден или уже запущен. Запущенную рассылку остановите командой /stop.")

    async def _send_once(self, event, message):
        if not message:
            await event.reply("Укажите текст: /send Ваше сообщение")
            return
        chat_ids = self.app.groups.get_selected_groups()
        if not chat_ids:
            await event.reply("Сначала выберите группы: /groups, затем /select 1 2.")
            return
        results = await asyncio.gather(*(self.telegram.send_message(chat_id, message) for chat_id in chat_ids), return_exceptions=True)
        sent = sum(not isinstance(result, Exception) for result in results)
        await event.reply(f"✅ Сообщение отправлено в {sent} из {len(chat_ids)} групп.")

    async def _start(self, event, message, slot_id=1):
        if not message:
            cmd = "/start2" if slot_id == 2 else "/start"
            await event.reply(f"Укажите текст: {cmd} Ваше сообщение")
            return
        chat_ids = self.app.groups.get_selected_groups()
        if not chat_ids:
            await event.reply("Сначала выберите группы: /groups, затем /select 1 2.")
            return
        titles = {group["chat_id"]: group["title"] for group in self.app.groups.get_groups()}
        interval = self.app.groups.get_interval()
        stop_cmd = f"/stop{slot_id}" if slot_id == 2 else "/stop"
        try:
            self.app.sender.start(chat_ids, message, interval, titles, slot_id=slot_id)
            await event.reply(f"✅ Рассылка {slot_id} запущена в {len(chat_ids)} групп. Интервал: {interval} сек. Остановка: {stop_cmd}")
        except (RuntimeError, ValueError) as error:
            await event.reply(f"❌ {error}")


    async def _show_admins(self, event):
        admins = self.app.admins.get_admins()
        await event.reply("Администраторы:\n" + "\n".join(f"• @{admin['username']} — {admin['role']}" for admin in admins))

    async def _add_admin(self, event, requester, username):
        if not self.app.admins.is_owner(requester):
            await event.reply("Назначать администраторов может только владелец.")
            return
        username = username.lstrip("@").strip().lower()
        if not username or " " in username:
            await event.reply("Укажите username: /admin_add @username")
            return
        self.app.admins.add_admin(username)
        await event.reply(f"✅ @{username} назначен администратором.")

    async def _remove_admin(self, event, requester, username):
        if not self.app.admins.is_owner(requester):
            await event.reply("Снимать права может только владелец.")
            return
        username = username.lstrip("@").strip().lower()
        if not username or " " in username:
            await event.reply("Укажите username: /admin_remove @username")
            return
        if self.app.admins.is_owner(username):
            await event.reply("Нельзя снять права владельца.")
            return
        if not self.app.admins.is_admin(username):
            await event.reply(f"@{username} не является администратором.")
            return
        self.app.admins.remove_admin(username)
        await event.reply(f"✅ Права администратора для @{username} сняты.")
