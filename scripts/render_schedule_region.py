"""Render an XLS/XLSX range with merged cells and borders for parser diagnostics."""

from __future__ import annotations

import argparse
import re
import textwrap
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from vstu_schedule_bot.parsing.base import CellRegion, SheetGrid
from vstu_schedule_bot.parsing.readers import WorkbookReaderRegistry

_RANGE_RE = re.compile(r"^([A-Z]+)(\d+):([A-Z]+)(\d+)$", re.IGNORECASE)


def _column(value: str) -> int:
    result = 0
    for char in value.upper():
        result = result * 26 + ord(char) - ord("A") + 1
    return result - 1


def _parse_range(value: str) -> tuple[int, int, int, int]:
    match = _RANGE_RE.fullmatch(value)
    if not match:
        raise argparse.ArgumentTypeError("Range must look like AA173:AH190")
    c0, r0, c1, r1 = match.groups()
    return int(r0) - 1, int(r1), _column(c0), _column(c1) + 1


def _font(size: int, bold: bool = False) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        Path("C:/Windows/Fonts/arialbd.ttf" if bold else "C:/Windows/Fonts/arial.ttf"),
        Path(
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"
            if bold
            else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"
        ),
    ]
    for candidate in candidates:
        if candidate.exists():
            return ImageFont.truetype(str(candidate), size=size)
    return ImageFont.load_default()


def _line_width(style: int) -> int:
    if style >= 5:
        return 4
    if style >= 2:
        return 3
    return 1 if style else 0


def _text_box(
    draw: ImageDraw.ImageDraw,
    value: str,
    box: tuple[int, int, int, int],
    *,
    color: str,
    bold: bool,
) -> None:
    left, top, right, bottom = box
    width = right - left
    font = _font(14 if bold else 12, bold=bold)
    lines = textwrap.wrap(value, width=max(5, width // 8)) or [value]
    text = "\n".join(lines[:5])
    text_box = draw.multiline_textbbox((0, 0), text, font=font, align="center", spacing=2)
    text_width = text_box[2] - text_box[0]
    text_height = text_box[3] - text_box[1]
    draw.multiline_text(
        (left + (width - text_width) / 2, top + (bottom - top - text_height) / 2),
        text,
        fill=color,
        font=font,
        align="center",
        spacing=2,
    )


def render(
    sheet: SheetGrid,
    cell_range: tuple[int, int, int, int],
    output: Path,
    *,
    header_row: int | None = None,
) -> None:
    row_start, row_end, col_start, col_end = cell_range
    rows = list(range(row_start, row_end))
    if header_row is not None and header_row - 1 not in rows:
        rows.insert(0, header_row - 1)
    row_map = {source: visual for visual, source in enumerate(rows)}
    cell_width, cell_height = 58, 34
    width = (col_end - col_start) * cell_width + 1
    height = len(rows) * cell_height + 1
    image = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(image)

    merged_cover: set[tuple[int, int]] = set()
    visible_merges: list[CellRegion] = []
    for region in sheet.regions:
        if region.width == 1 and region.height == 1:
            continue
        if (
            region.row_start in row_map
            and region.row_end - 1 in row_map
            and region.col_start < col_end
            and region.col_end > col_start
        ):
            visible_merges.append(region)
            for row in range(region.row_start, region.row_end):
                for col in range(region.col_start, region.col_end):
                    merged_cover.add((row, col))

    for row in rows:
        y = row_map[row] * cell_height
        for col in range(col_start, col_end):
            x = (col - col_start) * cell_width
            style = sheet.style(row, col)
            draw.rectangle((x, y, x + cell_width, y + cell_height), fill=style.fill_color)
            draw.rectangle((x, y, x + cell_width, y + cell_height), outline="#D9D9D9")

    for region in visible_merges:
        left = max(region.col_start, col_start)
        right = min(region.col_end, col_end)
        top = row_map[region.row_start]
        bottom = row_map[region.row_end - 1] + 1
        box = (
            (left - col_start) * cell_width,
            top * cell_height,
            (right - col_start) * cell_width,
            bottom * cell_height,
        )
        style = sheet.style(region.row_start, region.col_start)
        draw.rectangle(box, fill=style.fill_color, outline="#D9D9D9")
        if region.value:
            _text_box(
                draw,
                region.value,
                box,
                color=style.font_color,
                bold=style.bold,
            )

    for row in rows:
        y = row_map[row] * cell_height
        for col in range(col_start, col_end):
            x = (col - col_start) * cell_width
            style = sheet.style(row, col)
            border = style.border
            for coords, border_style in (
                ((x, y, x + cell_width, y), border.top),
                ((x, y + cell_height, x + cell_width, y + cell_height), border.bottom),
                ((x, y, x, y + cell_height), border.left),
                ((x + cell_width, y, x + cell_width, y + cell_height), border.right),
            ):
                line_width = _line_width(border_style)
                if line_width:
                    draw.line(coords, fill="black", width=line_width)
            value = sheet.value(row, col)
            if value and (row, col) not in merged_cover:
                _text_box(
                    draw,
                    value,
                    (x, y, x + cell_width, y + cell_height),
                    color=style.font_color,
                    bold=style.bold,
                )

    output.parent.mkdir(parents=True, exist_ok=True)
    image.save(output)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("workbook", type=Path)
    parser.add_argument("cell_range", type=_parse_range)
    parser.add_argument("output", type=Path)
    parser.add_argument("--header-row", type=int)
    args = parser.parse_args()
    workbook = WorkbookReaderRegistry().read(args.workbook)
    render(workbook.sheets[0], args.cell_range, args.output, header_row=args.header_row)


if __name__ == "__main__":
    main()
