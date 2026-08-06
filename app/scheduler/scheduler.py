from datetime import datetime, timedelta
from uuid import uuid4

from apscheduler.schedulers.asyncio import AsyncIOScheduler


class BroadcastScheduler:
    """Plans non-overlapping broadcasts and automatically stops each one."""

    def __init__(self, telegram, sender, logger, control_group_id):
        self.telegram = telegram
        self.sender = sender
        self.logger = logger
        self.control_group_id = control_group_id
        self.scheduler = AsyncIOScheduler(timezone=datetime.now().astimezone().tzinfo)
        self.plans = {}

    def start(self):
        self.scheduler.start()

    def shutdown(self):
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def schedule(self, start_at, duration_seconds, chat_ids, message, interval, titles):
        end_at = start_at + timedelta(seconds=duration_seconds)
        conflict = self._find_conflict(start_at, end_at)
        if conflict:
            raise ValueError(
                f"пересекается с планом {conflict['id']} "
                f"({conflict['start_at'].strftime('%d.%m %H:%M')}–{conflict['end_at'].strftime('%H:%M')})"
            )

        plan_id = uuid4().hex[:6].upper()
        self.plans[plan_id] = {
            "id": plan_id,
            "start_at": start_at,
            "end_at": end_at,
            "duration_seconds": duration_seconds,
            "chat_ids": chat_ids,
            "message": message,
            "interval": interval,
            "titles": titles,
            "started": False,
        }
        self.scheduler.add_job(
            self._start_broadcast,
            trigger="date",
            run_date=start_at,
            args=(plan_id,),
            id=f"broadcast_start_{plan_id}",
        )
        return self.plans[plan_id]

    def get_plans(self):
        now = datetime.now().astimezone()
        return sorted(
            (plan for plan in self.plans.values() if plan["end_at"] > now),
            key=lambda plan: plan["start_at"],
        )

    def cancel(self, plan_id):
        plan = self.plans.get(plan_id.upper())
        if not plan or plan["started"]:
            return False
        self.scheduler.remove_job(f"broadcast_start_{plan['id']}")
        del self.plans[plan["id"]]
        return True

    def forget_running_plan(self, slot_id=1):
        """Removes the automatic stop job when a running plan is stopped manually."""
        for plan_id, plan in list(self.plans.items()):
            if plan.get("started") and plan.get("slot_id") == slot_id:
                job = self.scheduler.get_job(f"broadcast_stop_{plan_id}")
                if job:
                    self.scheduler.remove_job(job.id)
                del self.plans[plan_id]
                return

    def _find_conflict(self, start_at, end_at):
        for plan in self.plans.values():
            if start_at < plan["end_at"] and end_at > plan["start_at"]:
                return plan
        return None

    async def _start_broadcast(self, plan_id):
        plan = self.plans.get(plan_id)
        if not plan:
            return

        slot_id = 1 if not self.sender.is_slot_running(1) else (2 if not self.sender.is_slot_running(2) else 1)

        try:
            self.sender.start(plan["chat_ids"], plan["message"], plan["interval"], plan["titles"], slot_id=slot_id)
        except (RuntimeError, ValueError) as error:
            await self.telegram.send_message(self.control_group_id, f"❌ Не удалось начать план {plan_id}: {error}")
            del self.plans[plan_id]
            return

        plan["started"] = True
        plan["slot_id"] = slot_id
        self.scheduler.add_job(
            self._stop_broadcast,
            trigger="date",
            run_date=plan["end_at"],
            args=(plan_id,),
            id=f"broadcast_stop_{plan_id}",
        )
        await self.telegram.send_message(
            self.control_group_id,
            f"▶️ Запланированная рассылка {plan_id} (слот {slot_id}) началась. Завершение: {plan['end_at'].strftime('%H:%M:%S')}.",
        )

    async def _stop_broadcast(self, plan_id):
        plan = self.plans.get(plan_id)
        slot_id = plan.get("slot_id", 1) if plan else 1
        stats = await self.sender.stop(slot_id=slot_id)
        if stats:
            await self.telegram.send_message(self.control_group_id, self.sender.format_stats(stats, slot_id=slot_id))
        self.plans.pop(plan_id, None)

