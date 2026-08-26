from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from vstu_schedule_bot.domain.models import DateRule
from vstu_schedule_bot.parsing.base import CellRegion, SheetGrid, WorkbookGrid
from vstu_schedule_bot.parsing.readers import WorkbookReaderRegistry
from vstu_schedule_bot.parsing.vstu_grid import VstuGridParser, extract_groups


def _grid() -> WorkbookGrid:
    rows, cols = 14, 15
    values = [["" for _ in range(cols)] for _ in range(rows)]
    values[0][0] = "Учебные занятия на I семестр 2026-2027 учебного года"
    values[1][6] = "ЭВМ - 1.2"
    values[1][10] = "ЭКОМ-1, ЭКОМ-1в"
    values[2][4] = "ПОНЕДЕЛЬНИК"
    values[2][5] = "1-2"
    values[5][5] = "3-4"
    values[8][5] = "5-6"
    values[11][4] = "ВТОРНИК"
    values[11][5] = "1-2"
    regions = (
        CellRegion(0, 1, 0, 10, values[0][0]),
        CellRegion(1, 2, 6, 10, values[1][6]),
        CellRegion(1, 2, 10, 14, values[1][10]),
        CellRegion(2, 11, 4, 5, values[2][4]),
        CellRegion(2, 3, 5, 6, values[2][5]),
        CellRegion(5, 6, 5, 6, values[5][5]),
        CellRegion(8, 9, 5, 6, values[8][5]),
        CellRegion(11, 14, 4, 5, values[11][4]),
        CellRegion(11, 12, 5, 6, values[11][5]),
        CellRegion(2, 6, 6, 10, "ТЕХНОЛОГИИ ПРОГРАММИРОВАНИЯ"),
        CellRegion(6, 7, 6, 8, "14.09, 12.10"),
        CellRegion(7, 8, 6, 9, "доц. Иванов И.И."),
        CellRegion(7, 8, 9, 10, "В-903"),
        CellRegion(8, 10, 10, 14, "НАУЧНО-ИССЛЕДОВАТЕЛЬСКАЯ РАБОТА"),
    )
    return WorkbookGrid(
        filename="fixture.xls",
        sheets=(
            SheetGrid(
                name="2026-2027",
                rows=rows,
                cols=cols,
                values=tuple(tuple(row) for row in values),
                regions=regions,
            ),
        ),
    )


def test_extracts_alias_groups() -> None:
    assert extract_groups("ЭКОМ-1, ЭКОМ-1в") == ("ЭКОМ-1", "ЭКОМ-1В")


def test_semantic_grid_parser_handles_merged_multi_pair_lesson() -> None:
    parsed = VstuGridParser().parse(_grid(), "ФЭВТ")

    assert parsed.groups == ("ЭВМ-1.2", "ЭКОМ-1", "ЭКОМ-1В")
    assert parsed.semester_start == date(2026, 9, 1)
    assert parsed.semester_end == date(2026, 12, 31)
    lesson = next(item for item in parsed.lessons if item.group == "ЭВМ-1.2")
    assert lesson.pair_label == "1–4"
    assert lesson.starts_at == "08:30"
    assert lesson.ends_at == "11:40"
    assert lesson.teacher == "доц. Иванов И.И."
    assert lesson.room == "В-903"
    assert lesson.date_rule is DateRule.EXPLICIT
    assert lesson.explicit_dates == (date(2026, 9, 14), date(2026, 10, 12))


@pytest.mark.skipif(not Path(".research/fevt1.xls").exists(), reason="local research file")
def test_real_fevt_workbook_smoke() -> None:
    workbook = WorkbookReaderRegistry().read(Path(".research/fevt1.xls"))
    parsed = VstuGridParser().parse(workbook, "ФЭВТ")

    assert len(parsed.groups) == 9
    assert len(parsed.lessons) >= 100
    assert "ЭВМ-1.2" in parsed.groups
    assert any(lesson.teacher for lesson in parsed.lessons)
    assert any(lesson.explicit_dates for lesson in parsed.lessons)
