"""Create-output CSV → email + api_key satırları."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from io import StringIO
from typing import Sequence

from backend.src.core.batch_keys.excel import MAX_BATCH_ROWS, BatchExcelError

_HEADER_ALIASES: dict[str, str] = {
    "email": "email",
    "e_posta": "email",
    "eposta": "email",
    "mail": "email",
    "requester_email": "email",
    "talep_eden_eposta": "email",
    "api_key": "api_key",
    "key": "api_key",
    "name": "name",
    "ad": "name",
    "ad_soyad": "name",
    "key_alias": "key_alias",
    "alias": "key_alias",
}
_TR_FOLD = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u",
})
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


def _norm_header(raw: object) -> str:
    text = str(raw or "").strip().translate(_TR_FOLD).casefold()
    return _NON_ALNUM.sub("_", text).strip("_")


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


@dataclass(frozen=True, slots=True)
class CsvKeyRow:
    row: int
    email: str
    name: str
    key_alias: str
    api_key: str


@dataclass(slots=True)
class MappingRow:
    email: str
    key_alias: str
    status: str
    error: str = ""


def parse_output_csv(data: bytes) -> list[CsvKeyRow]:
    """Create çıktısı CSV. ``api_key`` zorunlu; ``email`` görüntü."""
    text = data.decode("utf-8-sig")
    reader = csv.reader(StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise BatchExcelError("CSV boş") from exc
    mapping: dict[int, str] = {}
    for index, cell in enumerate(header):
        field = _HEADER_ALIASES.get(_norm_header(cell))
        if field and field not in mapping.values():
            mapping[index] = field
    if "api_key" not in mapping.values():
        raise BatchExcelError("CSV'de api_key kolonu yok")
    rows: list[CsvKeyRow] = []
    for excel_row, values in enumerate(reader, start=2):
        if not any(_cell(v) for v in values):
            continue
        parsed = {
            field: _cell(values[i]) if i < len(values) else ""
            for i, field in mapping.items()
        }
        rows.append(
            CsvKeyRow(
                row=excel_row,
                email=parsed.get("email", "").strip(),
                name=parsed.get("name", ""),
                key_alias=parsed.get("key_alias", ""),
                api_key=parsed.get("api_key", "").strip(),
            )
        )
        if len(rows) > MAX_BATCH_ROWS:
            raise BatchExcelError(f"En fazla {MAX_BATCH_ROWS} satır işlenir")
    if not rows:
        raise BatchExcelError("CSV'de işlenecek satır yok")
    return rows


def build_update_result_csv(rows: Sequence[MappingRow]) -> bytes:
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(["email", "key_alias", "status", "error"])
    for row in rows:
        writer.writerow([row.email, row.key_alias, row.status, row.error])
    return buffer.getvalue().encode("utf-8-sig")


__all__ = [
    "CsvKeyRow",
    "MappingRow",
    "build_update_result_csv",
    "parse_output_csv",
]
