from datetime import date

from vstu_schedule_bot.services.schedule import ScheduleService


def test_week_bounds_start_on_monday() -> None:
    assert ScheduleService.week_bounds(date(2026, 8, 26)) == (
        date(2026, 8, 24),
        date(2026, 8, 30),
    )
