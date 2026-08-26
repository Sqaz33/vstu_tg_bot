from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from vstu_schedule_bot.domain.models import DateRule, Lesson, ParsedSchedule
from vstu_schedule_bot.storage.database import Database


@pytest.fixture
def schedule() -> ParsedSchedule:
    return ParsedSchedule(
        faculty="ФЭВТ",
        academic_year="2026–2027",
        semester=1,
        semester_start=date(2026, 8, 20),
        semester_end=date(2027, 1, 15),
        groups=("ЭВМ-1.2",),
        lessons=(
            Lesson(
                group="ЭВМ-1.2",
                weekday=0,
                slot_start=1,
                slot_end=2,
                pair_label="1–2",
                starts_at="08:30",
                ends_at="10:00",
                subject="ТЕСТИРОВАНИЕ",
                teacher="Иванов И.И.",
                room="В-903",
            ),
            Lesson(
                group="ЭВМ-1.2",
                weekday=0,
                slot_start=3,
                slot_end=4,
                pair_label="3–4",
                starts_at="10:10",
                ends_at="11:40",
                subject="АРХИТЕКТУРА",
                teacher="Петров П.П.",
                date_rule=DateRule.EXPLICIT,
                explicit_dates=(date(2026, 9, 14),),
            ),
        ),
    )


async def test_atomic_schedule_storage_and_queries(tmp_path, schedule: ParsedSchedule) -> None:
    database = Database(tmp_path / "schedule.db")
    await database.connect()
    try:
        await database.replace_schedule(
            schedule,
            source_url="https://example.test/schedule.xls",
            source_label="1 курс ФЭВТ.xls",
            sha256="abc",
            etag=None,
            last_modified=None,
            checked_at=datetime(2026, 8, 26, tzinfo=UTC),
        )
        assert await database.list_groups() == ["ЭВМ-1.2"]

        lessons = await database.lessons_for_group("ЭВМ-1.2", date(2026, 9, 14), date(2026, 9, 14))
        assert [lesson.subject for _, lesson in lessons] == ["ТЕСТИРОВАНИЕ", "АРХИТЕКТУРА"]
        assert await database.search_teachers("иван") == ["Иванов И.И."]

        await database.set_user_group(42, "ЭВМ-1.2")
        assert await database.get_user_group(42) == "ЭВМ-1.2"
    finally:
        await database.close()
