"""Excel → batch satırları. İlk sayfa, ilk satır başlık."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from io import BytesIO, StringIO
from typing import Any, Sequence

from backend.src.core.naming import build_litellm_key_alias

MAX_BATCH_ROWS = 200
TEMPLATE_HEADERS = ("email", "name", "key_alias", "team", "environment")

_HEADER_ALIASES: dict[str, str] = {
    "email": "email",
    "e_posta": "email",
    "eposta": "email",
    "mail": "email",
    "requester_email": "email",
    "talep_eden_eposta": "email",
    "name": "name",
    "ad": "name",
    "adi": "name",
    "isim": "name",
    "ad_soyad": "name",
    "requester_name": "name",
    "talep_eden_adi": "name",
    "key_alias": "key_alias",
    "alias": "key_alias",
    "anahtar_alias": "key_alias",
    "team": "team",
    "team_id": "team",
    "department": "team",
    "departman": "team",
    "departman_adi": "team",
    "litellm_team_id": "team",
    "environment": "environment",
    "ortam": "environment",
}

_TR_FOLD = str.maketrans({
    "ç": "c", "ğ": "g", "ı": "i", "ö": "o", "ş": "s", "ü": "u",
    "Ç": "c", "Ğ": "g", "İ": "i", "Ö": "o", "Ş": "s", "Ü": "u",
})
_NON_ALNUM = re.compile(r"[^a-z0-9]+")


class BatchExcelError(ValueError):
    """Excel şeması / satır limiti hatası."""


@dataclass(frozen=True, slots=True)
class BatchRow:
    row: int
    email: str
    name: str
    key_alias: str
    team: str
    environment: str


@dataclass(frozen=True, slots=True)
class ParsedSheet:
    rows: list[BatchRow]
    headers: list[str]
    values: list[list[str]]


def _norm_header(raw: object) -> str:
    text = str(raw or "").strip().translate(_TR_FOLD).casefold()
    return _NON_ALNUM.sub("_", text).strip("_")


def _cell(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _email_ok(value: str) -> bool:
    if "@" not in value or value.startswith("@") or value.endswith("@"):
        return False
    local, _, domain = value.partition("@")
    return bool(local) and "." in domain


def _default_alias(*, team: str, email: str, row: int, environment: str, model_name: str) -> str:
    local = email.split("@", 1)[0]
    return build_litellm_key_alias(
        department=team or "BATCH",
        ticket=f"{local}-{row}",
        environment=environment,
        purpose=model_name,
    )


def parse_batch_excel(
    data: bytes,
    *,
    model_name: str,
    default_environment: str = "DEV",
) -> list[BatchRow]:
    """İlk sheet'i oku. ``email`` zorunlu; diğer kolonlar opsiyonel."""
    return parse_batch_workbook(
        data, model_name=model_name, default_environment=default_environment,
    ).rows


def parse_batch_workbook(
    data: bytes,
    *,
    model_name: str,
    default_environment: str = "DEV",
) -> ParsedSheet:
    """Orijinal başlık/değerlerle birlikte parse et (CSV çıktısı için)."""
    from openpyxl import load_workbook

    try:
        workbook = load_workbook(filename=BytesIO(data), read_only=True, data_only=True)
    except Exception as exc:
        raise BatchExcelError("Excel okunamadı; .xlsx bekleniyor") from exc
    try:
        sheet = workbook.active
        if sheet is None:
            raise BatchExcelError("Excel boş")
        iterator = sheet.iter_rows(values_only=True)
        header_raw = next(iterator, None)
        if not header_raw:
            raise BatchExcelError("Excel'de başlık satırı yok")
        headers = [_cell(cell) for cell in header_raw]
        while headers and not headers[-1]:
            headers.pop()
        if not headers:
            raise BatchExcelError("Excel'de başlık satırı yok")
        mapping: dict[int, str] = {}
        for index, cell in enumerate(headers):
            field = _HEADER_ALIASES.get(_norm_header(cell))
            if field and field not in mapping.values():
                mapping[index] = field
        if "email" not in mapping.values():
            raise BatchExcelError(
                "Excel'de email kolonu yok (email / eposta / talep_eden_eposta)"
            )

        rows: list[BatchRow] = []
        values: list[list[str]] = []
        for excel_row, raw in enumerate(iterator, start=2):
            cells = [_cell(v) for v in list(raw or ())]
            if not any(cells):
                continue
            padded = cells[: len(headers)] + [""] * max(0, len(headers) - len(cells))
            parsed: dict[str, Any] = {
                field: padded[i] if i < len(padded) else ""
                for i, field in mapping.items()
            }
            email = parsed.get("email", "").strip()
            if not email:
                raise BatchExcelError(f"Satır {excel_row}: email boş")
            if not _email_ok(email):
                raise BatchExcelError(f"Satır {excel_row}: geçersiz email ({email})")
            name = parsed.get("name", "") or email.split("@", 1)[0]
            team = parsed.get("team", "")
            environment = (parsed.get("environment") or default_environment or "DEV").upper()
            alias = parsed.get("key_alias", "") or _default_alias(
                team=team,
                email=email,
                row=excel_row,
                environment=environment,
                model_name=model_name,
            )
            rows.append(
                BatchRow(
                    row=excel_row,
                    email=email,
                    name=name,
                    key_alias=alias,
                    team=team,
                    environment=environment,
                )
            )
            values.append(padded)
            if len(rows) > MAX_BATCH_ROWS:
                raise BatchExcelError(f"En fazla {MAX_BATCH_ROWS} satır işlenir")
        if not rows:
            raise BatchExcelError("Excel'de işlenecek satır yok")
        return ParsedSheet(rows=rows, headers=headers, values=values)
    finally:
        workbook.close()


def build_result_csv(
    headers: Sequence[str],
    values: Sequence[Sequence[str]],
    api_keys: Sequence[str],
) -> bytes:
    """Kaynak kolonların sonuna (veya mevcut `api_key` kolonuna) key basar."""
    if len(values) != len(api_keys):
        raise BatchExcelError("CSV satır sayısı key sayısıyla uyuşmuyor")
    out_headers = list(headers)
    key_index = next(
        (i for i, name in enumerate(out_headers) if _norm_header(name) == "api_key"),
        None,
    )
    if key_index is None:
        out_headers.append("api_key")
        key_index = len(out_headers) - 1
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(out_headers)
    width = len(out_headers)
    for raw, api_key in zip(values, api_keys, strict=True):
        line = [_cell(v) for v in raw]
        if len(line) < width:
            line.extend([""] * (width - len(line)))
        elif len(line) > width:
            line = line[:width]
        line[key_index] = api_key
        writer.writerow(line)
    return buffer.getvalue().encode("utf-8-sig")


def build_template_xlsx() -> bytes:
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "batch"
    sheet.append(list(TEMPLATE_HEADERS))
    sheet.append(["ali.veli@allianz.com.tr", "Ali Veli", "", "GENAI", "DEV"])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


__all__ = [
    "MAX_BATCH_ROWS",
    "TEMPLATE_HEADERS",
    "BatchExcelError",
    "BatchRow",
    "ParsedSheet",
    "build_result_csv",
    "build_template_xlsx",
    "parse_batch_excel",
    "parse_batch_workbook",
]
