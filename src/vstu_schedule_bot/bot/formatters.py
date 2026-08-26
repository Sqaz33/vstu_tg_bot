from __future__ import annotations

import html
import re
from collections import defaultdict
from datetime import date, datetime

from vstu_schedule_bot.domain.models import Lesson

WEEKDAYS = (
    "Понедельник",
    "Вторник",
    "Среда",
    "Четверг",
    "Пятница",
    "Суббота",
    "Воскресенье",
)
MONTHS = (
    "",
    "января",
    "февраля",
    "марта",
    "апреля",
    "мая",
    "июня",
    "июля",
    "августа",
    "сентября",
    "октября",
    "ноября",
    "декабря",
)
_ACRONYMS = ("IT", "ИИ", "НИР", "САПР", "ЭВМ", "БД", "ПОАС")


def _date(value: date, *, weekday: bool = True) -> str:
    day = f"{value.day} {MONTHS[value.month]}"
    return f"{WEEKDAYS[value.weekday()]}, {day}" if weekday else day


def _subject(value: str) -> str:
    result = " ".join(value.split())
    if result.isupper() and len(result) > 5:
        result = result.lower().capitalize()
        for acronym in _ACRONYMS:
            result = re.sub(rf"\b{acronym.lower()}\b", acronym, result, flags=re.IGNORECASE)
    return html.escape(result)


def format_home(group: str, meta: dict[str, object] | None) -> str:
    if not meta:
        return (
            "<b>Расписание ВолгГТУ</b>\n\n"
            "⏳ Данные ещё загружаются. Попробуйте обновить экран через несколько секунд."
        )
    updated = datetime.fromisoformat(str(meta["updated_at"]))
    semester = f" · {meta['semester']} семестр" if meta.get("semester") else ""
    return (
        "🎓 <b>Расписание ВолгГТУ</b>\n\n"
        f"Ваша группа: <code>{html.escape(group)}</code>\n"
        f"{html.escape(str(meta['faculty']))} · "
        f"{html.escape(str(meta['academic_year']))}{semester}\n\n"
        "Выберите, что показать 👇\n\n"
        f"<i>Обновлено {updated:%d.%m.%Y в %H:%M}</i>"
    )


def _lesson_card(lesson: Lesson, *, show_group: bool = False) -> str:
    time = (
        f"{lesson.starts_at}–{lesson.ends_at}"
        if lesson.starts_at and lesson.ends_at
        else lesson.pair_label
    )
    type_suffix = f" · {html.escape(lesson.lesson_type)}" if lesson.lesson_type else ""
    lines = [
        f"<b>{html.escape(time)}</b>  <code>{html.escape(lesson.pair_label)}</code>{type_suffix}",
        f"{_subject(lesson.subject)}",
    ]
    details: list[str] = []
    if show_group:
        details.append(f"🎓 {html.escape(lesson.group)}")
    if lesson.teacher:
        details.append(f"👤 {html.escape(lesson.teacher)}")
    if lesson.room:
        details.append(f"📍 {html.escape(lesson.room)}")
    if details:
        lines.append("  ·  ".join(details))
    return "\n".join(lines)


def format_day(group: str, target: date, lessons: list[tuple[date, Lesson]]) -> str:
    header = f"📅 <b>{_date(target)}</b>\n<code>{html.escape(group)}</code>"
    if not lessons:
        return f"{header}\n\n🌿 Пар нет. Можно выдохнуть."
    cards = [_lesson_card(lesson) for _, lesson in lessons]
    count = len(cards)
    noun = "занятие" if count == 1 else "занятия" if 2 <= count <= 4 else "занятий"
    return f"{header}\n\n" + "\n\n".join(cards) + f"\n\n<i>{count} {noun}</i>"


def format_week(
    title: str,
    start: date,
    end: date,
    lessons: list[tuple[date, Lesson]],
    *,
    group: str | None = None,
    teacher: str | None = None,
) -> str:
    owner = ""
    if group:
        owner = f"\n<code>{html.escape(group)}</code>"
    elif teacher:
        owner = f"\n👤 <b>{html.escape(teacher)}</b>"
    header = (
        f"🗓 <b>{html.escape(title)}</b>\n"
        f"{_date(start, weekday=False)} — {_date(end, weekday=False)}{owner}"
    )
    if not lessons:
        return f"{header}\n\n🌿 В расписании ничего нет."

    by_day: dict[date, list[Lesson]] = defaultdict(list)
    for lesson_date, lesson in lessons:
        by_day[lesson_date].append(lesson)
    sections: list[str] = []
    for lesson_date, day_lessons in sorted(by_day.items()):
        cards = [
            _lesson_card(lesson, show_group=teacher is not None)
            for lesson in sorted(day_lessons, key=lambda item: (item.slot_start, item.group))
        ]
        sections.append(f"<b>{_date(lesson_date)}</b>\n" + "\n\n".join(cards))
    return f"{header}\n\n" + "\n\n──────────\n\n".join(sections)


def split_html_message(text: str, limit: int = 3900) -> list[str]:
    if len(text) <= limit:
        return [text]
    blocks = text.split("\n\n──────────\n\n")
    result: list[str] = []
    current = ""
    for block in blocks:
        candidate = f"{current}\n\n──────────\n\n{block}" if current else block
        if current and len(candidate) > limit:
            result.append(current)
            current = block
        else:
            current = candidate
    if current:
        result.append(current)
    return result
