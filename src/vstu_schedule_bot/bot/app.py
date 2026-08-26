from __future__ import annotations

import logging

from aiogram import Dispatcher
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import ErrorEvent

from vstu_schedule_bot.bot.handlers import router

logger = logging.getLogger(__name__)


def create_dispatcher() -> Dispatcher:
    dispatcher = Dispatcher(storage=MemoryStorage())
    dispatcher.include_router(router)

    @dispatcher.errors()
    async def handle_error(event: ErrorEvent) -> bool:
        logger.exception(
            "Unhandled Telegram update error",
            exc_info=event.exception,
            extra={"update_id": event.update.update_id},
        )
        return True

    return dispatcher
