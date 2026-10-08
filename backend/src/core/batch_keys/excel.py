"""Excel → batch satırları. İlk sayfa, ilk satır başlık."""

from __future__ import annotations

import csv
import re
from dataclasses import dataclass
from io import BytesIO, StringIO
from typing import Any, Mapping, Sequence

from backend.src.core.naming import build_litellm_key_alias, litellm_purpose_token

MAX_BATCH_ROWS = 1000
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


def _default_alias(
    *,
    team: str,
    name: str,
    environment: str,
    model_name: str,
) -> str:
    """Boş ``key_alias`` için yeni düzen.

    ``ALZ-{TEAM}-{ENV}-{MODEL}-{PURPOSE}``. Bireyselde ortaya ``BRYSL-{ISIM}``
    girer. Purpose model ``allianz-coder`` / ``text2test`` ise ``CODER``,
    değilse ``OTHER``. Proje segmenti model adından, en fazla 15 karakter.

    LiteLLM ``key_alias`` global olarak unique olmak zorunda. Aynı
    team+environment+model (bireyselde bir de isim) ile iki kez key üretilirse
    ilgili satır LiteLLM'in "already exists" hatasıyla döner. Çakışırsa
    Excel'deki ``key_alias`` kolonuna elle benzersiz bir alias girilebilir.
    """
    return build_litellm_key_alias(
        department=team or "BATCH",
        environment=environment,
        project=model_name,
        purpose=litellm_purpose_token(None, [model_name]),
        person=name,
    )


_ROW_SUFFIX_RE = re.compile(r"^([A-Z]+)(\d+)$")


def strip_batch_row_suffix(alias: str) -> str:
    """Eski batch alias'larındaki (``USERNAME<row>``) sayı ekini kaldırır.

    Eski şema ``ALZ-{TEAM}-{TICKET}-{ENV}-{PURPOSE}``; yalnız 3. segment
    (``TICKET`` — username+satır no) hedeflenir. Yeni alias'ta 3. parça
    ``DEV`` / ``PROD`` / ``BRYSL`` olduğu için eşleşmez ve alias aynen döner.
    """
    parts = alias.split("-")
    if len(parts) < 3:
        return alias
    match = _ROW_SUFFIX_RE.match(parts[2])
    if not match:
        return alias
    parts[2] = match.group(1)
    return "-".join(parts)


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


def _build_batch_sheet(
    headers: list[str],
    rows_iter: Any,
    *,
    model_name: str,
    default_environment: str,
    start_row: int = 2,
) -> ParsedSheet:
    """Excel ve CSV parser'ının paylaştığı satır → ``BatchRow`` mantığı."""
    mapping: dict[int, str] = {}
    for index, cell in enumerate(headers):
        field = _HEADER_ALIASES.get(_norm_header(cell))
        if field and field not in mapping.values():
            mapping[index] = field
    if "email" not in mapping.values():
        raise BatchExcelError(
            "email kolonu yok (email / eposta / talep_eden_eposta)"
        )

    rows: list[BatchRow] = []
    values: list[list[str]] = []
    for row_number, cells in enumerate(rows_iter, start=start_row):
        if not any(cells):
            continue
        padded = list(cells[: len(headers)]) + [""] * max(0, len(headers) - len(cells))
        parsed: dict[str, Any] = {
            field: padded[i] if i < len(padded) else ""
            for i, field in mapping.items()
        }
        email = parsed.get("email", "").strip()
        if not email:
            raise BatchExcelError(f"Satır {row_number}: email boş")
        if not _email_ok(email):
            raise BatchExcelError(f"Satır {row_number}: geçersiz email ({email})")
        name = parsed.get("name", "") or email.split("@", 1)[0]
        team = parsed.get("team", "")
        environment = (parsed.get("environment") or default_environment or "DEV").upper()
        alias = parsed.get("key_alias", "") or _default_alias(
            team=team,
            name=name,
            environment=environment,
            model_name=model_name,
        )
        rows.append(
            BatchRow(
                row=row_number,
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
        raise BatchExcelError("İşlenecek satır yok")
    return ParsedSheet(rows=rows, headers=headers, values=values)


def parse_batch_workbook(
    data: bytes,
    *,
    model_name: str,
    default_environment: str = "DEV",
) -> ParsedSheet:
    """Orijinal başlık/değerlerle birlikte .xlsx parse et."""
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
        cell_rows = ([_cell(v) for v in list(raw or ())] for raw in iterator)
        return _build_batch_sheet(
            headers, cell_rows, model_name=model_name, default_environment=default_environment,
        )
    finally:
        workbook.close()


def parse_batch_csv(
    data: bytes,
    *,
    model_name: str,
    default_environment: str = "DEV",
) -> ParsedSheet:
    """Create girdisi için .csv desteği; aynı kolon şeması (email,name,key_alias,team,environment)."""
    try:
        text = data.decode("utf-8-sig")
    except UnicodeDecodeError as exc:
        raise BatchExcelError("CSV UTF-8 olmalı") from exc
    reader = csv.reader(StringIO(text))
    try:
        header_raw = next(reader)
    except StopIteration as exc:
        raise BatchExcelError("CSV boş") from exc
    headers = [_cell(cell) for cell in header_raw]
    while headers and not headers[-1]:
        headers.pop()
    if not headers:
        raise BatchExcelError("CSV'de başlık satırı yok")
    cell_rows = ([_cell(v) for v in row] for row in reader)
    return _build_batch_sheet(
        headers, cell_rows, model_name=model_name, default_environment=default_environment,
    )


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


EXPORT_COLUMNS = ("email", "name", "key_alias", "team", "environment", "api_key", "status", "error")


def build_export_csv(rows: Sequence[Mapping[str, object]]) -> bytes:
    """Ekrandaki (seçilen) satırları CSV'ye yazar — export butonu."""
    buffer = StringIO()
    writer = csv.writer(buffer)
    writer.writerow(EXPORT_COLUMNS)
    for row in rows:
        writer.writerow([_cell(row.get(col)) for col in EXPORT_COLUMNS])
    return buffer.getvalue().encode("utf-8-sig")


def build_export_xlsx(rows: Sequence[Mapping[str, object]]) -> bytes:
    """Ekrandaki (seçilen) satırları .xlsx'e yazar — export butonu."""
    from openpyxl import Workbook

    workbook = Workbook()
    sheet = workbook.active
    assert sheet is not None
    sheet.title = "keys"
    sheet.append(list(EXPORT_COLUMNS))
    for row in rows:
        sheet.append([_cell(row.get(col)) for col in EXPORT_COLUMNS])
    buffer = BytesIO()
    workbook.save(buffer)
    return buffer.getvalue()


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
    "EXPORT_COLUMNS",
    "MAX_BATCH_ROWS",
    "TEMPLATE_HEADERS",
    "BatchExcelError",
    "BatchRow",
    "ParsedSheet",
    "build_export_csv",
    "build_export_xlsx",
    "build_result_csv",
    "build_template_xlsx",
    "parse_batch_csv",
    "parse_batch_excel",
    "parse_batch_workbook",
    "strip_batch_row_suffix",
]
