import asyncio
import logging
from datetime import datetime, timedelta, time
from typing import Dict, Any, List

from app.config import get_now, TZ
from app.utils.time_parser import parse_time_hhmm, format_seconds_to_hms


class CampaignEngine:
    """Manages multi-text daily repeating campaigns with auto-calculated intervals and completion notifications."""

    def __init__(self, telegram, database, logger, control_group_id, scheduler_instance):
        self.telegram = telegram
        self.db = database
        self.logger = logger
        self.control_group_id = control_group_id
        self.scheduler = scheduler_instance
        self._active_stats: Dict[int, Dict[int, int]] = {}  # campaign_id -> {chat_id: count}

    def reload_all(self):
        """Loads all enabled campaigns from database and schedules them."""
        campaigns = self.db.get_campaigns()
        for campaign in campaigns:
            if campaign["enabled"]:
                try:
                    self.schedule_campaign(campaign)
                except Exception:
                    self.logger.exception(f"Ошибка при загрузке кампании {campaign['id']}")

    def schedule_campaign(self, campaign: Dict[str, Any]):
        """Schedules all send jobs and end-of-day notification for a campaign."""
        cid = campaign["id"]
        self.unschedule_campaign(cid)

        self.validate_blocks(campaign["start_time"], campaign["end_time"], campaign.get("blocks", []))

        self._active_stats[cid] = {chat_id: 0 for chat_id in campaign["chat_ids"]}

        now = get_now()
        start_t = parse_time_hhmm(campaign["start_time"])
        end_t = parse_time_hhmm(campaign["end_time"])

        # Determine target date for today or tomorrow
        target_date = now.date()
        end_dt_today = datetime.combine(target_date, end_t, tzinfo=now.tzinfo)
        if now >= end_dt_today:
            target_date += timedelta(days=1)

        blocks = campaign.get("blocks", [])
        if not blocks:
            return

        total_jobs_added = 0

        for block in blocks:
            b_start = parse_time_hhmm(block["block_start"])
            b_end = parse_time_hhmm(block["block_end"])

            dt_start = datetime.combine(target_date, b_start, tzinfo=now.tzinfo)
            dt_end = datetime.combine(target_date, b_end, tzinfo=now.tzinfo)

            # Handle overnight block if end <= start
            if dt_end <= dt_start:
                dt_end += timedelta(days=1)

            duration_sec = (dt_end - dt_start).total_seconds()
            send_count = block.get("send_count")
            interval_sec = block.get("interval_seconds")

            if send_count and send_count >= 1:
                # The end is exclusive: the next block may start exactly at it.
                # Example: 3 sends in 09:00-12:00 run at 09:00, 10:00, 11:00.
                step_sec = duration_sec / send_count
                send_times = [dt_start + timedelta(seconds=i * step_sec) for i in range(send_count)]
            elif interval_sec and interval_sec >= 1:
                send_times = []
                cur = dt_start
                while cur < dt_end:
                    send_times.append(cur)
                    cur += timedelta(seconds=interval_sec)
            else:
                continue

            for idx, run_dt in enumerate(send_times):
                if run_dt < now:
                    continue  # Skip past timestamps if starting mid-day
                job_id = f"cmp_{cid}_b{block['id']}_{idx}"
                self.scheduler.scheduler.add_job(
                    self._execute_send,
                    trigger="date",
                    run_date=run_dt,
                    args=(cid, block["message_text"], campaign["chat_ids"]),
                    id=job_id,
                    replace_existing=True,
                )
                total_jobs_added += 1

        # Schedule End of Day Notification at end_time
        eod_dt = datetime.combine(target_date, end_t, tzinfo=now.tzinfo)
        if eod_dt <= datetime.combine(target_date, start_t, tzinfo=now.tzinfo):
            eod_dt += timedelta(days=1)

        self.scheduler.scheduler.add_job(
            self._end_of_day_handler,
            trigger="date",
            run_date=eod_dt,
            args=(cid,),
            id=f"cmp_{cid}_eod",
            replace_existing=True,
        )

        self.logger.info(f"Кампания '{campaign['name']}' (ID: {cid}) запланирована на {target_date.strftime('%d.%m.%Y')}. Задач: {total_jobs_added}")

    @staticmethod
    def validate_blocks(start_time: str, end_time: str, blocks: List[Dict[str, Any]]):
        """Ensure blocks fill one same-day campaign window without gaps or overlaps."""
        campaign_start = parse_time_hhmm(start_time)
        campaign_end = parse_time_hhmm(end_time)
        if campaign_end <= campaign_start:
            raise ValueError("Время окончания кампании должно быть позже времени начала.")
        if not blocks:
            raise ValueError("Добавьте хотя бы одно сообщение.")

        expected_start = campaign_start
        for number, block in enumerate(blocks, 1):
            block_start = parse_time_hhmm(block["block_start"])
            block_end = parse_time_hhmm(block["block_end"])
            if block_end <= block_start:
                raise ValueError(f"В блоке {number} время окончания должно быть позже времени начала.")
            if block_start != expected_start:
                raise ValueError(
                    f"Блок {number} должен начинаться в {expected_start.strftime('%H:%M')}, "
                    "чтобы не было пропусков или пересечений."
                )
            expected_start = block_end

        if expected_start != campaign_end:
            raise ValueError(
                f"Последний блок должен заканчиваться в {campaign_end.strftime('%H:%M')}."
            )

    def unschedule_campaign(self, campaign_id: int):
        """Removes all scheduled jobs for a campaign."""
        prefix = f"cmp_{campaign_id}_"
        jobs = self.scheduler.scheduler.get_jobs()
        for job in jobs:
            if job.id.startswith(prefix):
                self.scheduler.scheduler.remove_job(job.id)

    async def _execute_send(self, campaign_id: int, message_text: str, chat_ids: List[int]):
        """Executes a single send task for campaign."""
        results = await asyncio.gather(
            *(self.telegram.send_message(cid, message_text) for cid in chat_ids),
            return_exceptions=True
        )
        if campaign_id in self._active_stats:
            for cid, res in zip(chat_ids, results):
                if not isinstance(res, Exception):
                    self._active_stats[campaign_id][cid] = self._active_stats[campaign_id].get(cid, 0) + 1

    async def _end_of_day_handler(self, campaign_id: int):
        """Triggers end-of-day completion notice and schedules for tomorrow."""
        campaign = self.db.get_campaign(campaign_id)
        if not campaign or not campaign["enabled"]:
            return

        stats = self._active_stats.get(campaign_id, {})
        saved_groups = {g["chat_id"]: g["title"] for g in self.db.get_groups()}

        lines = [
            f"⏹ Кампания «{campaign['name']}» окончена на сегодня ({campaign['end_time']}).",
            f"Следующий автозапуск завтра в {campaign['start_time']}.",
            "",
            "Отправлено за день:",
        ]
        for cid in campaign["chat_ids"]:
            count = stats.get(cid, 0)
            lines.append(f"• {saved_groups.get(cid, cid)}: {count} сообщ.")

        await self.telegram.send_message(self.control_group_id, "\n".join(lines))

        # Re-schedule for tomorrow
        self.schedule_campaign(campaign)
