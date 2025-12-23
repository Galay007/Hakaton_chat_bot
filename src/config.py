import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    token: str
    min_inline_response: int = 50
    timezone: str = "UTC"


def load_settings() -> Settings:
    token = os.getenv("BOT_TOKEN")
    if not token:
        raise RuntimeError("BOT_TOKEN environment variable must be provided")

    min_inline_response = int(os.getenv("INLINE_THRESHOLD", "50"))

    return Settings(
        token=token,
        min_inline_response=min_inline_response,
        timezone=os.getenv("BOT_TZ", "UTC"),
    )
