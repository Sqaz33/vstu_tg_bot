from __future__ import annotations

from aiohttp import web

from vstu_schedule_bot.services.updater import ScheduleUpdater
from vstu_schedule_bot.storage.database import Database


class HealthServer:
    def __init__(
        self,
        database: Database,
        updater: ScheduleUpdater,
        host: str,
        port: int,
    ) -> None:
        self._database = database
        self._updater = updater
        self._host = host
        self._port = port
        self._runner: web.AppRunner | None = None

    async def start(self) -> None:
        app = web.Application()
        app.router.add_get("/health", self._health)
        app.router.add_get("/ready", self._ready)
        self._runner = web.AppRunner(app, access_log=None)
        await self._runner.setup()
        await web.TCPSite(self._runner, self._host, self._port).start()

    async def stop(self) -> None:
        if self._runner is not None:
            await self._runner.cleanup()
            self._runner = None

    async def _health(self, _request: web.Request) -> web.Response:
        result = self._updater.last_result
        return web.json_response(
            {
                "status": "ok",
                "last_update_status": result.status.value if result else "pending",
                "last_checked_at": result.checked_at.isoformat() if result else None,
            }
        )

    async def _ready(self, _request: web.Request) -> web.Response:
        ready = await self._database.is_ready()
        meta = await self._database.get_meta()
        return web.json_response(
            {
                "status": "ready" if ready else "not_ready",
                "schedule_updated_at": meta.get("updated_at") if meta else None,
            },
            status=200 if ready else 503,
        )
