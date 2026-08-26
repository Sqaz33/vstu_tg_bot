from __future__ import annotations

from datetime import date, timedelta

from aiogram import F, Router
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import Command, CommandObject, CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.types import CallbackQuery, InlineKeyboardMarkup, Message

from vstu_schedule_bot.bot.callbacks import (
    ActionCallback,
    DateCallback,
    GroupCallback,
    TeacherPickCallback,
    TeacherWeekCallback,
    WeekCallback,
)
from vstu_schedule_bot.bot.formatters import (
    format_day,
    format_home,
    format_week,
    split_html_message,
)
from vstu_schedule_bot.bot.keyboards import (
    day_keyboard,
    groups_keyboard,
    home_keyboard,
    teacher_results_keyboard,
    teacher_week_keyboard,
    week_keyboard,
)
from vstu_schedule_bot.bot.states import GroupSearch, TeacherSearch
from vstu_schedule_bot.services.schedule import ScheduleService
from vstu_schedule_bot.storage.database import Database

router = Router(name="schedule")


async def _send_or_edit(
    event: Message | CallbackQuery,
    text: str,
    *,
    reply_markup: InlineKeyboardMarkup | None = None,
) -> None:
    parts = split_html_message(text)
    if isinstance(event, CallbackQuery) and isinstance(event.message, Message):
        try:
            await event.message.edit_text(parts[0], reply_markup=reply_markup)
        except TelegramBadRequest as error:
            if "message is not modified" not in str(error).lower():
                await event.message.answer(parts[0], reply_markup=reply_markup)
        for part in parts[1:]:
            await event.message.answer(part)
    elif isinstance(event, Message):
        for index, part in enumerate(parts):
            await event.answer(part, reply_markup=reply_markup if index == 0 else None)


async def _show_groups(event: Message | CallbackQuery, database: Database, query: str = "") -> None:
    groups = await database.list_groups(query)
    if not groups:
        text = "🔎 <b>Группы не найдены</b>\n\nПопробуйте другой фрагмент названия."
        await _send_or_edit(event, text, reply_markup=home_keyboard())
        return
    text = "🎓 <b>Выберите группу</b>\n\nБот запомнит выбор — менять его каждый раз не придётся."
    await _send_or_edit(event, text, reply_markup=groups_keyboard(groups))


async def _selected_group(
    event: Message | CallbackQuery, database: Database, user_id: int
) -> str | None:
    group = await database.get_user_group(user_id)
    if group is None:
        await _show_groups(event, database)
    return group


async def _show_home(event: Message | CallbackQuery, database: Database, user_id: int) -> None:
    group = await database.get_user_group(user_id)
    if group is None:
        await _show_groups(event, database)
        return
    await _send_or_edit(
        event,
        format_home(group, await database.get_meta()),
        reply_markup=home_keyboard(),
    )


def _message_user_id(message: Message) -> int:
    if message.from_user is None:
        raise ValueError("A private bot message has no sender")
    return message.from_user.id


async def _show_day(
    event: Message | CallbackQuery,
    database: Database,
    service: ScheduleService,
    user_id: int,
    target: date,
) -> None:
    group = await _selected_group(event, database, user_id)
    if not group:
        return
    lessons = await service.group_day(group, target)
    await _send_or_edit(
        event, format_day(group, target, lessons), reply_markup=day_keyboard(target)
    )


async def _show_week(
    event: Message | CallbackQuery,
    database: Database,
    service: ScheduleService,
    user_id: int,
    target: date,
) -> None:
    group = await _selected_group(event, database, user_id)
    if not group:
        return
    start, end = service.week_bounds(target)
    lessons = await service.group_week(group, target)
    current_start, _ = service.week_bounds(service.today())
    if start == current_start:
        title = "Эта неделя"
    elif start == current_start + timedelta(days=7):
        title = "Следующая неделя"
    else:
        title = "Неделя"
    await _send_or_edit(
        event,
        format_week(title, start, end, lessons, group=group),
        reply_markup=week_keyboard(start),
    )


@router.message(CommandStart())
async def start(message: Message, state: FSMContext, database: Database) -> None:
    await state.clear()
    if not await database.is_ready():
        await message.answer(
            "⏳ <b>Расписание загружается</b>\n\n"
            "Первый запуск обычно занимает несколько секунд. Нажмите /start чуть позже."
        )
        return
    await _show_home(message, database, _message_user_id(message))


@router.message(Command("group"))
async def group_command(
    message: Message, command: CommandObject, state: FSMContext, database: Database
) -> None:
    if command.args:
        groups = await database.list_groups(command.args, limit=10)
        await _send_or_edit(
            message,
            "🎓 <b>Результаты поиска</b>",
            reply_markup=groups_keyboard(groups) if groups else home_keyboard(),
        )
        return
    await state.clear()
    await _show_groups(message, database)


@router.message(Command("today"))
async def today_command(message: Message, database: Database, service: ScheduleService) -> None:
    await _show_day(message, database, service, _message_user_id(message), service.today())


@router.message(Command("week"))
async def week_command(message: Message, database: Database, service: ScheduleService) -> None:
    await _show_week(message, database, service, _message_user_id(message), service.today())


@router.message(Command("teacher"))
async def teacher_command(
    message: Message, command: CommandObject, state: FSMContext, database: Database
) -> None:
    if not command.args:
        await state.set_state(TeacherSearch.waiting_for_query)
        await message.answer(
            "👤 <b>Поиск преподавателя</b>\n\n"
            "Введите фамилию или её часть — например, <code>Аникин</code>."
        )
        return
    await _teacher_results(message, command.args, state, database)


@router.callback_query(ActionCallback.filter())
async def action_callback(
    callback: CallbackQuery,
    callback_data: ActionCallback,
    state: FSMContext,
    database: Database,
    service: ScheduleService,
) -> None:
    await callback.answer()
    action = callback_data.name
    if action == "home":
        await state.clear()
        await _show_home(callback, database, callback.from_user.id)
    elif action == "groups":
        await state.clear()
        await _show_groups(callback, database)
    elif action == "group_search":
        await state.set_state(GroupSearch.waiting_for_query)
        await _send_or_edit(
            callback,
            "⌕ <b>Поиск группы</b>\n\nВведите часть названия, например <code>ЭВМ</code>.",
            reply_markup=home_keyboard(),
        )
    elif action == "today":
        await _show_day(callback, database, service, callback.from_user.id, service.today())
    elif action == "tomorrow":
        await _show_day(
            callback,
            database,
            service,
            callback.from_user.id,
            service.today() + timedelta(days=1),
        )
    elif action == "week":
        await _show_week(callback, database, service, callback.from_user.id, service.today())
    elif action == "next_week":
        await _show_week(
            callback,
            database,
            service,
            callback.from_user.id,
            service.today() + timedelta(days=7),
        )
    elif action == "teacher":
        await state.set_state(TeacherSearch.waiting_for_query)
        await _send_or_edit(
            callback,
            "👤 <b>Поиск преподавателя</b>\n\n"
            "Введите фамилию или её часть — например, <code>Аникин</code>.",
            reply_markup=home_keyboard(),
        )


@router.callback_query(GroupCallback.filter())
async def select_group(
    callback: CallbackQuery,
    callback_data: GroupCallback,
    state: FSMContext,
    database: Database,
) -> None:
    if callback_data.name not in await database.list_groups(callback_data.name, limit=20):
        await callback.answer("Группа больше не доступна", show_alert=True)
        return
    await callback.answer("Группа сохранена")
    await database.set_user_group(callback.from_user.id, callback_data.name)
    await state.clear()
    await _show_home(callback, database, callback.from_user.id)


@router.callback_query(DateCallback.filter())
async def date_callback(
    callback: CallbackQuery,
    callback_data: DateCallback,
    database: Database,
    service: ScheduleService,
) -> None:
    await callback.answer()
    await _show_day(
        callback,
        database,
        service,
        callback.from_user.id,
        date.fromisoformat(callback_data.value),
    )


@router.callback_query(WeekCallback.filter())
async def week_callback(
    callback: CallbackQuery,
    callback_data: WeekCallback,
    database: Database,
    service: ScheduleService,
) -> None:
    await callback.answer()
    await _show_week(
        callback,
        database,
        service,
        callback.from_user.id,
        date.fromisoformat(callback_data.value),
    )


@router.message(GroupSearch.waiting_for_query, F.text)
async def group_search_message(message: Message, state: FSMContext, database: Database) -> None:
    await state.clear()
    await _show_groups(message, database, message.text or "")


async def _teacher_results(
    event: Message | CallbackQuery,
    query: str,
    state: FSMContext,
    database: Database,
) -> None:
    teachers = await database.search_teachers(query)
    if not teachers:
        await state.set_state(TeacherSearch.waiting_for_query)
        await _send_or_edit(
            event,
            "🔎 <b>Ничего не найдено</b>\n\n"
            "Проверьте фамилию или введите несколько первых букв ещё раз.",
            reply_markup=home_keyboard(),
        )
        return
    await state.update_data(teacher_candidates=teachers)
    await state.set_state(None)
    await _send_or_edit(
        event,
        "👤 <b>Кого показать?</b>\n\nВыберите преподавателя:",
        reply_markup=teacher_results_keyboard(teachers),
    )


@router.message(TeacherSearch.waiting_for_query, F.text)
async def teacher_search_message(message: Message, state: FSMContext, database: Database) -> None:
    await _teacher_results(message, message.text or "", state, database)


@router.callback_query(TeacherPickCallback.filter())
async def teacher_pick_callback(
    callback: CallbackQuery,
    callback_data: TeacherPickCallback,
    state: FSMContext,
    service: ScheduleService,
) -> None:
    data = await state.get_data()
    candidates = data.get("teacher_candidates", [])
    if not isinstance(candidates, list) or not 0 <= callback_data.index < len(candidates):
        await callback.answer("Поиск устарел, повторите его", show_alert=True)
        return
    await callback.answer()
    teacher = str(candidates[callback_data.index])
    await state.update_data(active_teacher=teacher)
    await _show_teacher_week(callback, teacher, 0, service)


@router.callback_query(TeacherWeekCallback.filter())
async def teacher_week_callback(
    callback: CallbackQuery,
    callback_data: TeacherWeekCallback,
    state: FSMContext,
    service: ScheduleService,
) -> None:
    teacher = (await state.get_data()).get("active_teacher")
    if not teacher:
        await callback.answer("Сначала найдите преподавателя", show_alert=True)
        return
    await callback.answer()
    await _show_teacher_week(callback, str(teacher), callback_data.offset, service)


async def _show_teacher_week(
    event: Message | CallbackQuery,
    teacher: str,
    offset: int,
    service: ScheduleService,
) -> None:
    target = service.today() + timedelta(days=offset * 7)
    start, end = service.week_bounds(target)
    lessons = await service.teacher_week(teacher, target)
    title = "Расписание преподавателя"
    await _send_or_edit(
        event,
        format_week(title, start, end, lessons, teacher=teacher),
        reply_markup=teacher_week_keyboard(offset),
    )


@router.message()
async def fallback(message: Message) -> None:
    await message.answer("Не понял сообщение. Откройте удобное меню командой /start.")
