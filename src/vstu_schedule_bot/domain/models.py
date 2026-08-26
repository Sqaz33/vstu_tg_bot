from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import StrEnum


class DateRule(StrEnum):
    WEEKLY = "weekly"
    EXPLICIT = "explicit"


@dataclass(frozen=True, slots=True)
class Lesson:
    group: str
    weekday: int
    slot_start: int
    slot_end: int
    pair_label: str
    starts_at: str
    ends_at: str
    subject: str
    lesson_type: str = ""
    teacher: str = ""
    room: str = ""
    date_rule: DateRule = DateRule.WEEKLY
    explicit_dates: tuple[date, ...] = ()
    source_sheet: str = ""
    raw_text: str = ""

    def occurs_on(self, target: date, semester_start: date, semester_end: date) -> bool:
        if not semester_start <= target <= semester_end or target.weekday() != self.weekday:
            return False
        if self.date_rule is DateRule.EXPLICIT:
            return target in self.explicit_dates
        return True


@dataclass(frozen=True, slots=True)
class ParsedSchedule:
    faculty: str
    academic_year: str
    semester: int | None
    semester_start: date
    semester_end: date
    groups: tuple[str, ...]
    lessons: tuple[Lesson, ...]
    warnings: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class SourceFile:
    label: str
    url: str
    last_modified_text: str = ""


@dataclass(frozen=True, slots=True)
class DownloadedFile:
    source: SourceFile
    content: bytes
    sha256: str
    etag: str | None = None
    last_modified: str | None = None
    not_modified: bool = False


class UpdateStatus(StrEnum):
    UPDATED = "updated"
    UNCHANGED = "unchanged"
    FAILED = "failed"


@dataclass(frozen=True, slots=True)
class UpdateResult:
    status: UpdateStatus
    checked_at: datetime
    groups_count: int = 0
    lessons_count: int = 0
    message: str = ""
    warnings: tuple[str, ...] = field(default_factory=tuple)
