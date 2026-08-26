from __future__ import annotations

from datetime import date, timedelta

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder

from vstu_schedule_bot.bot.callbacks import (
    ActionCallback,
    DateCallback,
    GroupCallback,
    TeacherPickCallback,
    TeacherWeekCallback,
    WeekCallback,
)


def home_keyboard() -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(text="📅 Сегодня", callback_data=ActionCallback(name="today").pack()),
        InlineKeyboardButton(text="🌤 Завтра", callback_data=ActionCallback(name="tomorrow").pack()),
    )
    builder.row(
        InlineKeyboardButton(text="🗓 Эта неделя", callback_data=ActionCallback(name="week").pack()),
        InlineKeyboardButton(
            text="⏭ Следующая", callback_data=ActionCallback(name="next_week").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="👤 Преподаватель", callback_data=ActionCallback(name="teacher").pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🎓 Сменить группу", callback_data=ActionCallback(name="groups").pack()
        ),
        InlineKeyboardButton(text="↻ Обновить", callback_data=ActionCallback(name="home").pack()),
    )
    return builder.as_markup()


def groups_keyboard(groups: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for group in groups:
        builder.button(text=group, callback_data=GroupCallback(name=group))
    builder.adjust(2)
    builder.row(
        InlineKeyboardButton(
            text="⌕ Найти группу", callback_data=ActionCallback(name="group_search").pack()
        ),
        InlineKeyboardButton(text="‹ Назад", callback_data=ActionCallback(name="home").pack()),
    )
    return builder.as_markup()


def day_keyboard(target: date) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="‹ День",
            callback_data=DateCallback(value=(target - timedelta(days=1)).isoformat()).pack(),
        ),
        InlineKeyboardButton(text="⌂ Меню", callback_data=ActionCallback(name="home").pack()),
        InlineKeyboardButton(
            text="День ›",
            callback_data=DateCallback(value=(target + timedelta(days=1)).isoformat()).pack(),
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="🗓 Вся неделя", callback_data=WeekCallback(value=target.isoformat()).pack()
        )
    )
    return builder.as_markup()


def week_keyboard(start: date) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="‹ Неделя",
            callback_data=WeekCallback(value=(start - timedelta(days=7)).isoformat()).pack(),
        ),
        InlineKeyboardButton(text="⌂ Меню", callback_data=ActionCallback(name="home").pack()),
        InlineKeyboardButton(
            text="Неделя ›",
            callback_data=WeekCallback(value=(start + timedelta(days=7)).isoformat()).pack(),
        ),
    )
    return builder.as_markup()


def teacher_results_keyboard(teachers: list[str]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for index, teacher in enumerate(teachers):
        builder.button(text=f"👤 {teacher}", callback_data=TeacherPickCallback(index=index))
    builder.adjust(1)
    builder.row(
        InlineKeyboardButton(text="‹ Назад", callback_data=ActionCallback(name="home").pack())
    )
    return builder.as_markup()


def teacher_week_keyboard(offset: int) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    builder.row(
        InlineKeyboardButton(
            text="‹ Неделя", callback_data=TeacherWeekCallback(offset=offset - 1).pack()
        ),
        InlineKeyboardButton(text="⌂ Меню", callback_data=ActionCallback(name="home").pack()),
        InlineKeyboardButton(
            text="Неделя ›", callback_data=TeacherWeekCallback(offset=offset + 1).pack()
        ),
    )
    builder.row(
        InlineKeyboardButton(
            text="⌕ Другой преподаватель", callback_data=ActionCallback(name="teacher").pack()
        )
    )
    return builder.as_markup()
