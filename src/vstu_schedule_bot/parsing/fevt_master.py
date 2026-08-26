from __future__ import annotations

import re
from collections import Counter
from datetime import date
from statistics import median

from vstu_schedule_bot.domain.models import Lesson, ParsedSchedule
from vstu_schedule_bot.parsing.base import CellRegion, SheetGrid, WorkbookGrid
from vstu_schedule_bot.parsing.vstu_grid import (
    _PAIR_RE,
    DAY_NAMES,
    VstuGridParser,
    extract_groups,
)

_MONTHS = {
    "ЯНВАРЬ": 1,
    "ФЕВРАЛЬ": 2,
    "МАРТ": 3,
    "АПРЕЛЬ": 4,
    "МАЙ": 5,
    "ИЮНЬ": 6,
    "ИЮЛЬ": 7,
    "АВГУСТ": 8,
    "СЕНТЯБРЬ": 9,
    "ОКТЯБРЬ": 10,
    "НОЯБРЬ": 11,
    "ДЕКАБРЬ": 12,
}
_DAY_NUMBER_RE = re.compile(r"^\d{1,2}$")


class FevtMasterGridParser(VstuGridParser):
    """Formatting-aware parser for the first-year FEVT master's workbook.

    The workbook contains two consecutive calendar grids. Month-column numbers
    define the default dates for a weekday in each grid. Dates printed inside a
    bordered lesson card override them. Merged subject cells define shared group
    ownership, while the next subject or card border defines lesson duration.
    """

    name = "vstu-fevt-master-year1-v2"

    def score(self, workbook: WorkbookGrid) -> int:
        text = self._all_text(workbook).upper()
        groups = {
            group
            for sheet in workbook.sheets
            for row in sheet.values
            for value in row
            for group in extract_groups(value)
        }
        has_formatting = any(sheet.styles for sheet in workbook.sheets)
        is_first_year = bool(re.search(r"\b1\s+(?:КУРС|КУРСА)\b", text))
        if (
            has_formatting
            and "ФЭВТ" in text
            and is_first_year
            and {"ПОАС-1.1", "ПОАС-1.2"}.issubset(groups)
        ):
            return 10_000 + super().score(workbook)
        return 0

    def parse(self, workbook: WorkbookGrid, faculty: str) -> ParsedSchedule:
        academic_year, year_start, year_end = self._academic_year(workbook)
        semester = self._semester(workbook)
        semester_start, semester_end = self._semester_bounds(year_start, year_end, semester)
        groups: list[str] = []
        lessons: list[Lesson] = []
        warnings: list[str] = []

        for sheet in workbook.sheets:
            sheet_groups, sheet_lessons, sheet_warnings = self._parse_formatted_sheet(
                sheet,
                year_start=year_start,
                year_end=year_end,
                semester_start=semester_start,
                semester_end=semester_end,
            )
            groups.extend(sheet_groups)
            lessons.extend(sheet_lessons)
            warnings.extend(sheet_warnings)

        unique_groups = tuple(dict.fromkeys(groups))
        unique_lessons = tuple(dict.fromkeys(lessons))
        if not unique_groups:
            raise ValueError("FEVT workbook contains no recognizable group headers")
        if not unique_lessons:
            warnings.append("No formatting-aware lessons were recognized")
        return ParsedSchedule(
            faculty=faculty,
            academic_year=academic_year,
            semester=semester,
            semester_start=semester_start,
            semester_end=semester_end,
            groups=unique_groups,
            lessons=unique_lessons,
            warnings=tuple(warnings),
        )

    def _parse_formatted_sheet(
        self,
        sheet: SheetGrid,
        *,
        year_start: int,
        year_end: int,
        semester_start: date,
        semester_end: date,
    ) -> tuple[list[str], list[Lesson], list[str]]:
        header_row, group_bands = self._group_bands(sheet)
        if header_row is None or not group_bands:
            return [], [], [f"{sheet.name}: formatted group header was not found"]
        month_columns = self._month_columns(sheet, header_row)
        if not month_columns:
            return [], [], [f"{sheet.name}: month columns were not found"]

        lesson_col = self._lesson_column(sheet)
        if lesson_col is None:
            return [], [], [f"{sheet.name}: lesson-number column was not found"]
        day_anchors = sorted(
            dict.fromkeys(
                (region.row_start, DAY_NAMES[region.value.upper()])
                for region in sheet.regions
                if region.row_start >= header_row and region.value.upper() in DAY_NAMES
            )
        )
        day_steps = [
            right[0] - left[0]
            for left, right in zip(day_anchors, day_anchors[1:], strict=False)
            if 0 < right[0] - left[0] <= 36
        ]
        day_height = round(median(day_steps)) if day_steps else 18
        lessons: list[Lesson] = []
        for day_index, (day_start, weekday) in enumerate(day_anchors):
            next_anchor = (
                day_anchors[day_index + 1][0] if day_index + 1 < len(day_anchors) else sheet.rows
            )
            day_end = min(next_anchor, day_start + day_height)
            slots = self._slots(sheet, lesson_col, day_start, day_end)
            if not slots:
                continue
            calendar_dates = self._calendar_dates(
                sheet,
                day_start,
                day_end,
                weekday,
                month_columns,
                year_start,
                year_end,
                semester_start,
                semester_end,
            )
            all_subjects = [
                region
                for region in sheet.regions
                if day_start <= region.row_start < day_end
                and region.col_start > lesson_col
                and self._is_subject(region.value)
            ]
            all_subjects.sort(key=lambda region: (region.row_start, region.col_start))

            for aliases, col_start, col_end in group_bands:
                subjects = [
                    region
                    for region in all_subjects
                    if region.intersects(day_start, day_end, col_start, col_end)
                ]
                for subject in subjects:
                    following = [
                        candidate.row_start
                        for candidate in subjects
                        if candidate.row_start > subject.row_start
                    ]
                    next_subject_row = min(following, default=day_end)
                    border_end = self._card_border_end(
                        sheet,
                        subject,
                        col_start,
                        col_end,
                        next_subject_row,
                    )
                    event_end = min(day_end, next_subject_row, border_end)
                    detail_col_start, detail_col_end = self._detail_columns(
                        subject, col_start, col_end
                    )
                    related = [
                        region
                        for region in sheet.regions
                        if region.intersects(
                            subject.row_start,
                            event_end,
                            detail_col_start,
                            detail_col_end,
                        )
                    ]
                    for group in aliases:
                        lesson = self._build_lesson(
                            group=group,
                            weekday=weekday,
                            slots=slots,
                            subject_region=subject,
                            related=related,
                            year_start=year_start,
                            year_end=year_end,
                            semester_start=semester_start,
                            semester_end=semester_end,
                            sheet_name=sheet.name,
                            event_row_end=event_end,
                            fallback_dates=calendar_dates,
                        )
                        if lesson is not None:
                            lessons.append(lesson)

        groups = [group for aliases, _, _ in group_bands for group in aliases]
        return groups, lessons, []

    @staticmethod
    def _group_bands(
        sheet: SheetGrid,
    ) -> tuple[int | None, list[tuple[tuple[str, ...], int, int]]]:
        row_counts: Counter[int] = Counter()
        cells: list[tuple[int, int, tuple[str, ...]]] = []
        for row_index, row in enumerate(sheet.values):
            for col_index, value in enumerate(row):
                aliases = extract_groups(value)
                if aliases:
                    row_counts[row_index] += len(aliases)
                    cells.append((row_index, col_index, aliases))
        if not row_counts:
            return None, []
        header_row = max(row_counts, key=lambda row: (row_counts[row], -row))
        headers = sorted(
            ((col, aliases) for row, col, aliases in cells if row == header_row),
            key=lambda item: item[0],
        )
        starts = [col for col, _ in headers]
        differences = [
            right - left for left, right in zip(starts, starts[1:], strict=False) if right > left
        ]
        band_width = max(2, min(12, round(median(differences)) if differences else 4))
        return header_row, [
            (
                aliases,
                col,
                starts[index + 1] if index + 1 < len(starts) else col + band_width,
            )
            for index, (col, aliases) in enumerate(headers)
        ]

    @staticmethod
    def _month_columns(sheet: SheetGrid, header_row: int) -> dict[int, int]:
        result: dict[int, int] = {}
        for row in range(max(0, header_row - 2), min(sheet.rows, header_row + 2)):
            for col, value in enumerate(sheet.values[row]):
                month = _MONTHS.get(value.strip().upper())
                if month is not None:
                    result[col] = month
        return result

    @staticmethod
    def _lesson_column(sheet: SheetGrid) -> int | None:
        columns: Counter[int] = Counter()
        for row in sheet.values:
            for col, value in enumerate(row):
                if _PAIR_RE.fullmatch(value):
                    columns[col] += 1
        return columns.most_common(1)[0][0] if columns else None

    @staticmethod
    def _calendar_dates(
        sheet: SheetGrid,
        day_start: int,
        day_end: int,
        weekday: int,
        month_columns: dict[int, int],
        year_start: int,
        year_end: int,
        semester_start: date,
        semester_end: date,
    ) -> tuple[date, ...]:
        result: set[date] = set()
        for col, month in month_columns.items():
            year = year_start if month >= 8 else year_end
            for row in range(day_start, day_end):
                value = sheet.value(row, col)
                if not _DAY_NUMBER_RE.fullmatch(value):
                    continue
                try:
                    candidate = date(year, month, int(value))
                except ValueError:
                    continue
                if candidate.weekday() == weekday and semester_start <= candidate <= semester_end:
                    result.add(candidate)
        return tuple(sorted(result))

    @staticmethod
    def _card_border_end(
        sheet: SheetGrid,
        subject: CellRegion,
        col_start: int,
        col_end: int,
        limit: int,
    ) -> int:
        for row in range(max(subject.row_start, subject.row_end - 1), limit):
            left = max(
                sheet.style(row, col_start).border.bottom,
                sheet.style(row + 1, col_start).border.top,
            )
            right = max(
                sheet.style(row, col_end - 1).border.bottom,
                sheet.style(row + 1, col_end - 1).border.top,
            )
            if left and right:
                return row + 1
        return limit

    @staticmethod
    def _detail_columns(subject: CellRegion, col_start: int, col_end: int) -> tuple[int, int]:
        if subject.col_start < col_start or subject.col_end > col_end:
            return subject.col_start, subject.col_end
        return col_start, col_end
