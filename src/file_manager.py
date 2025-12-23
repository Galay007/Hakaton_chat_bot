from __future__ import annotations

from typing import Optional

from telegram import Bot, Document


class FileManager:
    """Handles file download and validation with in-memory buffers."""

    ALLOWED_SUFFIXES = ".json"

    @staticmethod
    def is_supported(document: Document) -> bool:
        if not document.file_name:
            return False
        return document.file_name.lower().endswith(FileManager.ALLOWED_SUFFIXES)

    async def fetch_file_bytes(self, bot: Bot, file_id: str) -> bytes:
        telegram_file = await bot.get_file(file_id)
        payload = await telegram_file.download_as_bytearray()
        return bytes(payload)
