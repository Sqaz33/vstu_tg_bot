from __future__ import annotations

from vstu_schedule_bot.parsing.base import ParserRegistry
from vstu_schedule_bot.parsing.fevt_master import FevtMasterGridParser
from vstu_schedule_bot.parsing.vstu_grid import VstuGridParser

PARSER_CACHE_VERSION = "formatted-cards-v2"


def create_parser_registry() -> ParserRegistry:
    registry = ParserRegistry()
    registry.register(FevtMasterGridParser())
    registry.register(VstuGridParser())
    return registry
