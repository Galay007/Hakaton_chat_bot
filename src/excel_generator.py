from __future__ import annotations

from io import BytesIO
from typing import Dict, List

import pandas as pd


COLUMNS = [
    "Дата экспорта",
    "Username",
    "Имя и фамилия",
    "Описание",
    "Дата регистрации",
    "Наличие канала",
]


class ExcelGenerator:
    """Builds Excel workbooks with the required tab structure."""

    def build_workbook(
        self, tables: Dict[str, List[Dict[str, str]]]
    ) -> bytes:
        buffer = BytesIO()
        with pd.ExcelWriter(buffer, engine="xlsxwriter") as writer:
            for sheet_name, rows in tables.items():
                frame = pd.DataFrame(rows, columns=COLUMNS)
                frame.to_excel(writer, sheet_name=self._sheet_title(sheet_name), index=False)
        buffer.seek(0)
        return buffer.read()

    @staticmethod
    def _sheet_title(key: str) -> str:
        mapping = {
            "participants": "Участники",
            "mentions": "Упоминания",
            "channels": "Каналы",
        }
        return mapping.get(key, key.title())
