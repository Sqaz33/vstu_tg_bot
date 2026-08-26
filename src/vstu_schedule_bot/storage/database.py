from __future__ import annotations

import asyncio
import json
import re
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import aiosqlite

from vstu_schedule_bot.domain.models import DateRule, Lesson, ParsedSchedule


def normalize_search(value: str) -> str:
    return re.sub(r"[^a-zа-яё0-9]+", " ", value.casefold().replace("ё", "е")).strip()


class Database:
    def __init__(self, path: Path) -> None:
        self._path = path
        self._connection: aiosqlite.Connection | None = None
        self._write_lock = asyncio.Lock()

    @property
    def connection(self) -> aiosqlite.Connection:
        if self._connection is None:
            raise RuntimeError("Database is not connected")
        return self._connection

    async def connect(self) -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = await aiosqlite.connect(self._path)
        self._connection.row_factory = aiosqlite.Row
        await self._connection.execute("PRAGMA journal_mode=WAL")
        await self._connection.execute("PRAGMA synchronous=NORMAL")
        await self._connection.execute("PRAGMA foreign_keys=ON")
        await self._connection.execute("PRAGMA busy_timeout=5000")
        await self._create_schema()

    async def close(self) -> None:
        if self._connection is not None:
            await self._connection.close()
            self._connection = None

    async def _create_schema(self) -> None:
        await self.connection.executescript(
            """
            CREATE TABLE IF NOT EXISTS schedule_meta (
                id INTEGER PRIMARY KEY CHECK (id = 1),
                faculty TEXT NOT NULL,
                academic_year TEXT NOT NULL,
                semester INTEGER,
                semester_start TEXT NOT NULL,
                semester_end TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS groups (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                name TEXT NOT NULL UNIQUE,
                name_norm TEXT NOT NULL
            );

            CREATE TABLE IF NOT EXISTS lessons (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                group_id INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
                weekday INTEGER NOT NULL CHECK (weekday BETWEEN 0 AND 6),
                slot_start INTEGER NOT NULL,
                slot_end INTEGER NOT NULL,
                pair_label TEXT NOT NULL,
                starts_at TEXT NOT NULL,
                ends_at TEXT NOT NULL,
                subject TEXT NOT NULL,
                lesson_type TEXT NOT NULL DEFAULT '',
                teacher TEXT NOT NULL DEFAULT '',
                teacher_norm TEXT NOT NULL DEFAULT '',
                room TEXT NOT NULL DEFAULT '',
                date_rule TEXT NOT NULL,
                explicit_dates TEXT NOT NULL DEFAULT '[]',
                source_sheet TEXT NOT NULL DEFAULT '',
                raw_text TEXT NOT NULL DEFAULT ''
            );
            CREATE INDEX IF NOT EXISTS idx_lessons_group_weekday
                ON lessons(group_id, weekday, slot_start);
            CREATE INDEX IF NOT EXISTS idx_lessons_teacher
                ON lessons(teacher_norm);

            CREATE TABLE IF NOT EXISTS source_state (
                url TEXT PRIMARY KEY,
                label TEXT NOT NULL,
                sha256 TEXT,
                etag TEXT,
                last_modified TEXT,
                checked_at TEXT NOT NULL,
                updated_at TEXT,
                status TEXT NOT NULL,
                error TEXT
            );

            CREATE TABLE IF NOT EXISTS user_preferences (
                user_id INTEGER PRIMARY KEY,
                group_name TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
            """
        )
        await self.connection.commit()

    async def replace_schedule(
        self,
        schedule: ParsedSchedule,
        *,
        source_url: str,
        source_label: str,
        sha256: str,
        etag: str | None,
        last_modified: str | None,
        checked_at: datetime,
    ) -> None:
        async with self._write_lock:
            try:
                await self.connection.execute("BEGIN IMMEDIATE")
                await self.connection.execute("DELETE FROM lessons")
                await self.connection.execute("DELETE FROM groups")
                group_ids: dict[str, int] = {}
                for group in schedule.groups:
                    cursor = await self.connection.execute(
                        "INSERT INTO groups(name, name_norm) VALUES (?, ?)",
                        (group, normalize_search(group)),
                    )
                    if cursor.lastrowid is None:
                        raise RuntimeError(f"Could not insert group {group}")
                    group_ids[group] = cursor.lastrowid

                lesson_rows = [
                    (
                        group_ids[lesson.group],
                        lesson.weekday,
                        lesson.slot_start,
                        lesson.slot_end,
                        lesson.pair_label,
                        lesson.starts_at,
                        lesson.ends_at,
                        lesson.subject,
                        lesson.lesson_type,
                        lesson.teacher,
                        normalize_search(lesson.teacher),
                        lesson.room,
                        lesson.date_rule.value,
                        json.dumps([value.isoformat() for value in lesson.explicit_dates]),
                        lesson.source_sheet,
                        lesson.raw_text,
                    )
                    for lesson in schedule.lessons
                ]
                await self.connection.executemany(
                    """
                    INSERT INTO lessons(
                        group_id, weekday, slot_start, slot_end, pair_label,
                        starts_at, ends_at, subject, lesson_type, teacher,
                        teacher_norm, room, date_rule, explicit_dates,
                        source_sheet, raw_text
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    lesson_rows,
                )
                now = checked_at.isoformat()
                await self.connection.execute(
                    """
                    INSERT INTO schedule_meta(
                        id, faculty, academic_year, semester, semester_start,
                        semester_end, updated_at
                    ) VALUES (1, ?, ?, ?, ?, ?, ?)
                    ON CONFLICT(id) DO UPDATE SET
                        faculty=excluded.faculty,
                        academic_year=excluded.academic_year,
                        semester=excluded.semester,
                        semester_start=excluded.semester_start,
                        semester_end=excluded.semester_end,
                        updated_at=excluded.updated_at
                    """,
                    (
                        schedule.faculty,
                        schedule.academic_year,
                        schedule.semester,
                        schedule.semester_start.isoformat(),
                        schedule.semester_end.isoformat(),
                        now,
                    ),
                )
                await self.connection.execute(
                    """
                    INSERT INTO source_state(
                        url, label, sha256, etag, last_modified, checked_at,
                        updated_at, status, error
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, 'updated', NULL)
                    ON CONFLICT(url) DO UPDATE SET
                        label=excluded.label,
                        sha256=excluded.sha256,
                        etag=excluded.etag,
                        last_modified=excluded.last_modified,
                        checked_at=excluded.checked_at,
                        updated_at=excluded.updated_at,
                        status='updated',
                        error=NULL
                    """,
                    (source_url, source_label, sha256, etag, last_modified, now, now),
                )
                await self.connection.commit()
            except BaseException:
                await self.connection.rollback()
                raise

    async def mark_source_checked(
        self,
        *,
        source_url: str,
        source_label: str,
        checked_at: datetime,
        status: str,
        error: str | None = None,
    ) -> None:
        async with self._write_lock:
            await self.connection.execute(
                """
                INSERT INTO source_state(url, label, checked_at, status, error)
                VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(url) DO UPDATE SET
                    label=excluded.label,
                    checked_at=excluded.checked_at,
                    status=excluded.status,
                    error=excluded.error
                """,
                (source_url, source_label, checked_at.isoformat(), status, error),
            )
            await self.connection.commit()

    async def get_source_state(self, url: str) -> dict[str, Any] | None:
        cursor = await self.connection.execute("SELECT * FROM source_state WHERE url = ?", (url,))
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def get_meta(self) -> dict[str, Any] | None:
        cursor = await self.connection.execute("SELECT * FROM schedule_meta WHERE id = 1")
        row = await cursor.fetchone()
        return dict(row) if row else None

    async def is_ready(self) -> bool:
        cursor = await self.connection.execute("SELECT EXISTS(SELECT 1 FROM groups)")
        row = await cursor.fetchone()
        return bool(row and row[0])

    async def list_groups(self, query: str = "", limit: int = 100) -> list[str]:
        normalized = normalize_search(query)
        if normalized:
            cursor = await self.connection.execute(
                "SELECT name FROM groups WHERE name_norm LIKE ? ORDER BY name LIMIT ?",
                (f"%{normalized}%", limit),
            )
        else:
            cursor = await self.connection.execute(
                "SELECT name FROM groups ORDER BY name LIMIT ?", (limit,)
            )
        return [str(row[0]) for row in await cursor.fetchall()]

    async def set_user_group(self, user_id: int, group: str) -> None:
        async with self._write_lock:
            await self.connection.execute(
                """
                INSERT INTO user_preferences(user_id, group_name, updated_at)
                VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET
                    group_name=excluded.group_name,
                    updated_at=excluded.updated_at
                """,
                (user_id, group, datetime.now().astimezone().isoformat()),
            )
            await self.connection.commit()

    async def get_user_group(self, user_id: int) -> str | None:
        cursor = await self.connection.execute(
            "SELECT group_name FROM user_preferences WHERE user_id = ?", (user_id,)
        )
        row = await cursor.fetchone()
        if not row:
            return None
        group = str(row[0])
        cursor = await self.connection.execute("SELECT 1 FROM groups WHERE name = ?", (group,))
        return group if await cursor.fetchone() else None

    async def lessons_for_group(
        self, group: str, start: date, end: date
    ) -> list[tuple[date, Lesson]]:
        rows = await self._lesson_rows(
            "WHERE g.name = ? AND l.weekday BETWEEN ? AND ?",
            (group, 0, 6),
        )
        return await self._materialize(rows, start, end)

    async def search_teachers(self, query: str, limit: int = 8) -> list[str]:
        normalized = normalize_search(query)
        if len(normalized) < 2:
            return []
        cursor = await self.connection.execute(
            """
            SELECT DISTINCT teacher FROM lessons
            WHERE teacher_norm LIKE ? AND teacher != ''
            ORDER BY teacher
            LIMIT 50
            """,
            (f"%{normalized}%",),
        )
        result: list[str] = []
        for row in await cursor.fetchall():
            for teacher in (part.strip() for part in str(row[0]).split(";")):
                if normalized in normalize_search(teacher) and teacher not in result:
                    result.append(teacher)
                    if len(result) == limit:
                        return result
        return result

    async def lessons_for_teacher(
        self, teacher: str, start: date, end: date
    ) -> list[tuple[date, Lesson]]:
        normalized = normalize_search(teacher)
        rows = await self._lesson_rows(
            "WHERE l.teacher_norm LIKE ?",
            (f"%{normalized}%",),
        )
        return await self._materialize(rows, start, end)

    async def _lesson_rows(self, where: str, params: tuple[object, ...]) -> list[aiosqlite.Row]:
        cursor = await self.connection.execute(
            f"""
            SELECT l.*, g.name AS group_name
            FROM lessons l
            JOIN groups g ON g.id = l.group_id
            {where}
            ORDER BY l.weekday, l.slot_start, g.name, l.subject
            """,  # noqa: S608 - where clauses are internal constants only
            params,
        )
        return list(await cursor.fetchall())

    async def _materialize(
        self, rows: list[aiosqlite.Row], start: date, end: date
    ) -> list[tuple[date, Lesson]]:
        meta = await self.get_meta()
        if not meta:
            return []
        semester_start = date.fromisoformat(str(meta["semester_start"]))
        semester_end = date.fromisoformat(str(meta["semester_end"]))
        lessons = [self._row_to_lesson(row) for row in rows]
        result: list[tuple[date, Lesson]] = []
        target = start
        while target <= end:
            result.extend(
                (target, lesson)
                for lesson in lessons
                if lesson.occurs_on(target, semester_start, semester_end)
            )
            target += timedelta(days=1)
        return sorted(result, key=lambda item: (item[0], item[1].slot_start, item[1].group))

    @staticmethod
    def _row_to_lesson(row: aiosqlite.Row) -> Lesson:
        return Lesson(
            group=str(row["group_name"]),
            weekday=int(row["weekday"]),
            slot_start=int(row["slot_start"]),
            slot_end=int(row["slot_end"]),
            pair_label=str(row["pair_label"]),
            starts_at=str(row["starts_at"]),
            ends_at=str(row["ends_at"]),
            subject=str(row["subject"]),
            lesson_type=str(row["lesson_type"]),
            teacher=str(row["teacher"]),
            room=str(row["room"]),
            date_rule=DateRule(str(row["date_rule"])),
            explicit_dates=tuple(
                date.fromisoformat(value) for value in json.loads(str(row["explicit_dates"]))
            ),
            source_sheet=str(row["source_sheet"]),
            raw_text=str(row["raw_text"]),
        )
