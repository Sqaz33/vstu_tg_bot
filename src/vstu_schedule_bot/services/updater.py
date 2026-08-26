from __future__ import annotations

import asyncio
import logging
import tempfile
from datetime import datetime
from pathlib import Path
from urllib.parse import urlsplit

from vstu_schedule_bot.domain.models import UpdateResult, UpdateStatus
from vstu_schedule_bot.parsing.base import ParserRegistry
from vstu_schedule_bot.parsing.readers import WorkbookReaderRegistry
from vstu_schedule_bot.sources.vstu import VstuSourceClient
from vstu_schedule_bot.storage.database import Database

logger = logging.getLogger(__name__)


class ScheduleUpdater:
    def __init__(
        self,
        *,
        source: VstuSourceClient,
        database: Database,
        readers: WorkbookReaderRegistry,
        parsers: ParserRegistry,
        faculty: str,
        interval_seconds: int,
        timezone: object,
    ) -> None:
        self._source = source
        self._database = database
        self._readers = readers
        self._parsers = parsers
        self._faculty = faculty
        self._interval = interval_seconds
        self._timezone = timezone
        self._lock = asyncio.Lock()
        self.last_result: UpdateResult | None = None

    async def update_once(self) -> UpdateResult:
        if self._lock.locked():
            return UpdateResult(
                status=UpdateStatus.UNCHANGED,
                checked_at=datetime.now(self._timezone),  # type: ignore[arg-type]
                message="Update is already in progress",
            )
        async with self._lock:
            checked_at = datetime.now(self._timezone)  # type: ignore[arg-type]
            source_file = None
            try:
                source_file = await self._source.discover_file()
                state = await self._database.get_source_state(source_file.url)
                downloaded = await self._source.download(
                    source_file,
                    etag=str(state["etag"]) if state and state.get("etag") else None,
                    last_modified=(
                        str(state["last_modified"])
                        if state and state.get("last_modified")
                        else None
                    ),
                )
                if downloaded.not_modified or (state and state.get("sha256") == downloaded.sha256):
                    await self._database.mark_source_checked(
                        source_url=source_file.url,
                        source_label=source_file.label,
                        checked_at=checked_at,
                        status="unchanged",
                    )
                    result = UpdateResult(
                        status=UpdateStatus.UNCHANGED,
                        checked_at=checked_at,
                        message="Source file has not changed",
                    )
                    self.last_result = result
                    logger.debug(
                        "Schedule source is unchanged", extra={"source_url": source_file.url}
                    )
                    return result

                suffix = Path(urlsplit(source_file.url).path).suffix.lower()
                if suffix not in {".xls", ".xlsx", ".xlsm"}:
                    suffix = Path(source_file.label).suffix.lower()
                parsed = await asyncio.to_thread(self._parse_bytes, downloaded.content, suffix)
                await self._database.replace_schedule(
                    parsed,
                    source_url=source_file.url,
                    source_label=source_file.label,
                    sha256=downloaded.sha256,
                    etag=downloaded.etag,
                    last_modified=downloaded.last_modified,
                    checked_at=checked_at,
                )
                result = UpdateResult(
                    status=UpdateStatus.UPDATED,
                    checked_at=checked_at,
                    groups_count=len(parsed.groups),
                    lessons_count=len(parsed.lessons),
                    message="Schedule was updated",
                    warnings=parsed.warnings,
                )
                self.last_result = result
                logger.info(
                    "Schedule updated",
                    extra={
                        "source_url": source_file.url,
                        "groups": len(parsed.groups),
                        "lessons": len(parsed.lessons),
                        "warnings": len(parsed.warnings),
                    },
                )
                return result
            except Exception as error:
                if source_file is not None:
                    await self._database.mark_source_checked(
                        source_url=source_file.url,
                        source_label=source_file.label,
                        checked_at=checked_at,
                        status="failed",
                        error=str(error)[:1000],
                    )
                result = UpdateResult(
                    status=UpdateStatus.FAILED,
                    checked_at=checked_at,
                    message=str(error),
                )
                self.last_result = result
                logger.exception("Schedule update failed")
                return result

    def _parse_bytes(self, content: bytes, suffix: str):  # type: ignore[no-untyped-def]
        temporary_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(
                prefix="vstu-schedule-", suffix=suffix, delete=False
            ) as file:
                file.write(content)
                temporary_path = Path(file.name)
            workbook = self._readers.read(temporary_path)
            return self._parsers.parse(workbook, self._faculty)
        finally:
            if temporary_path is not None:
                temporary_path.unlink(missing_ok=True)

    async def run(self, stop_event: asyncio.Event) -> None:
        while not stop_event.is_set():
            await self.update_once()
            try:
                await asyncio.wait_for(stop_event.wait(), timeout=self._interval)
            except TimeoutError:
                continue
