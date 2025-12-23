from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional


@dataclass
class IdentityRecord:
    identifier: str
    username: Optional[str] = None
    full_name: Optional[str] = None
    bio: Optional[str] = None
    registered_at: Optional[str] = None
    has_channel: Optional[bool] = None

    def to_row(self, exported_at: datetime) -> Dict[str, Optional[str]]:
        return {
            "Дата экспорта": exported_at.isoformat(),
            "Username": self.username or "",
            "Имя и фамилия": self.full_name or "",
            "Описание": self.bio or "",
            "Дата регистрации": self.registered_at or "",
            "Наличие канала": self._bool_to_text(self.has_channel),
        }

    @staticmethod
    def _bool_to_text(value: Optional[bool]) -> str:
        if value is None:
            return "Неизвестно"
        return "Да" if value else "Нет"


@dataclass
class ParsedData:
    exported_at: datetime
    participants: List[IdentityRecord] = field(default_factory=list)
    mentions: List[IdentityRecord] = field(default_factory=list)
    channels: List[IdentityRecord] = field(default_factory=list)


@dataclass
class SessionData:
    participants: Dict[str, IdentityRecord] = field(default_factory=dict)
    mentions: Dict[str, IdentityRecord] = field(default_factory=dict)
    channels: Dict[str, IdentityRecord] = field(default_factory=dict)
    files_processed: int = 0
    last_exported_at: Optional[datetime] = None
    files_received: int = 0

    def merge(self, parsed: ParsedData) -> Dict[str, int]:
        counters = {"participants": 0, "mentions": 0, "channels": 0}
        for record in parsed.participants:
            if record.identifier not in self.participants:
                self.participants[record.identifier] = record
                counters["participants"] += 1
        for record in parsed.mentions:
            if record.identifier not in self.mentions:
                self.mentions[record.identifier] = record
                counters["mentions"] += 1
        for record in parsed.channels:
            if record.identifier not in self.channels:
                self.channels[record.identifier] = record
                counters["channels"] += 1
        self.files_processed += 1
        self.last_exported_at = parsed.exported_at
        return counters

    def reset(self) -> None:
        self.participants.clear()
        self.mentions.clear()
        self.channels.clear()
        self.files_processed = 0
        self.last_exported_at = None
        self.files_received = 0

    def as_rows(
        self, exported_at: Optional[datetime] = None
    ) -> Dict[str, List[Dict[str, Optional[str]]]]:
        exported_at = exported_at or self.last_exported_at or datetime.utcnow()
        return {
            "participants": _records_to_rows(self.participants.values(), exported_at),
            "mentions": _records_to_rows(self.mentions.values(), exported_at),
            "channels": _records_to_rows(self.channels.values(), exported_at),
        }


def _records_to_rows(
    records: Iterable[IdentityRecord], exported_at: datetime
) -> List[Dict[str, Optional[str]]]:
    return [record.to_row(exported_at) for record in records]
