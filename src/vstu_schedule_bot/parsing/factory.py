from __future__ import annotations

from vstu_schedule_bot.parsing.base import ParserRegistry
from vstu_schedule_bot.parsing.vstu_grid import VstuGridParser


def create_parser_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(VstuGridParser())
    return registry
