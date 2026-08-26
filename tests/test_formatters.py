from datetime import date

from vstu_schedule_bot.bot.formatters import format_day, format_week
from vstu_schedule_bot.domain.models import Lesson


def _lesson() -> Lesson:
    return Lesson(
        group="ЭВМ-1.2",
        weekday=0,
        slot_start=1,
        slot_end=2,
        pair_label="1–2",
        starts_at="08:30",
        ends_at="10:00",
        subject="БАЗЫ ДАННЫХ & ИНФОРМАЦИОННЫЕ СИСТЕМЫ",
        lesson_type="лекция",
        teacher="Иванов <И.И.>",
        room="В-903",
    )


def test_day_formatter_escapes_telegram_html() -> None:
    target = date(2026, 9, 14)
    text = format_day("ЭВМ-1.2", target, [(target, _lesson())])

    assert "08:30–10:00" in text
    assert "&amp;" in text
    assert "&lt;И.И.&gt;" in text
    assert "📍 В-903" in text


def test_teacher_week_includes_group() -> None:
    target = date(2026, 9, 14)
    text = format_week(
        "Расписание преподавателя",
        target,
        date(2026, 9, 20),
        [(target, _lesson())],
        teacher="Иванов И.И.",
    )

    assert "🎓 ЭВМ-1.2" in text
