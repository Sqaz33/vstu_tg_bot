from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

from vstu_schedule_bot.domain.models import ParsedSchedule


@dataclass(frozen=True, slots=True)
class CellBorder:
    top: int = 0
    bottom: int = 0
    left: int = 0
    right: int = 0


@dataclass(frozen=True, slots=True)
class CellStyle:
    border: CellBorder = CellBorder()
    font_color: str = "#000000"
    fill_color: str = "#FFFFFF"
    bold: bool = False


DEFAULT_CELL_STYLE = CellStyle()


@dataclass(frozen=True, slots=True)
class CellRegion:
    row_start: int
    row_end: int
    col_start: int
    col_end: int
    value: str

    @property
    def height(self) -> int:
        return self.row_end - self.row_start

    @property
    def width(self) -> int:
        return self.col_end - self.col_start

    def intersects(self, row_start: int, row_end: int, col_start: int, col_end: int) -> bool:
        return (
            self.row_start < row_end
            and self.row_end > row_start
            and self.col_start < col_end
            and self.col_end > col_start
        )


@dataclass(frozen=True, slots=True)
class SheetGrid:
    name: str
    rows: int
    cols: int
    values: tuple[tuple[str, ...], ...]
    regions: tuple[CellRegion, ...]
    styles: tuple[tuple[CellStyle, ...], ...] = ()

    def value(self, row: int, col: int) -> str:
        if row < 0 or col < 0 or row >= self.rows or col >= self.cols:
            return ""
        return self.values[row][col]

    def style(self, row: int, col: int) -> CellStyle:
        if row < 0 or col < 0 or row >= len(self.styles):
            return DEFAULT_CELL_STYLE
        style_row = self.styles[row]
        if col >= len(style_row):
            return DEFAULT_CELL_STYLE
        return style_row[col]


@dataclass(frozen=True, slots=True)
class WorkbookGrid:
    filename: str
    sheets: tuple[SheetGrid, ...]


class WorkbookReader(Protocol):
    def supports(self, suffix: str) -> bool: ...

    def read(self, path: Path) -> WorkbookGrid: ...


class ScheduleParser(ABC):
    name: str

    @abstractmethod
    def score(self, workbook: WorkbookGrid) -> int:
        """Return a positive confidence score when this parser supports the workbook."""

    @abstractmethod
    def parse(self, workbook: WorkbookGrid, faculty: str) -> ParsedSchedule:
        """Parse a workbook into normalized lessons."""


class ParserNotFoundError(ValueError):
    pass


class ParserRegistry:
    def __init__(self, parsers: list[ScheduleParser] | None = None) -> None:
        self._parsers = parsers or []

    def register(self, parser: ScheduleParser) -> None:
        self._parsers.append(parser)

    def select(self, workbook: WorkbookGrid) -> ScheduleParser:
        ranked = sorted(
            ((parser.score(workbook), parser) for parser in self._parsers),
            key=lambda item: item[0],
            reverse=True,
        )
        if not ranked or ranked[0][0] <= 0:
            raise ParserNotFoundError(f"No parser supports {workbook.filename}")
        return ranked[0][1]

    def parse(self, workbook: WorkbookGrid, faculty: str) -> ParsedSchedule:
        return self.select(workbook).parse(workbook, faculty)
