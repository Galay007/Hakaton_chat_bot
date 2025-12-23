from __future__ import annotations

import json
import re
from dataclasses import dataclass
from datetime import datetime
from typing import Dict, Iterable, List, Set, Tuple

from bs4 import BeautifulSoup

from .models import IdentityRecord, ParsedData


MENTION_PATTERN = re.compile(r"@([A-Za-z0-9_]{5,})")
CHANNEL_LINK_PATTERN = re.compile(
    r"(?:https?://)?t\.me/([A-Za-z0-9_]+)", flags=re.IGNORECASE
)
DELETED_TOKENS = ("deleted account", "удалённый", "удаленный")


class DataParser:
    """Parses Telegram export files (JSON) and extracts participants."""

    def parse(self, file_name: str, payload: bytes) -> ParsedData:
        file_name = (file_name or "").lower()
        if file_name.endswith(".json"):
            return self._parse_json(payload)
        # Fallback to auto-detection by content
        data = payload.lstrip()
        if data.startswith(b"{"):
            return self._parse_json(payload)

    # JSON parsing ---------------------------------------------------------
    def _parse_json(self, payload: bytes) -> ParsedData:
        try:
            raw = json.loads(payload.decode("utf-8"))
        except Exception as exc:  # pragma: no cover - defensive logging
            raise ValueError("Не удалось разобрать JSON-файл экспорта") from exc

        messages = raw.get("messages", [])
        exported_at = self._extract_exported_at(raw)

        authors: Dict[str, IdentityRecord] = {}
        mentions, channels = set(), set()

        for message in messages:
            if not isinstance(message, dict):
                continue
            if message.get("type") not in (None, "message", "service"):
                continue
            sender = message.get("from") or message.get("actor")
            if self._is_deleted(sender):
                continue
            identifier = self._build_identifier(
                username=self._extract_username(message),
                fallback=str(message.get("from_id") or message.get("actor_id") or ""),
                full_name=sender,
            )
            if identifier and identifier not in authors:
                authors[identifier] = IdentityRecord(
                    identifier=identifier,
                    username=self._extract_username(message),
                    full_name=sender,
                    registered_at=self._safe_iso_date(message.get("date")),
                )
            elif identifier:
                record = authors[identifier]
                msg_date = self._safe_iso_date(message.get("date"))
                if msg_date and (
                    not record.registered_at or msg_date < record.registered_at
                ):
                    record.registered_at = msg_date

            text_content = self._stringify_text(message)
            msg_mentions, msg_channels = self._extract_mentions(text_content)
            mentions.update(msg_mentions)
            channels.update(msg_channels)

            for entity in self._extract_entities(message):
                if entity.startswith("@"):
                    mentions.add(entity)
                else:
                    channels.add(entity)

        return ParsedData(
            exported_at=exported_at,
            participants=list(authors.values()),
            mentions=self._records_from_handles(mentions),
            channels=self._records_from_handles(channels, assume_channel=True),
        )

    # Helpers ---------------------------------------------------------------
    @staticmethod
    def _stringify_text(message: Dict) -> str:
        text = message.get("text")
        if isinstance(text, str):
            return text
        if isinstance(text, list):
            fragments: List[str] = []
            for chunk in text:
                if isinstance(chunk, str):
                    fragments.append(chunk)
                elif isinstance(chunk, dict):
                    fragments.append(chunk.get("text", ""))
            return " ".join(fragments)
        return ""

    @staticmethod
    def _extract_entities(message: Dict) -> Iterable[str]:
        entities = message.get("text_entities") or message.get("entities") or []
        for entity in entities:
            text = entity.get("text") or ""
            if text.startswith("@"):
                yield text
                continue
            url = entity.get("href") or entity.get("url")
            handle = DataParser._handle_from_href(url)
            if handle:
                yield handle

    @staticmethod
    def _extract_username(message: Dict) -> str | None:
        username = message.get("from_username") or message.get("username")
        return DataParser._normalize_username(username)

    @staticmethod
    def _extract_username_attr(message) -> str | None:
        username = message.get("data-username")
        return DataParser._normalize_username(username)

    @staticmethod
    def _normalize_username(value: str | None) -> str | None:
        if not value:
            return None
        value = value.strip()
        if not value:
            return None
        if not value.startswith("@"):
            value = f"@{value}"
        return value

    @staticmethod
    def _extract_mentions(text: str) -> Tuple[Set[str], Set[str]]:
        mentions = {f"@{match.lower()}" for match in MENTION_PATTERN.findall(text)}
        channels = {
            f"t.me/{match.lower()}" for match in CHANNEL_LINK_PATTERN.findall(text)
        }
        return mentions, channels

    @staticmethod
    def _handle_from_href(href: str | None) -> str | None:
        if not href:
            return None
        if href.startswith("@"):
            return href
        match = CHANNEL_LINK_PATTERN.search(href)
        if match:
            return f"t.me/{match.group(1).lower()}"
        return None

    @staticmethod
    def _extract_html_date(message) -> str | None:
        date_node = message.select_one(".date")
        if not date_node:
            return None
        raw = date_node.get("title") or date_node.get_text(strip=True)
        return DataParser._safe_iso_date(raw)

    @staticmethod
    def _safe_iso_date(raw: str | None) -> str | None:
        if not raw:
            return None
        raw = raw.strip()
        if not raw:
            return None
        try:
            parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        except ValueError:
            # Accept formats like "03.12.2024 12:05:00"
            try:
                parsed = datetime.strptime(raw, "%d.%m.%Y %H:%M:%S")
            except ValueError:
                return None
        return parsed.isoformat()

    @staticmethod
    def _extract_exported_at(raw: Dict) -> datetime:
        date_value = (
            raw.get("date")
            or raw.get("exported_at")
            or raw.get("date_range", {}).get("to")
        )
        parsed = DataParser._safe_iso_date(date_value)
        if parsed:
            return datetime.fromisoformat(parsed)
        return datetime.utcnow()

    @staticmethod
    def _is_deleted(name: str | None) -> bool:
        if not name:
            return False
        lowered = name.lower()
        return any(token in lowered for token in DELETED_TOKENS)

    @staticmethod
    def _build_identifier(
        username: str | None, fallback: str | None, full_name: str | None
    ) -> str:
        if username:
            return username.lower()
        if fallback:
            full = (full_name or "").lower()
            return f"{fallback}:{full}"
        return (full_name or "unknown").lower()

    @staticmethod
    def _records_from_handles(
        handles: Iterable[str], assume_channel: bool = False
    ) -> List[IdentityRecord]:
        records = []
        for handle in sorted(handles):
            username = handle if handle.startswith("@") else handle
            identifier = handle.lower()
            records.append(
                IdentityRecord(
                    identifier=identifier,
                    username=username if username.startswith("@") else None,
                    full_name=None if username.startswith("@") else username,
                    has_channel=True if assume_channel else None,
                )
            )
        return records
