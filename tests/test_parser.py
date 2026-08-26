from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from vstu_schedule_bot.domain.models import DateRule
from vstu_schedule_bot.parsing.base import (
    CellBorder,
    CellRegion,
    CellStyle,
    SheetGrid,
    WorkbookGrid,
)
from vstu_schedule_bot.parsing.factory import create_parser_registry
from vstu_schedule_bot.parsing.fevt_master import FevtMasterGridParser
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


def _formatted_fevt_grid() -> WorkbookGrid:
    rows, cols = 17, 14
    values = [["" for _ in range(cols)] for _ in range(rows)]
    styles = [[CellStyle() for _ in range(cols)] for _ in range(rows)]
    values[0][0] = "Учебные занятия 1 курса магистров ФЭВТ на I семестр 2026-2027"
    values[0][1] = "СЕНТЯБРЬ"
    values[1][6] = "ПОАС-1.1"
    values[1][10] = "ПОАС-1.2"
    values[2][1] = "14"
    values[2][4] = "ПОНЕДЕЛЬНИК"
    values[2][5] = "1-2"
    values[5][5] = "3-4"
    values[8][5] = "5-6"
    values[11][5] = "7-8"
    values[14][4] = "ВТОРНИК"
    values[14][5] = "1-2"

    for col in (10, 13):
        styles[7][col] = CellStyle(border=CellBorder(bottom=1))
    for col in (6, 9, 10, 13):
        styles[13][col] = CellStyle(border=CellBorder(bottom=1))

    regions = (
        CellRegion(0, 1, 0, 14, values[0][0]),
        CellRegion(0, 1, 1, 2, values[0][1]),
        CellRegion(1, 2, 6, 10, values[1][6]),
        CellRegion(1, 2, 10, 14, values[1][10]),
        CellRegion(2, 14, 4, 5, values[2][4]),
        CellRegion(2, 3, 5, 6, values[2][5]),
        CellRegion(5, 6, 5, 6, values[5][5]),
        CellRegion(8, 9, 5, 6, values[8][5]),
        CellRegion(11, 12, 5, 6, values[11][5]),
        CellRegion(14, 17, 4, 5, values[14][4]),
        CellRegion(14, 15, 5, 6, values[14][5]),
        CellRegion(2, 4, 10, 14, "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"),
        CellRegion(4, 5, 10, 14, "07.09"),
        CellRegion(6, 7, 10, 13, "Гилка В.В."),
        CellRegion(6, 7, 13, 14, "В-908"),
        CellRegion(8, 10, 6, 14, "РЕЛЯЦИОННЫЕ СИСТЕМЫ БАЗ ДАННЫХ"),
        CellRegion(10, 11, 6, 14, "14.09"),
        CellRegion(12, 13, 6, 13, "Аникин А.В."),
        CellRegion(12, 13, 13, 14, "В-903"),
    )
    return WorkbookGrid(
        filename="fevt-master.xls",
        sheets=(
            SheetGrid(
                name="2026-2027",
                rows=rows,
                cols=cols,
                values=tuple(tuple(row) for row in values),
                regions=regions,
                styles=tuple(tuple(row) for row in styles),
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


def test_fevt_parser_uses_card_borders_group_span_and_date_override() -> None:
    workbook = _formatted_fevt_grid()
    registry = create_parser_registry()

    assert isinstance(registry.select(workbook), FevtMasterGridParser)
    parsed = registry.parse(workbook, "ФЭВТ")

    upper = [lesson for lesson in parsed.lessons if "АНАЛИЗ" in lesson.subject]
    assert [(lesson.group, lesson.pair_label) for lesson in upper] == [("ПОАС-1.2", "1–4")]
    assert upper[0].explicit_dates == (date(2026, 9, 7),)
    assert date(2026, 9, 14) not in upper[0].explicit_dates

    shared = [lesson for lesson in parsed.lessons if "РЕЛЯЦИОННЫЕ" in lesson.subject]
    assert [(lesson.group, lesson.pair_label) for lesson in shared] == [
        ("ПОАС-1.1", "5–8"),
        ("ПОАС-1.2", "5–8"),
    ]
    assert all(lesson.explicit_dates == (date(2026, 9, 14),) for lesson in shared)


@pytest.mark.skipif(not Path(".research/fevt1.xls").exists(), reason="local research file")
def test_real_fevt_workbook_smoke() -> None:
    workbook = WorkbookReaderRegistry().read(Path(".research/fevt1.xls"))
    registry = create_parser_registry()
    parser = registry.select(workbook)
    parsed = parser.parse(workbook, "ФЭВТ")

    assert isinstance(parser, FevtMasterGridParser)
    assert len(parsed.groups) == 9
    assert len(parsed.lessons) >= 100
    assert "ЭВМ-1.2" in parsed.groups
    assert any(lesson.teacher for lesson in parsed.lessons)
    assert any(lesson.explicit_dates for lesson in parsed.lessons)
    # The visual border below the POAS-1.2 card is part of its semantics.
    assert workbook.sheets[0].style(183, 30).border.bottom > 0  # AE184
    assert workbook.sheets[0].style(183, 33).border.bottom > 0  # AH184

    poas_12 = [lesson for lesson in parsed.lessons if lesson.group == "ПОАС-1.2"]
    september_10 = [lesson for lesson in poas_12 if date(2026, 9, 10) in lesson.explicit_dates]
    assert [(lesson.pair_label, lesson.subject) for lesson in september_10] == [
        ("5–8", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ")
    ]
    september_24 = [lesson for lesson in poas_12 if date(2026, 9, 24) in lesson.explicit_dates]
    assert [(lesson.pair_label, lesson.subject) for lesson in september_24] == [
        ("9–12", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ")
    ]
    poas_11_shared = [
        lesson
        for lesson in parsed.lessons
        if lesson.group == "ПОАС-1.1" and date(2026, 9, 24) in lesson.explicit_dates
    ]
    assert [(lesson.pair_label, lesson.subject) for lesson in poas_11_shared] == [
        ("9–12", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ")
    ]
    september_12 = [lesson for lesson in poas_12 if date(2026, 9, 12) in lesson.explicit_dates]
    assert [(lesson.pair_label, lesson.subject) for lesson in september_12] == [
        ("1–4", "РАЗРАБОТКА ABAP-ПРИЛОЖЕНИЙ В СРЕДЕ SAP")
    ]
