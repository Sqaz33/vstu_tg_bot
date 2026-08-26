from aiogram.filters.callback_data import CallbackData


class ActionCallback(CallbackData, prefix="a"):
    name: str


class GroupCallback(CallbackData, prefix="g"):
    name: str


class DateCallback(CallbackData, prefix="d"):
    value: str


class WeekCallback(CallbackData, prefix="w"):
    value: str


class TeacherPickCallback(CallbackData, prefix="tp"):
    index: int


class TeacherWeekCallback(CallbackData, prefix="tw"):
    offset: int
