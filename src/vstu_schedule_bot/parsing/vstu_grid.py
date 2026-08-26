from __future__ import annotations

import re
from collections import Counter
from datetime import date
from statistics import median

from vstu_schedule_bot.domain.models import DateRule, Lesson, ParsedSchedule
from vstu_schedule_bot.parsing.base import CellRegion, ScheduleParser, SheetGrid, WorkbookGrid

DAY_NAMES = {
    "ПОНЕДЕЛЬНИК": 0,
    "ВТОРНИК": 1,
    "СРЕДА": 2,
    "ЧЕТВЕРГ": 3,
    "ПЯТНИЦА": 4,
    "СУББОТА": 5,
    "ВОСКРЕСЕНЬЕ": 6,
}
PAIR_TIMES = {
    1: ("08:30", "09:15"),
    2: ("09:20", "10:00"),
    3: ("10:10", "10:55"),
    4: ("11:00", "11:40"),
    5: ("11:50", "12:35"),
    6: ("12:40", "13:20"),
    7: ("13:40", "14:25"),
    8: ("14:30", "15:10"),
    9: ("15:20", "16:05"),
    10: ("16:10", "16:50"),
    11: ("17:00", "17:45"),
    12: ("17:50", "18:30"),
    13: ("18:35", "19:15"),
    14: ("19:20", "20:00"),
    15: ("20:05", "20:45"),
    16: ("20:50", "21:30"),
}

_GROUP_RE = re.compile(r"^[A-ZА-ЯЁ]{1,12}\s*-\s*\d(?:[.\dA-ZА-ЯЁ]*)?$", re.IGNORECASE)
_PAIR_RE = re.compile(r"^\s*(\d{1,2})\s*[-–]\s*(\d{1,2})\s*$")
_DATE_RE = re.compile(r"(?<!\d)(\d{1,2})\s*\.\s*(\d{1,2})(?:\s*\.\s*(\d{2,4}))?(?!\d)")
_YEAR_RE = re.compile(r"(20\d{2})\s*[-–]\s*(20\d{2})")
_INITIALS_RE = re.compile(r"\b[А-ЯЁA-Z][а-яёa-z-]+\s+(?:[А-ЯЁA-Z]\.){1,2}", re.IGNORECASE)
_ROOM_RE = re.compile(
    r"^(?:[А-ЯЁA-Z]{1,3}\s*[-–]?\s*)?\d{3,4}(?:\s*[-–]\s*\d+)?[А-ЯЁA-ZА-Яа-яё]?$",
    re.IGNORECASE,
)
_TRAILING_ROOM_RE = re.compile(
    r"(?:^|\s)((?:[А-ЯЁA-Z]{1,3}\s*[-–]?\s*)?\d{3,4}(?:\s*[-–]\s*\d+)?[А-ЯЁA-ZА-Яа-яё]?)$",
    re.IGNORECASE,
)
_TYPE_RE = re.compile(
    r"\b(лекц(?:ия|\.)?|лаб(?:ораторная|\.)?|практ(?:ика|ическая|\.)?|семинар|"
    r"консультация)\b",
    re.IGNORECASE,
)
_NON_SUBJECT_RE = re.compile(r"^(?:\d+\s*[-–]\s*\d+\s*ч\.?|\d+\s*час\.?)$", re.IGNORECASE)


def normalize_group(value: str) -> str:
    return re.sub(r"\s*-\s*", "-", " ".join(value.upper().split()))


def extract_groups(value: str) -> tuple[str, ...]:
    candidates = [part.strip() for part in re.split(r"[,;/]", value) if part.strip()]
    if candidates and all(_GROUP_RE.fullmatch(part) for part in candidates):
        return tuple(normalize_group(part) for part in candidates)
    if _GROUP_RE.fullmatch(value):
        return (normalize_group(value),)
    return ()


def _unique(values: list[str]) -> list[str]:
    return list(dict.fromkeys(value for value in values if value))


class VstuGridParser(ScheduleParser):
    """Parser for the merged-cell grid used by VSTU faculty schedule files.

    Coordinates are discovered from semantic anchors rather than hard-coded. A new
    faculty layout can therefore use this parser when it keeps the group/day/pair
    vocabulary, or register a higher-scoring parser through ``ParserRegistry``.
    """

    name = "vstu-merged-grid-v1"

    def score(self, workbook: WorkbookGrid) -> int:
        best = 0
        for sheet in workbook.sheets:
            groups = sum(len(extract_groups(value)) for row in sheet.values for value in row)
            days = sum(1 for row in sheet.values for value in row if value.upper() in DAY_NAMES)
            pairs = sum(1 for row in sheet.values for value in row if _PAIR_RE.fullmatch(value))
            best = max(best, groups * 3 + days * 2 + min(pairs, 12))
        return best

    def parse(self, workbook: WorkbookGrid, faculty: str) -> ParsedSchedule:
        academic_year, year_start, year_end = self._academic_year(workbook)
        semester = self._semester(workbook)
        semester_start, semester_end = self._semester_bounds(year_start, year_end, semester)
        lessons: list[Lesson] = []
        groups: list[str] = []
        warnings: list[str] = []

        for sheet in workbook.sheets:
            sheet_groups, sheet_lessons, sheet_warnings = self._parse_sheet(
                sheet,
                year_start=year_start,
                year_end=year_end,
                semester_start=semester_start,
                semester_end=semester_end,
            )
            groups.extend(sheet_groups)
            lessons.extend(sheet_lessons)
            warnings.extend(sheet_warnings)

        groups = _unique(groups)
        lessons = list(dict.fromkeys(lessons))
        if not groups:
            raise ValueError("Workbook contains no recognizable group headers")
        if not lessons:
            warnings.append("No lessons were recognized in the workbook")

        return ParsedSchedule(
            faculty=faculty,
            academic_year=academic_year,
            semester=semester,
            semester_start=semester_start,
            semester_end=semester_end,
            groups=tuple(groups),
            lessons=tuple(lessons),
            warnings=tuple(warnings),
        )

    def _parse_sheet(
        self,
        sheet: SheetGrid,
        *,
        year_start: int,
        year_end: int,
        semester_start: date,
        semester_end: date,
    ) -> tuple[list[str], list[Lesson], list[str]]:
        group_rows: Counter[int] = Counter()
        group_cells: list[tuple[int, int, tuple[str, ...]]] = []
        for row_index, row in enumerate(sheet.values):
            for col_index, value in enumerate(row):
                aliases = extract_groups(value)
                if aliases:
                    group_rows[row_index] += len(aliases)
                    group_cells.append((row_index, col_index, aliases))
        if not group_rows:
            return [], [], [f"{sheet.name}: group header was not found"]

        header_row = max(group_rows, key=lambda row: (group_rows[row], -row))
        header_groups = sorted(
            ((col, aliases) for row, col, aliases in group_cells if row == header_row),
            key=lambda item: item[0],
        )
        if not header_groups:
            return [], [], [f"{sheet.name}: group header row is empty"]

        starts = [item[0] for item in header_groups]
        differences = [
            right - left for left, right in zip(starts, starts[1:], strict=False) if right > left
        ]
        band_width = max(2, min(12, round(median(differences)) if differences else 4))
        group_bands = [
            (aliases, col, starts[index + 1] if index + 1 < len(starts) else col + band_width)
            for index, (col, aliases) in enumerate(header_groups)
        ]

        day_anchors: list[tuple[int, int]] = []
        for region in sheet.regions:
            day = DAY_NAMES.get(region.value.upper())
            if day is not None and region.row_start >= header_row:
                day_anchors.append((region.row_start, day))
        day_anchors = sorted(dict.fromkeys(day_anchors))
        if not day_anchors:
            return (
                [group for aliases, _, _ in group_bands for group in aliases],
                [],
                [f"{sheet.name}: weekday anchors were not found"],
            )

        lesson_columns: Counter[int] = Counter()
        for row in sheet.values:
            for col, value in enumerate(row):
                if _PAIR_RE.fullmatch(value):
                    lesson_columns[col] += 1
        if not lesson_columns:
            return (
                [group for aliases, _, _ in group_bands for group in aliases],
                [],
                [f"{sheet.name}: lesson-number column was not found"],
            )
        lesson_col = lesson_columns.most_common(1)[0][0]

        lessons: list[Lesson] = []
        for day_index, (day_start, weekday) in enumerate(day_anchors):
            day_end = (
                day_anchors[day_index + 1][0] if day_index + 1 < len(day_anchors) else sheet.rows
            )
            slots = self._slots(sheet, lesson_col, day_start, day_end)
            if not slots:
                continue
            for aliases, col_start, col_end in group_bands:
                subjects = [
                    region
                    for region in sheet.regions
                    if region.intersects(day_start, day_end, col_start, col_end)
                    and self._is_subject(region.value)
                ]
                subjects.sort(
                    key=lambda region: (region.row_start, region.col_start, region.row_end)
                )
                for subject_index, subject_region in enumerate(subjects):
                    following_rows = [
                        candidate.row_start
                        for candidate in subjects[subject_index + 1 :]
                        if candidate.row_start > subject_region.row_start
                    ]
                    detail_end = min([day_end, subject_region.row_end + 7, *following_rows])
                    detail_col_start = min(col_start, subject_region.col_start)
                    detail_col_end = max(col_end, subject_region.col_end)
                    related = [
                        region
                        for region in sheet.regions
                        if region.intersects(
                            subject_region.row_start,
                            detail_end,
                            detail_col_start,
                            detail_col_end,
                        )
                    ]
                    for group in aliases:
                        lesson = self._build_lesson(
                            group=group,
                            weekday=weekday,
                            slots=slots,
                            subject_region=subject_region,
                            related=related,
                            year_start=year_start,
                            year_end=year_end,
                            semester_start=semester_start,
                            semester_end=semester_end,
                            sheet_name=sheet.name,
                        )
                        if lesson is not None:
                            lessons.append(lesson)

        return [group for aliases, _, _ in group_bands for group in aliases], lessons, []

    @staticmethod
    def _slots(
        sheet: SheetGrid, lesson_col: int, day_start: int, day_end: int
    ) -> list[tuple[int, int, int, str]]:
        result: list[tuple[int, int, int, str]] = []
        for row in range(day_start, day_end):
            match = _PAIR_RE.fullmatch(sheet.value(row, lesson_col))
            if match:
                start, end = int(match.group(1)), int(match.group(2))
                result.append((row, start, end, f"{start}–{end}"))
        return result

    def _build_lesson(
        self,
        *,
        group: str,
        weekday: int,
        slots: list[tuple[int, int, int, str]],
        subject_region: CellRegion,
        related: list[CellRegion],
        year_start: int,
        year_end: int,
        semester_start: date,
        semester_end: date,
        sheet_name: str,
        event_row_end: int | None = None,
        fallback_dates: tuple[date, ...] = (),
    ) -> Lesson | None:
        preceding = [slot for slot in slots if slot[0] <= subject_region.row_start]
        if not preceding:
            return None
        event_start_row = preceding[-1][0]
        event_end_row = event_row_end or subject_region.row_end
        covered_slots = [slot for slot in slots if event_start_row <= slot[0] < event_end_row]
        if not covered_slots:
            covered_slots = [preceding[-1]]

        first_slot, last_slot = covered_slots[0], covered_slots[-1]
        slot_start, slot_end = first_slot[1], last_slot[2]
        starts_at = PAIR_TIMES.get(slot_start, ("", ""))[0]
        ends_at = PAIR_TIMES.get(slot_end, ("", ""))[1]
        pair_label = f"{slot_start}–{slot_end}"

        subject = _TYPE_RE.sub("", subject_region.value).strip(" ()-,.;")
        if not subject:
            return None
        text_values = _unique([region.value for region in related])
        dates: list[date] = []
        teachers: list[str] = []
        rooms: list[str] = []
        types: list[str] = []
        has_explicit_date_text = False
        for value in text_values:
            has_explicit_date_text = has_explicit_date_text or bool(_DATE_RE.search(value))
            dates.extend(self._dates(value, year_start, year_end))
            type_match = _TYPE_RE.search(value)
            if type_match:
                types.append(self._normalize_type(type_match.group(1)))
            if self._is_teacher(value):
                teacher, trailing_room = self._split_teacher_room(value)
                teachers.append(teacher)
                if trailing_room:
                    rooms.append(trailing_room)
            elif self._is_room(value):
                rooms.append(value)

        valid_dates = sorted(
            {
                value
                for value in dates
                if semester_start <= value <= semester_end and value.weekday() == weekday
            }
        )
        occurrence_dates = tuple(valid_dates) if has_explicit_date_text else fallback_dates
        return Lesson(
            group=group,
            weekday=weekday,
            slot_start=slot_start,
            slot_end=slot_end,
            pair_label=pair_label,
            starts_at=starts_at,
            ends_at=ends_at,
            subject=subject,
            lesson_type=" / ".join(_unique(types)),
            teacher="; ".join(_unique(teachers)),
            room=" / ".join(_unique(rooms)),
            date_rule=(
                DateRule.EXPLICIT if has_explicit_date_text or fallback_dates else DateRule.WEEKLY
            ),
            explicit_dates=occurrence_dates,
            source_sheet=sheet_name,
            raw_text=" | ".join(text_values),
        )

    @staticmethod
    def _is_subject(value: str) -> bool:
        normalized = " ".join(value.split()).strip()
        upper = normalized.upper()
        if len(normalized) < 3 or upper in DAY_NAMES or _PAIR_RE.fullmatch(normalized):
            return False
        if _DATE_RE.search(normalized) or _NON_SUBJECT_RE.fullmatch(normalized):
            return False
        if _TYPE_RE.fullmatch(normalized) or VstuGridParser._is_teacher(normalized):
            return False
        if VstuGridParser._is_room(normalized):
            return False
        alpha = [char for char in normalized if char.isalpha()]
        if not alpha:
            return False
        uppercase_ratio = sum(char.isupper() for char in alpha) / len(alpha)
        return uppercase_ratio >= 0.72 or len(normalized) >= 18

    @staticmethod
    def _is_teacher(value: str) -> bool:
        return bool(_INITIALS_RE.search(value)) or value.strip().upper() in {"ВАКАНСИЯ", "ВАКАНТНО"}

    @staticmethod
    def _is_room(value: str) -> bool:
        normalized = " ".join(value.replace("ауд.", "").replace("ауд", "").split())
        return bool(_ROOM_RE.fullmatch(normalized))

    @staticmethod
    def _split_teacher_room(value: str) -> tuple[str, str]:
        match = _TRAILING_ROOM_RE.search(value)
        if match and match.start(1) > 0:
            return value[: match.start(1)].strip(" ,;"), match.group(1).strip()
        return value.strip(), ""

    @staticmethod
    def _normalize_type(value: str) -> str:
        lower = value.lower()
        if lower.startswith("лек"):
            return "лекция"
        if lower.startswith("лаб"):
            return "лабораторная"
        if lower.startswith("практ"):
            return "практика"
        return lower.rstrip(".")

    @staticmethod
    def _dates(value: str, year_start: int, year_end: int) -> list[date]:
        result: list[date] = []
        for day_text, month_text, year_text in _DATE_RE.findall(value):
            day, month = int(day_text), int(month_text)
            if year_text:
                year = int(year_text)
                if year < 100:
                    year += 2000
            else:
                year = year_start if month >= 8 else year_end
            try:
                result.append(date(year, month, day))
            except ValueError:
                continue
        return result

    @staticmethod
    def _all_text(workbook: WorkbookGrid) -> str:
        return " ".join(value for sheet in workbook.sheets for row in sheet.values for value in row)

    def _academic_year(self, workbook: WorkbookGrid) -> tuple[str, int, int]:
        match = _YEAR_RE.search(self._all_text(workbook))
        if match:
            start, end = int(match.group(1)), int(match.group(2))
            return f"{start}–{end}", start, end
        current = date.today().year
        start = current if date.today().month >= 8 else current - 1
        return f"{start}–{start + 1}", start, start + 1

    def _semester(self, workbook: WorkbookGrid) -> int | None:
        text = self._all_text(workbook).upper()
        if re.search(r"(?:\bI\b|\b1)\s*(?:-?Й)?\s*СЕМЕСТР", text):
            return 1
        if re.search(r"(?:\bII\b|\b2)\s*(?:-?Й)?\s*СЕМЕСТР", text):
            return 2
        return None

    @staticmethod
    def _semester_bounds(year_start: int, year_end: int, semester: int | None) -> tuple[date, date]:
        if semester == 2:
            return date(year_end, 2, 1), date(year_end, 6, 30)
        return date(year_start, 9, 1), date(year_start, 12, 31)
