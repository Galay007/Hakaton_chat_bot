import logging
import os

from .bot_handler import BotHandler
from .config import load_settings


def configure_logging() -> None:
    logging.basicConfig(
        level=os.getenv("LOG_LEVEL", "INFO"),
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )


def main() -> None:
    configure_logging()
    settings = load_settings()
    bot = BotHandler(settings)
    bot.run()


if __name__ == "__main__":
    main()
