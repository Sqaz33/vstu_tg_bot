from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

from vstu_schedule_bot.domain.models import Lesson
from vstu_schedule_bot.storage.database import Database


class ScheduleService:
    def __init__(self, database: Database, timezone: ZoneInfo) -> None:
        self._database = database
        self._timezone = timezone

    def today(self) -> date:
        return datetime.now(self._timezone).date()

    @staticmethod
    def week_bounds(target: date) -> tuple[date, date]:
        start = target - timedelta(days=target.weekday())
        return start, start + timedelta(days=6)

    async def group_day(self, group: str, target: date) -> list[tuple[date, Lesson]]:
        return await self._database.lessons_for_group(group, target, target)

    async def group_week(
        self, group: str, target: date, *, next_week: bool = False
    ) -> list[tuple[date, Lesson]]:
        start, end = self.week_bounds(target)
        if next_week:
            start += timedelta(days=7)
            end += timedelta(days=7)
        return await self._database.lessons_for_group(group, start, end)

    async def teacher_week(
        self, teacher: str, target: date, *, next_week: bool = False
    ) -> list[tuple[date, Lesson]]:
        start, end = self.week_bounds(target)
        if next_week:
            start += timedelta(days=7)
            end += timedelta(days=7)
        return await self._database.lessons_for_teacher(teacher, start, end)
