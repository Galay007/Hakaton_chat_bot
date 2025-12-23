from __future__ import annotations

from typing import List

from .data_parser import DataParser
from .models import ParsedData


class DataProcessor:
    """Coordinates parsing and prepares structured data."""

    def __init__(self) -> None:
        self.parser = DataParser()

    def parse_document(self, file_name: str, payload: bytes) -> ParsedData:
        return self.parser.parse(file_name, payload)

