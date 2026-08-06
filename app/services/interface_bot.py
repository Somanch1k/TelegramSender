import asyncio
import json
from datetime import datetime
from urllib.error import URLError
from urllib.request import Request, urlopen

from app.config import get_now, TIMEZONE_NAME
from app.utils.time_parser import parse_time_range, parse_interval_to_seconds, format_seconds_to_hms, parse_time_hhmm


class InterfaceBot:
    """Bot API control panel for a Telethon-based sender."""

    def __init__(self, token, control_group_id, admins, scheduler, groups, sender, telegram, logger, campaign_engine=None, database=None):
        self.token = token
        self.control_group_id = control_group_id
        self.admins = admins
        self.scheduler = scheduler
        self.groups = groups
        self.sender = sender
        self.telegram = telegram
        self.logger = logger
        self.campaign_engine = campaign_engine
        self.db = database
        self.username = None
        self._offset = None
        self._task = None
        self._menu_message_id = None
        self._groups_by_id = {}
        self._pending = {}
        self._wizard = {}

    @property
    def enabled(self):
        return bool(self.token)

    async def initialize(self):
        if not self.enabled:
            return
        try:
            bot = await self._api("getMe")
            self.username = bot["username"].lower()
            self.logger.info("Интерфейсный бот @%s подключён.", self.username)
        except Exception:
            self.logger.exception("Не удалось подключить интерфейсного бота.")
            self.token = None

    async def start(self):
        if not self.enabled or not self.username:
            return
        self._task = asyncio.create_task(self._poll())
        await self.send_menu()

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
            self._task = None

    async def send_menu(self):
        s1_running = self.sender.is_slot_running(1)
        s2_running = self.sender.is_slot_running(2)

        if s1_running and not s2_running:
            start_btn = self._button("▶️ Начать рассылку 2", "start2")
        elif not s1_running and s2_running:
            start_btn = self._button("▶️ Начать рассылку 1", "start")
        elif not s1_running and not s2_running:
            start_btn = self._button("▶️ Начать рассылку", "start")
        else:
            start_btn = None

        row2 = [start_btn, self._button("✉️ Отправить один раз", "send")] if start_btn else [self._button("✉️ Отправить один раз", "send")]

        keyboard = [
            [self._button("📋 Группы", "groups"), self._button("📌 Выбранные", "selected")],
            row2,
            [self._button("⏱ Интервал", "interval"), self._button("🗓 Запланировать", "schedule")],
            [self._button("⚙️ Кампании", "campaigns"), self._button("🕒 Время", "time")],
            [self._button("🗓 Планы", "plans"), self._button("ℹ️ Статус", "status")],
        ]

        if s1_running and s2_running:
            keyboard.append([self._button("⏹ Остановить рассылку 1", "stop1"), self._button("⏹ Остановить рассылку 2", "stop2")])
            keyboard.append([self._button("⏹ Остановить все рассылки", "stop_all")])
        elif s1_running:
            keyboard.append([self._button("⏹ Остановить рассылку", "stop1")])
        elif s2_running:
            keyboard.append([self._button("⏹ Остановить рассылку 2", "stop2")])

        now_str = get_now().strftime("%H:%M:%S")
        text = f"Панель управления рассылкой.\n🕒 Время программы: {now_str} ({TIMEZONE_NAME})\nВыберите действие:"
        if self._menu_message_id:
            try:
                await self._edit_message(self._menu_message_id, text, keyboard)
                return
            except Exception:
                self._menu_message_id = None
        message = await self._send_message(self.control_group_id, text, keyboard)
        self._menu_message_id = message["message_id"]

    async def _show_time(self):
        now_dt = get_now()
        msg = (
            f"🕒 **Текущее время программы**: {now_dt.strftime('%H:%M:%S')}\n"
            f"📅 Дата: {now_dt.strftime('%d.%m.%Y')}\n"
            f"🌐 Часовой пояс: {TIMEZONE_NAME}\n\n"
            f"Сверьте это время с вашим реальным временем перед созданием расписаний."
        )
        await self._send_message(self.control_group_id, msg)

    async def _show_campaigns(self):
        if not self.db:
            await self._send_message(self.control_group_id, "База данных недоступна.")
            return
        camps = self.db.get_campaigns()
        keyboard = [
            [self._button("➕ Создать кампанию", "wizard_start")]
        ]
        if not camps:
            await self._send_message(self.control_group_id, "Кампаний пока нет. Нажмите «Создать кампанию».", keyboard)
            return

        lines = ["⚙️ **Ваши многотекстовые кампании:**\n"]
        for c in camps:
            status = "🟢 Активна" if c["enabled"] else "⚪️ Остановлена"
            lines.append(f"• ID {c['id']}: **{c['name']}** ({c['start_time']}–{c['end_time']}) [{status}]")
            lines.append(f"  Групп: {len(c['chat_ids'])}, Сообщений: {len(c['blocks'])}")
            keyboard.append([self._button(f"🗑 Удалить #{c['id']}", f"cmp_del:{c['id']}")])

        await self._send_message(self.control_group_id, "\n".join(lines), keyboard)

    async def _start_wizard(self, user_id):
        chat_ids = self.groups.get_selected_groups()
        if not chat_ids:
            await self._send_message(self.control_group_id, "Сначала выберите группы в меню: «📋 Группы».")
            return
        self._wizard[user_id] = {
            "step": "name_window",
            "chat_ids": chat_ids,
            "blocks": [],
        }
        await self._send_message(
            self.control_group_id,
            "⚙️ **Конструктор кампании (Шаг 1 из 3)**\n\n"
            "Введите название и общее время работы кампании через дефис или пробел.\n"
            "Пример: `УтреннийПрогрев 09:00-21:00`",
            reply_markup={"force_reply": True, "input_field_placeholder": "УтреннийПрогрев 09:00-21:00"}
        )

    async def _handle_wizard_input(self, user_id, text):
        state = self._wizard.get(user_id)
        if not state:
            return

        step = state["step"]

        if step == "name_window":
            parts = text.strip().rsplit(maxsplit=1)
            if len(parts) != 2:
                await self._send_message(self.control_group_id, "Формат: `Название кампании 09:00-21:00`. Попробуйте снова.")
                return
            name = parts[0]
            try:
                t1, t2 = parse_time_range(parts[1])
            except ValueError as e:
                await self._send_message(self.control_group_id, f"❌ {e}")
                return
            if t2 <= t1:
                await self._send_message(self.control_group_id, "❌ Время окончания кампании должно быть позже времени начала.")
                return

            state["name"] = name
            state["start_time"] = t1.strftime("%H:%M")
            state["end_time"] = t2.strftime("%H:%M")
            state["step"] = "block_count"

            await self._send_message(
                self.control_group_id,
                f"✅ Кампания «{name}» ({state['start_time']}–{state['end_time']}).\n\n"
                "**Шаг 2 из 3**: Укажите количество разных сообщений (блоков), например: `3`",
                reply_markup={"force_reply": True, "input_field_placeholder": "3"}
            )

        elif step == "block_count":
            try:
                count = int(text.strip())
                if count < 1 or count > 20:
                    raise ValueError
            except ValueError:
                await self._send_message(self.control_group_id, "Укажите число от 1 до 20.")
                return
            state["target_blocks"] = count
            state["current_block"] = 1
            state["step"] = "block_window"

            await self._send_message(
                self.control_group_id,
                f"**Сообщение №1 из {count}**\n\n"
                "Введите промежуток времени для Сообщения №1 в формате `ЧЧ:ММ-ЧЧ:ММ`.\n"
                "Пример: `09:00-12:00`",
                reply_markup={"force_reply": True, "input_field_placeholder": "09:00-12:00"}
            )

        elif step == "block_window":
            try:
                t1, t2 = parse_time_range(text)
            except ValueError as e:
                await self._send_message(self.control_group_id, f"❌ {e}")
                return
            cur = state["current_block"]
            expected_start = state["start_time"] if cur == 1 else state["blocks"][-1]["block_end"]
            if t1.strftime("%H:%M") != expected_start:
                await self._send_message(
                    self.control_group_id,
                    f"❌ Сообщение №{cur} должно начинаться в {expected_start}, чтобы расписание шло без пропусков и пересечений.",
                )
                return
            if t2 <= t1:
                await self._send_message(self.control_group_id, "❌ Время окончания должно быть позже времени начала.")
                return
            if cur == state["target_blocks"] and t2.strftime("%H:%M") != state["end_time"]:
                await self._send_message(
                    self.control_group_id,
                    f"❌ Последнее сообщение должно заканчиваться в {state['end_time']}.",
                )
                return
            state["temp_block"] = {
                "block_start": t1.strftime("%H:%M"),
                "block_end": t2.strftime("%H:%M"),
            }
            state["step"] = "block_text"
            await self._send_message(
                self.control_group_id,
                f"Введите текст для Сообщения №{cur} ({state['temp_block']['block_start']}–{state['temp_block']['block_end']}):",
                reply_markup={"force_reply": True, "input_field_placeholder": "Ваш текст здесь"}
            )

        elif step == "block_text":
            state["temp_block"]["message_text"] = text
            state["step"] = "block_mode"
            cur = state["current_block"]
            await self._send_message(
                self.control_group_id,
                f"Укажите режим отправки для Сообщения №{cur}:\n\n"
                "• Для автоматического равномерного расчёта введите **количество отправок** (число, например: `3`).\n"
                "• Или введите **интервал** (например: `1ч 30м` или `01:30:00`).",
                reply_markup={"force_reply": True, "input_field_placeholder": "3 или 1ч 30м"}
            )

        elif step == "block_mode":
            val = text.strip()
            tb = state["temp_block"]
            if val.isdigit() and int(val) > 0:
                tb["send_count"] = int(val)
                tb["interval_seconds"] = None
            else:
                try:
                    sec = parse_interval_to_seconds(val)
                    tb["interval_seconds"] = sec
                    tb["send_count"] = None
                except ValueError as e:
                    await self._send_message(self.control_group_id, f"❌ {e}")
                    return

            state["blocks"].append(tb)

            if state["current_block"] < state["target_blocks"]:
                state["current_block"] += 1
                state["step"] = "block_window"
                cur = state["current_block"]
                tot = state["target_blocks"]
                await self._send_message(
                    self.control_group_id,
                    f"**Сообщение №{cur} из {tot}**\n\n"
                    "Введите промежуток времени для следующего сообщения (например: `12:00-16:00`):",
                    reply_markup={"force_reply": True, "input_field_placeholder": "12:00-16:00"}
                )
            else:
                # Wizard Finished -> Save to DB & Schedule
                try:
                    self.campaign_engine.validate_blocks(
                        state["start_time"], state["end_time"], state["blocks"]
                    )
                except ValueError as error:
                    await self._send_message(self.control_group_id, f"❌ {error}")
                    return
                del self._wizard[user_id]
                camp_id = self.db.create_campaign(
                    state["name"],
                    state["start_time"],
                    state["end_time"],
                    state["chat_ids"],
                    state["blocks"]
                )
                camp = self.db.get_campaign(camp_id)
                if self.campaign_engine:
                    self.campaign_engine.schedule_campaign(camp)

                lines = [
                    f"🎉 **Кампания «{camp['name']}» успешно создана и запущена!**",
                    f"⏰ Ежедневное время: {camp['start_time']}–{camp['end_time']}",
                    f"🎯 Групп: {len(camp['chat_ids'])}",
                    "",
                    "📋 **Сообщения и расписание:**"
                ]
                for idx, b in enumerate(camp["blocks"], 1):
                    if b.get("send_count"):
                        b_start = parse_time_hhmm(b["block_start"])
                        b_end = parse_time_hhmm(b["block_end"])
                        dur = (datetime.combine(datetime.today(), b_end) - datetime.combine(datetime.today(), b_start)).total_seconds()
                        if dur <= 0:
                            dur += 86400
                        step = dur / b["send_count"]
                        mode_str = f"{b['send_count']} раз(а) (каждые {format_seconds_to_hms(step)})"
                    else:
                        mode_str = f"интервал {format_seconds_to_hms(b['interval_seconds'])}"

                    lines.append(f"{idx}. {b['block_start']}–{b['block_end']}: {mode_str}")
                    lines.append(f"   «{b['message_text'][:30]}...»")

                await self._send_message(self.control_group_id, "\n".join(lines))
                await asyncio.sleep(0.5)
                await self.send_menu()

    async def _show_groups(self, message_id=None):
        dialogs = await self.telegram.get_dialogs()
        groups = [dialog for dialog in dialogs if dialog.is_group]
        self._groups_by_id = {dialog.id: dialog for dialog in groups}
        selected = set(self.groups.get_selected_groups())
        keyboard = []
        for dialog in groups:
            marker = "✅ " if dialog.id in selected else "▫️ "
            title = (dialog.name or str(dialog.id))[:45]
            keyboard.append([self._button(marker + title, f"toggle:{dialog.id}")])
        keyboard.append([self._button("✅ Готово", "menu")])
        text = "Выберите группы. Нажатие переключает выбор; отметьте все нужные и нажмите «Готово»."
        if message_id:
            await self._edit_message(message_id, text, keyboard)
        else:
            await self._send_message(self.control_group_id, text, keyboard)

    async def _toggle_group(self, group_id, message_id):
        try:
            group_id = int(group_id)
            self._groups_by_id[group_id]
        except (KeyError, ValueError):
            await self._show_groups(message_id)
            return
        selected = set(self.groups.get_selected_groups())
        if group_id in selected:
            selected.remove(group_id)
        else:
            selected.add(group_id)
        dialogs = [self._groups_by_id[chat_id] for chat_id in selected if chat_id in self._groups_by_id]
        self.groups.set_selected_groups(dialogs)
        await self._show_groups(message_id)

    async def _show_selected(self):
        ids = self.groups.get_selected_groups()
        saved = {row["chat_id"]: row["title"] for row in self.groups.get_groups()}
        text = "Выбранные группы:\n" + "\n".join(f"• {saved.get(chat_id, chat_id)}" for chat_id in ids) if ids else "Группы ещё не выбраны."
        await self._send_message(self.control_group_id, text)

    async def _show_plans(self):
        plans = self.scheduler.get_plans()
        if not plans:
            await self._send_message(self.control_group_id, "Запланированных разовых рассылок нет.")
            return
        keyboard = [[self._button(f"Отменить {plan['id']}", f"cancel:{plan['id']}")] for plan in plans if not plan["started"]]
        lines = ["Запланированные разовые рассылки:"]
        lines.extend(f"• {plan['id']}: {plan['start_at'].strftime('%d.%m %H:%M')}–{plan['end_at'].strftime('%H:%M')}" for plan in plans)
        await self._send_message(self.control_group_id, "\n".join(lines), keyboard or None)

    async def _ask(self, user_id, action):
        prompts = {
            "start": "Введите текст для рассылки 1.",
            "start2": "Введите текст для параллельной рассылки 2.",
            "send": "Введите текст для однократной отправки.",
            "interval": "Введите интервал (например: 10 или 1ч 30м).",
            "schedule": "Введите: ЧЧ:ММ ДЛИТЕЛЬНОСТЬ_СЕК ИНТЕРВАЛ_СЕК ТЕКСТ\nПример: 18:30 300 10 Привет!",
        }
        self._pending[user_id] = action
        await self._send_message(self.control_group_id, prompts[action], reply_markup={"force_reply": True, "input_field_placeholder": "Введите значение"})

    async def _finish_input(self, user_id, text):
        action = self._pending.pop(user_id)
        if action == "interval":
            try:
                sec = parse_interval_to_seconds(text)
                if sec < 1:
                    raise ValueError
            except ValueError:
                await self._send_message(self.control_group_id, "Неверный интервал. Укажите число секунд или 1ч 30м.")
                return
            command = f"/interval {sec}"
        elif action == "schedule":
            if len(text.split(maxsplit=3)) != 4:
                await self._send_message(self.control_group_id, "Неверный формат. Откройте меню и попробуйте снова.")
                return
            command = f"/schedule {text}"
        else:
            if not text:
                await self._send_message(self.control_group_id, "Текст не должен быть пустым.")
                return
            command = f"/{action} {text}"
        await self._run_telethon_command(command)
        await asyncio.sleep(0.2)
        await self.send_menu()

    async def _poll(self):
        while self.enabled:
            try:
                data = {"timeout": 25, "allowed_updates": ["message", "callback_query"]}
                if self._offset is not None:
                    data["offset"] = self._offset
                updates = await self._api("getUpdates", data)
                for update in updates:
                    self._offset = update["update_id"] + 1
                    await self._handle_update(update)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Ошибка получения обновлений интерфейсного бота.")
                await asyncio.sleep(5)

    async def _handle_update(self, update):
        message = update.get("message")
        if message:
            if message.get("chat", {}).get("id") != self.control_group_id:
                return
            user_id = message.get("from", {}).get("id")
            username = (message.get("from", {}).get("username") or "").lower()
            text = (message.get("text") or "").strip()
            if not self.admins.has_access(username):
                return
            if text.lower() in {"/menu", f"/menu@{self.username}"}:
                await self.send_menu()
            elif user_id in self._wizard:
                await self._handle_wizard_input(user_id, text)
            elif user_id in self._pending:
                await self._finish_input(user_id, text)
            return

        callback = update.get("callback_query")
        if not callback or callback.get("message", {}).get("chat", {}).get("id") != self.control_group_id:
            return
        username = (callback.get("from", {}).get("username") or "").lower()
        callback_id = callback["id"]
        if not self.admins.has_access(username):
            await self._api("answerCallbackQuery", {"callback_query_id": callback_id, "text": "Нет доступа."})
            return
        await self._api("answerCallbackQuery", {"callback_query_id": callback_id})
        data = callback.get("data", "")
        message_id = callback["message"]["message_id"]
        user_id = callback["from"]["id"]
        if data == "menu":
            await self.send_menu()
        elif data == "groups":
            await self._show_groups(message_id)
        elif data.startswith("toggle:"):
            await self._toggle_group(data.removeprefix("toggle:"), message_id)
        elif data == "selected":
            await self._show_selected()
        elif data == "time":
            await self._show_time()
        elif data == "campaigns":
            await self._show_campaigns()
        elif data == "wizard_start":
            await self._start_wizard(user_id)
        elif data.startswith("cmp_del:"):
            cid = int(data.removeprefix("cmp_del:"))
            if self.campaign_engine:
                self.campaign_engine.unschedule_campaign(cid)
            self.db.delete_campaign(cid)
            await self._send_message(self.control_group_id, f"✅ Кампания #{cid} удалена.")
            await self._show_campaigns()
        elif data in {"start", "start2", "send", "interval", "schedule"}:
            await self._ask(user_id, data)
        elif data == "status":
            await self._run_telethon_command("/status")
        elif data in {"stop", "stop1"}:
            await self._run_telethon_command("/stop1")
            await asyncio.sleep(0.2)
            await self.send_menu()
        elif data == "stop2":
            await self._run_telethon_command("/stop2")
            await asyncio.sleep(0.2)
            await self.send_menu()
        elif data == "stop_all":
            await self._run_telethon_command("/stop_all")
            await asyncio.sleep(0.2)
            await self.send_menu()
        elif data == "plans":
            await self._show_plans()
        elif data.startswith("cancel:"):
            plan_id = data.removeprefix("cancel:")
            if self.scheduler.cancel(plan_id):
                await self._send_message(self.control_group_id, f"✅ План {plan_id} отменён.")
            else:
                await self._send_message(self.control_group_id, "План не найден или уже запущен.")

    async def _run_telethon_command(self, command):
        await self._send_message(self.control_group_id, command)

    @staticmethod
    def _button(text, data):
        return {"text": text, "callback_data": data}

    async def _send_message(self, chat_id, text, keyboard=None, reply_markup=None):
        data = {"chat_id": chat_id, "text": text}
        if reply_markup:
            data["reply_markup"] = reply_markup
        elif keyboard:
            data["reply_markup"] = {"inline_keyboard": keyboard}
        return await self._api("sendMessage", data)

    async def _edit_message(self, message_id, text, keyboard):
        return await self._api("editMessageText", {"chat_id": self.control_group_id, "message_id": message_id, "text": text, "reply_markup": {"inline_keyboard": keyboard}})

    async def _api(self, method, data=None):
        return await asyncio.to_thread(self._api_sync, method, data or {})

    def _api_sync(self, method, data):
        url = f"https://api.telegram.org/bot{self.token}/{method}"
        request = Request(url, data=json.dumps(data).encode("utf-8"), headers={"Content-Type": "application/json"})
        try:
            with urlopen(request, timeout=35) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except URLError as error:
            raise RuntimeError(f"Bot API недоступен: {error.reason}") from error
        if not payload.get("ok"):
            raise RuntimeError(payload.get("description", "Неизвестная ошибка Bot API"))
        return payload["result"]
