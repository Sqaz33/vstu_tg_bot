from aiogram.fsm.state import State, StatesGroup


class GroupSearch(StatesGroup):
    waiting_for_query = State()


class TeacherSearch(StatesGroup):
    waiting_for_query = State()
