"""Render side-by-side Excel and Telegram output checks for every FEVT group."""

from __future__ import annotations

import html
import re
import textwrap
from dataclasses import dataclass
from datetime import date
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont
from render_schedule_region import _parse_range, render

from vstu_schedule_bot.bot.formatters import format_day
from vstu_schedule_bot.parsing.factory import create_parser_registry
from vstu_schedule_bot.parsing.readers import WorkbookReaderRegistry


@dataclass(frozen=True, slots=True)
class AuditCase:
    group: str
    target: date
    cell_range: str


CASES = (
    AuditCase("ЭВМ-1.2", date(2026, 9, 16), "G46:J63"),
    AuditCase("ЭВМ-1.3", date(2026, 9, 22), "K137:N154"),
    AuditCase("САПР-1.1", date(2026, 9, 21), "O119:R136"),
    AuditCase("САПР-1.4", date(2026, 9, 29), "S28:V45"),
    AuditCase("САПР-1.3", date(2026, 9, 11), "W191:Z208"),
    AuditCase("ПОАС-1.1", date(2026, 9, 24), "AA173:AD190"),
    AuditCase("ПОАС-1.2", date(2026, 9, 10), "AE173:AH190"),
    AuditCase("Ф-1", date(2026, 9, 9), "AI155:AL172"),
    AuditCase("ЭТ-1", date(2026, 9, 9), "AM155:AP172"),
)


def _font(size: int, *, bold: bool = False) -> ImageFont.FreeTypeFont:
    name = "arialbd.ttf" if bold else "arial.ttf"
    return ImageFont.truetype(str(Path("C:/Windows/Fonts") / name), size=size)


def _plain_message(value: str) -> str:
    return re.sub(r"</?(?:b|code|i)>", "", html.unescape(value))


def _draw_message(image: Image.Image, value: str, top: int) -> None:
    draw = ImageDraw.Draw(image)
    bubble = (285, top + 36, 870, top + 640)
    draw.rounded_rectangle(bubble, radius=22, fill="#FFFFFF")
    draw.text((305, top + 52), "Сообщение пользователю", font=_font(18, bold=True), fill="#167A8B")
    lines: list[str] = []
    for line in _plain_message(value).splitlines():
        lines.extend(textwrap.wrap(line, width=54, break_long_words=False) or [""])
    y = top + 88
    for line in lines:
        draw.text((305, y), line, font=_font(16), fill="#17212B")
        y += 23


def main() -> None:
    output_dir = Path(".research/final_visual_audit")
    output_dir.mkdir(parents=True, exist_ok=True)
    workbook = WorkbookReaderRegistry().read(Path(".research/fevt1.xls"))
    sheet = workbook.sheets[0]
    schedule = create_parser_registry().parse(workbook, "ФЭВТ")

    for page_index in range(3):
        page = Image.new("RGB", (900, 2100), "#D9E7EB")
        draw = ImageDraw.Draw(page)
        for row_index, case in enumerate(CASES[page_index * 3 : page_index * 3 + 3]):
            top = row_index * 700
            raw_path = output_dir / f"{case.group}.png"
            render(sheet, _parse_range(case.cell_range), raw_path, header_row=9)
            raw = Image.open(raw_path)
            page.paste(raw, (25, top + 36))
            draw.text((25, top + 8), "Исходный Excel", font=_font(18, bold=True), fill="#17212B")
            lessons = sorted(
                (
                    lesson
                    for lesson in schedule.lessons
                    if lesson.group == case.group
                    and lesson.occurs_on(
                        case.target,
                        schedule.semester_start,
                        schedule.semester_end,
                    )
                ),
                key=lambda lesson: lesson.slot_start,
            )
            message = format_day(
                case.group,
                case.target,
                [(case.target, lesson) for lesson in lessons],
            )
            _draw_message(page, message, top)
        page.save(output_dir / f"comparison-{page_index + 1}.png")


if __name__ == "__main__":
    main()
