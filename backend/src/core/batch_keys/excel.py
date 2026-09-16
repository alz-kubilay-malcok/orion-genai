"""Excel → batch satırları. İlk sayfa, ilk satır başlık."""

from __future__ import annotations

import re
from dataclasses import dataclass
from io import BytesIO
from typing import Any

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
    "max_parallel_requests": "max_parallel_requests",
    "max_concurrent_requests": "max_parallel_requests",
    "maksimum_es_zamanli_istek": "max_parallel_requests",
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
    max_parallel_requests: int | None


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


def _int_or_none(value: object) -> int | None:
    text = _cell(value)
    if not text:
        return None
    try:
        number = int(float(text))
    except (TypeError, ValueError):
        return None
    return number if number >= 1 else None


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
        mapping: dict[int, str] = {}
        for index, cell in enumerate(header_raw):
            field = _HEADER_ALIASES.get(_norm_header(cell))
            if field and field not in mapping.values():
                mapping[index] = field
        if "email" not in mapping.values():
            raise BatchExcelError(
                "Excel'de email kolonu yok (email / eposta / talep_eden_eposta)"
            )

        rows: list[BatchRow] = []
        for excel_row, values in enumerate(iterator, start=2):
            cells = list(values or ())
            if not any(_cell(v) for v in cells):
                continue
            parsed: dict[str, Any] = {field: _cell(cells[i]) if i < len(cells) else "" for i, field in mapping.items()}
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
                    max_parallel_requests=_int_or_none(parsed.get("max_parallel_requests")),
                )
            )
            if len(rows) > MAX_BATCH_ROWS:
                raise BatchExcelError(f"En fazla {MAX_BATCH_ROWS} satır işlenir")
        if not rows:
            raise BatchExcelError("Excel'de işlenecek satır yok")
        return rows
    finally:
        workbook.close()


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
    "build_template_xlsx",
    "parse_batch_excel",
]
