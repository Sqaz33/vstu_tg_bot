from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from zoneinfo import ZoneInfo

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    bot_token: SecretStr
    database_path: Path = Path("data/schedule.db")
    source_page_url: str = "https://www.vstu.ru/student/raspisaniya/zanyatiy/index.php?dep=mag"
    source_file_pattern: str = "1 курс ФЭВТ.xls"
    faculty_name: str = "ФЭВТ"
    update_interval_seconds: int = Field(default=300, ge=60)
    request_timeout_seconds: int = Field(default=30, ge=5, le=120)
    timezone: str = "Europe/Moscow"
    log_level: str = "INFO"
    log_format: str = "json"
    health_host: str = "0.0.0.0"
    health_port: int = Field(default=8080, ge=1, le=65535)

    @field_validator("bot_token")
    @classmethod
    def validate_token(cls, value: SecretStr) -> SecretStr:
        token = value.get_secret_value().strip()
        if not token or ":" not in token:
            raise ValueError("BOT_TOKEN must be a Telegram bot token from BotFather")
        return SecretStr(token)

    @field_validator("log_level")
    @classmethod
    def normalize_log_level(cls, value: str) -> str:
        return value.upper()

    @property
    def tz(self) -> ZoneInfo:
        return ZoneInfo(self.timezone)

    def prepare_directories(self) -> None:
        self.database_path.parent.mkdir(parents=True, exist_ok=True)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()  # type: ignore[call-arg]
