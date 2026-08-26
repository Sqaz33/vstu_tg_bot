from __future__ import annotations

import asyncio
import contextlib
import logging

import aiohttp
from aiogram import Bot
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.types import BotCommand

from vstu_schedule_bot.bot.app import create_dispatcher
from vstu_schedule_bot.config import get_settings
from vstu_schedule_bot.health import HealthServer
from vstu_schedule_bot.logging_config import configure_logging
from vstu_schedule_bot.parsing.factory import create_parser_registry
from vstu_schedule_bot.parsing.readers import WorkbookReaderRegistry
from vstu_schedule_bot.services.schedule import ScheduleService
from vstu_schedule_bot.services.updater import ScheduleUpdater
from vstu_schedule_bot.sources.vstu import VstuSourceClient
from vstu_schedule_bot.storage.database import Database

logger = logging.getLogger(__name__)


async def run() -> None:
    settings = get_settings()
    configure_logging(settings.log_level, settings.log_format)
    settings.prepare_directories()

    database = Database(settings.database_path)
    await database.connect()
    timeout = aiohttp.ClientTimeout(total=settings.request_timeout_seconds)
    headers = {"User-Agent": "VSTU-Schedule-Bot/0.1 (+https://www.vstu.ru/)"}
    stop_event = asyncio.Event()

    try:
        async with aiohttp.ClientSession(timeout=timeout, headers=headers) as http_session:
            source = VstuSourceClient(
                http_session,
                settings.source_page_url,
                settings.source_file_pattern,
            )
            updater = ScheduleUpdater(
                source=source,
                database=database,
                readers=WorkbookReaderRegistry(),
                parsers=create_parser_registry(),
                faculty=settings.faculty_name,
                interval_seconds=settings.update_interval_seconds,
                timezone=settings.tz,
            )
            service = ScheduleService(database, settings.tz)
            initial_result = await updater.update_once()
            if not await database.is_ready():
                logger.warning(
                    "Starting without schedule data",
                    extra={"initial_update_status": initial_result.status.value},
                )

            health = HealthServer(
                database,
                updater,
                settings.health_host,
                settings.health_port,
            )
            await health.start()
            updater_task = asyncio.create_task(updater.run(stop_event), name="schedule-updater")
            try:
                async with Bot(
                    token=settings.bot_token.get_secret_value(),
                    default=DefaultBotProperties(
                        parse_mode=ParseMode.HTML,
                        link_preview_is_disabled=True,
                    ),
                ) as bot:
                    await bot.set_my_commands(
                        [
                            BotCommand(command="start", description="Главное меню"),
                            BotCommand(command="today", description="Расписание на сегодня"),
                            BotCommand(command="week", description="Расписание на неделю"),
                            BotCommand(command="group", description="Выбрать группу"),
                            BotCommand(command="teacher", description="Найти преподавателя"),
                        ]
                    )
                    dispatcher = create_dispatcher()
                    logger.info("Telegram bot started")
                    await dispatcher.start_polling(
                        bot,
                        database=database,
                        service=service,
                        allowed_updates=dispatcher.resolve_used_update_types(),
                    )
            finally:
                stop_event.set()
                updater_task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await updater_task
                await health.stop()
    finally:
        await database.close()


def main() -> None:
    try:
        asyncio.run(run())
    except (KeyboardInterrupt, SystemExit):
        pass


if __name__ == "__main__":
    main()
