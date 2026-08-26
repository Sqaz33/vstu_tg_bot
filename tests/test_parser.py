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
    rows, cols = 45, 14
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
    values[20][4] = "ВТОРНИК"
    values[20][5] = "1-2"
    values[40][10] = "НАЧАЛЬНИК УЧЕБНОГО ОТДЕЛА"

    for col in (10, 13):
        styles[8][col] = CellStyle(border=CellBorder(top=1))
    for col in (6, 9, 10, 13):
        styles[13][col] = CellStyle(border=CellBorder(bottom=1))

    regions = (
        CellRegion(0, 1, 0, 14, values[0][0]),
        CellRegion(0, 1, 1, 2, values[0][1]),
        CellRegion(1, 2, 6, 10, values[1][6]),
        CellRegion(1, 2, 10, 14, values[1][10]),
        CellRegion(2, 20, 4, 5, values[2][4]),
        CellRegion(2, 3, 5, 6, values[2][5]),
        CellRegion(5, 6, 5, 6, values[5][5]),
        CellRegion(8, 9, 5, 6, values[8][5]),
        CellRegion(11, 12, 5, 6, values[11][5]),
        CellRegion(20, 38, 4, 5, values[20][4]),
        CellRegion(20, 21, 5, 6, values[20][5]),
        CellRegion(2, 4, 10, 14, "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"),
        CellRegion(4, 5, 10, 14, "07.09"),
        CellRegion(6, 7, 10, 13, "Гилка В.В."),
        CellRegion(6, 7, 13, 14, "В-908"),
        CellRegion(8, 10, 6, 14, "РЕЛЯЦИОННЫЕ СИСТЕМЫ БАЗ ДАННЫХ"),
        CellRegion(10, 11, 6, 14, "14.09"),
        CellRegion(12, 13, 6, 13, "Аникин А.В."),
        CellRegion(12, 13, 13, 14, "В-903"),
        CellRegion(40, 42, 10, 14, values[40][10]),
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
    assert all("НАЧАЛЬНИК" not in lesson.subject for lesson in parsed.lessons)


def test_compact_date_typo_is_read_only_inside_a_date_list() -> None:
    parser = VstuGridParser()

    assert parser._dates("16.09, 1410, 11.11", 2026, 2027) == [
        date(2026, 9, 16),
        date(2026, 11, 11),
        date(2026, 10, 14),
    ]
    assert parser._dates("В-1303", 2026, 2027) == []


@pytest.mark.skipif(not Path(".research/fevt1.xls").exists(), reason="local research file")
def test_real_fevt_workbook_smoke() -> None:
    workbook = WorkbookReaderRegistry().read(Path(".research/fevt1.xls"))
    registry = create_parser_registry()
    parser = registry.select(workbook)
    parsed = parser.parse(workbook, "ФЭВТ")

    assert isinstance(parser, FevtMasterGridParser)
    assert len(parsed.groups) == 9
    assert len(parsed.lessons) == 116
    assert "ЭВМ-1.2" in parsed.groups
    assert any(lesson.teacher for lesson in parsed.lessons)
    assert any(lesson.explicit_dates for lesson in parsed.lessons)
    # The visual border below the POAS-1.2 card is part of its semantics.
    assert workbook.sheets[0].style(183, 30).border.bottom > 0  # AE184
    assert workbook.sheets[0].style(183, 33).border.bottom > 0  # AH184

    poas_visual_golden = {
        (lesson.group, lesson.weekday, lesson.pair_label, lesson.subject): ",".join(
            value.strftime("%d.%m") for value in lesson.explicit_dates
        )
        for lesson in parsed.lessons
        if lesson.group in {"ПОАС-1.1", "ПОАС-1.2"}
    }
    assert poas_visual_golden == {
        (
            "ПОАС-1.1",
            0,
            "5–8",
            "РЕЛЯЦИОННЫЕ И НЕРЕЛЯЦИОННЫЕ СИСТЕМЫ БАЗ ДАННЫХ",
        ): "14.09,12.10,09.11,07.12",  # noqa: E501
        ("ПОАС-1.1", 1, "1–4", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"): "15.09,13.10,10.11,08.12",
        (
            "ПОАС-1.1",
            1,
            "5–8",
            "ПРОФ. ИН-ЯЗ КОММУНИКАЦИЯ",
        ): "01.09,15.09,29.09,13.10,27.10,10.11,24.11,08.12,22.12",  # noqa: E501
        (
            "ПОАС-1.1",
            2,
            "1–4",
            "ПРОИЗВОДСТВЕННАЯ : НАУЧНО-ИССЛЕД. РАБОТА",
        ): "30.09,28.10,25.11,23.12",  # noqa: E501
        (
            "ПОАС-1.1",
            2,
            "1–4",
            "РЕЛЯЦИОННЫЕ И НЕРЕЛЯЦИОННЫЕ СИСТЕМЫ БАЗ ДАННЫХ",
        ): "09.09,23.09,07.10,21.10,04.11,18.11,02.12,16.12",  # noqa: E501
        (
            "ПОАС-1.1",
            3,
            "3–6",
            "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ",
        ): "03.09,17.09,15.10,29.10,12.11,26.11,10.12,24.12",  # noqa: E501
        ("ПОАС-1.1", 3, "9–12", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"): "24.09,22.10,19.11,17.12",
        ("ПОАС-1.1", 4, "1–4", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"): "25.09,23.10,20.11,18.12",
        (
            "ПОАС-1.1",
            4,
            "9–12",
            "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ",
        ): "04.09,18.09,02.10,16.10,30.10,13.11,27.11,11.12,25.12",  # noqa: E501
        ("ПОАС-1.1", 5, "1–4", "РАЗРАБОТКА ABAP-ПРИЛОЖЕНИЙ В СРЕДЕ SAP"): "26.09,24.10,21.11,19.12",
        ("ПОАС-1.1", 5, "5–8", "РАЗРАБОТКА ABAP-ПРИЛОЖЕНИЙ В СРЕДЕ SAP"): "26.09,24.10,21.11,19.12",
        (
            "ПОАС-1.2",
            0,
            "3–6",
            "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ",
        ): "07.09,21.09,05.10,19.10,02.11,16.11,30.11,14.12,28.12",  # noqa: E501
        (
            "ПОАС-1.2",
            0,
            "5–8",
            "РЕЛЯЦИОННЫЕ И НЕРЕЛЯЦИОННЫЕ СИСТЕМЫ БАЗ ДАННЫХ",
        ): "14.09,12.10,09.11,07.12",  # noqa: E501
        ("ПОАС-1.2", 1, "1–4", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"): "29.09,27.10,24.11,22.12",
        (
            "ПОАС-1.2",
            2,
            "1–4",
            "ПРОИЗВОДСТВЕННАЯ : НАУЧНО-ИССЛЕД. РАБОТА",
        ): "16.09,14.10,11.11,09.12",  # noqa: E501
        ("ПОАС-1.2", 3, "5–8", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"): "10.09,08.10,05.11,03.12",
        ("ПОАС-1.2", 3, "9–12", "АНАЛИЗ И ВИЗУАЛИЗАЦИЯ ДАННЫХ"): "24.09,22.10,19.11,17.12",
        (
            "ПОАС-1.2",
            4,
            "5–8",
            "РЕЛЯЦИОННЫЕ И НЕРЕЛЯЦИОННЫЕ СИСТЕМЫ БАЗ ДАННЫХ",
        ): "04.09,18.09,02.10,16.10,30.10,13.11,27.11,11.12,25.12",  # noqa: E501
        (
            "ПОАС-1.2",
            4,
            "9–12",
            "ПРОФ. ИН-ЯЗ КОММУНИКАЦИЯ",
        ): "11.09,25.09,09.10,23.10,06.11,20.11,04.12,18.12",  # noqa: E501
        ("ПОАС-1.2", 5, "1–4", "РАЗРАБОТКА ABAP-ПРИЛОЖЕНИЙ В СРЕДЕ SAP"): "12.09,10.10,07.11,05.12",
        ("ПОАС-1.2", 5, "5–8", "РАЗРАБОТКА ABAP-ПРИЛОЖЕНИЙ В СРЕДЕ SAP"): "26.09,24.10,21.11,19.12",
    }

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
    assert all("НАЧАЛЬНИК УЧЕБНОГО ОТДЕЛА" not in lesson.subject for lesson in parsed.lessons)
    evm_shared = [
        lesson
        for lesson in parsed.lessons
        if lesson.group == "ЭВМ-1.2"
        and lesson.subject.startswith("ТЕХНОЛОГИИ ПРОГРАММИРОВАНИЯ")
        and lesson.weekday == 2
    ]
    assert evm_shared[0].explicit_dates == (
        date(2026, 9, 16),
        date(2026, 10, 14),
        date(2026, 11, 11),
        date(2026, 12, 9),
    )
