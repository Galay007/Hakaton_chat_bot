import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    token: str
    max_size: int = 10485760 #значение в байтах по умолчанию, если не задан в среде переменных
    min_inline_response: int = 50 #значение по умолчанию, если не задан в среде переменных
    timezone: str = "UTC"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable must be provided")

    max_size = int(os.getenv("MAX_SIZE", int(Settings.max_size)))
    min_inline_response = int(os.getenv("INLINE_THRESHOLD", int(Settings.min_inline_response)))

    return Settings(
        token=token,
        max_size=max_size,
        min_inline_response=min_inline_response,
        timezone=os.getenv("BOT_TZ", "UTC"),
    )
