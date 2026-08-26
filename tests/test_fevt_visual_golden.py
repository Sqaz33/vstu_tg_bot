from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path

import pytest

from vstu_schedule_bot.bot.formatters import format_day
from vstu_schedule_bot.domain.models import Lesson, ParsedSchedule
from vstu_schedule_bot.parsing.factory import create_parser_registry
from vstu_schedule_bot.parsing.readers import WorkbookReaderRegistry

WORKBOOK_PATH = Path(".research/fevt1.xls")
pytestmark = pytest.mark.skipif(not WORKBOOK_PATH.exists(), reason="local research file")


@pytest.fixture(scope="module")
def fevt_schedule() -> ParsedSchedule:
    workbook = WorkbookReaderRegistry().read(WORKBOOK_PATH)
    return create_parser_registry().parse(workbook, "ФЭВТ")


def _group_digest(schedule: ParsedSchedule, group: str) -> tuple[int, str]:
    rows = sorted(
        (
            lesson.weekday,
            lesson.slot_start,
            lesson.slot_end,
            lesson.subject,
            lesson.lesson_type,
            lesson.teacher,
            lesson.room,
            [value.isoformat() for value in lesson.explicit_dates],
        )
        for lesson in schedule.lessons
        if lesson.group == group
    )
    payload = json.dumps(rows, ensure_ascii=False, separators=(",", ":"))
    return len(rows), hashlib.sha256(payload.encode()).hexdigest()


def test_every_group_matches_the_visually_approved_workbook_snapshot(
    fevt_schedule: ParsedSchedule,
) -> None:
    expected = {
        "ЭВМ-1.2": (14, "c0926500859e2ae646a6420e0dd571649fe6e6a632462a1095110c16dcde4809"),
        "ЭВМ-1.3": (14, "2b9710c850ee59cffe4693c487b6b9f901dbfef8ee24be4068e7933567292c38"),
        "САПР-1.1": (15, "c63df8f97b7fd9c61f14709816353b07af3f42448509569d506677dabfa37bde"),
        "САПР-1.4": (16, "a4a656bf0098443fff1e6eea990029b03383220920d8d78ac8cac6ca5ae4ded9"),
        "САПР-1.3": (13, "877b0362e1d8ed6d809d05d6792c1bed375c46d9ab2bd5291b0a32fc704fb6d5"),
        "ПОАС-1.1": (11, "fe472f707ce9ccfe3d27796129151ef6c2e5a6a0ea7e1f5be888d5cdd9f05700"),
        "ПОАС-1.2": (10, "aa3502cd929a9e65d6632dbb5c1601091cfddcf0e9f898aaa8fb52eda9c45cfb"),
        "Ф-1": (14, "bbce5576cd803e9e4f5b87dd736f0ac20a9e7d6d61c3c852c8813182e3c8f1ce"),
        "ЭТ-1": (9, "79298d43961bde2b9cb73249e24a3f65164f58c1855508cabc6c7c6f37c15602"),
    }

    assert {
        group: _group_digest(fevt_schedule, group) for group in fevt_schedule.groups
    } == expected


@pytest.mark.parametrize(
    ("group", "target", "expected"),
    [
        (
            "ЭВМ-1.2",
            date(2026, 9, 16),
            (("1–4", "ТЕХНОЛОГИИ ПРОГРАММИРОВАНИЯ И ИНСТРУМЕНТАЛЬНЫЕ СР-ВА РАЗРАБОТКИ С-М ИИ"),),
        ),
        (
            "ЭВМ-1.3",
            date(2026, 9, 22),
            (("1–4", "ИНФОКОММУНИКАЦИОННЫЕ СИСТЕМЫ ИССКУСТВЕННОГО ИНТЕЛЛЕКТА"),),
        ),
        ("САПР-1.1", date(2026, 9, 21), (("9–12", "СИСТЕМНАЯ ИНЖЕНЕРИЯ"),)),
        (
            "САПР-1.4",
            date(2026, 9, 29),
            (("1–4", "СИСТЕМЫ ОБРАБОТКИ БОЛЬШИХ ДАННЫХ"),),
        ),
        (
            "САПР-1.3",
            date(2026, 9, 11),
            (
                ("3–4", "МЕХАНИКА РОБОТОТЕХ. С-М"),
                ("5–6", "МЕХАНИКА РОБОТОТЕХ. С-М"),
            ),
        ),
        ("ПОАС-1.1", date(2026, 9, 24), (("9–12", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"),)),
        ("ПОАС-1.2", date(2026, 9, 10), (("5–8", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"),)),
        (
            "Ф-1",
            date(2026, 9, 9),
            (
                ("1–2", "ФУНДАМЕНТАЛЬНЫЕ ФИЗИЧЕСКИЕ ЭКСПЕРИМЕНТЫ"),
                ("3–4", "МАТЕМАТИЧЕСКИЕ МЕТОДЫ В ФИЗИКЕ"),
                ("5–6", "МАТЕМАТИЧЕСКИЕ МЕТОДЫ В ФИЗИКЕ"),
            ),
        ),
        (
            "ЭТ-1",
            date(2026, 9, 9),
            (
                ("5–6", "ИСТОРИЯ И МЕТОДОЛОГИЯ ПРИБОРОСТРОЕНИЯ"),
                ("7–8", "ИСТОРИЯ И МЕТОДОЛОГИЯ ПРИБОРОСТРОЕНИЯ"),
            ),
        ),
    ],
)
def test_user_day_output_matches_visual_excel_card(
    fevt_schedule: ParsedSchedule,
    group: str,
    target: date,
    expected: tuple[tuple[str, str], ...],
) -> None:
    lessons: list[Lesson] = sorted(
        (
            lesson
            for lesson in fevt_schedule.lessons
            if lesson.group == group
            and lesson.occurs_on(
                target,
                fevt_schedule.semester_start,
                fevt_schedule.semester_end,
            )
        ),
        key=lambda lesson: lesson.slot_start,
    )

    assert tuple((lesson.pair_label, lesson.subject) for lesson in lessons) == expected
    message = format_day(group, target, [(target, lesson) for lesson in lessons])
    assert f"<code>{group}</code>" in message
    for pair_label, _ in expected:
        assert f"<code>{pair_label}</code>" in message
