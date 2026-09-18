"""CSV preview (LiteLLM /key/info) + batch /key/update."""

from __future__ import annotations

import logging
import time
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.src.core.batch_keys.csv_io import CsvKeyRow, MappingRow
from backend.src.core.batch_keys.excel import strip_batch_row_suffix
from backend.src.core.litellm.generate_key import (
    LiteLLMKeyError,
    LiteLLMKeyInfo,
    fetch_key_info,
    update_litellm_virtual_key,
)

logger = logging.getLogger(__name__)

FetchInfo = Callable[..., Awaitable[LiteLLMKeyInfo | None]]
UpdateKey = Callable[..., Awaitable[dict[str, Any]]]


@dataclass(slots=True)
class PreviewRow:
    row: int
    email: str
    name: str
    api_key: str
    found: bool
    key_alias: str = ""
    team: str = ""
    models: list[str] = field(default_factory=list)
    max_parallel_requests: int | None = None
    blocked: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "email": self.email,
            "name": self.name,
            "api_key": self.api_key,
            "found": self.found,
            "key_alias": self.key_alias,
            "team": self.team,
            "models": self.models,
            "max_parallel_requests": self.max_parallel_requests,
            "blocked": self.blocked,
            "error": self.error,
        }


@dataclass(slots=True)
class PreviewResult:
    csv_rows: int
    with_api_key: int
    found: int
    missing: int
    rows: list[PreviewRow]

    def as_dict(self) -> dict[str, Any]:
        return {
            "csv_rows": self.csv_rows,
            "with_api_key": self.with_api_key,
            "found": self.found,
            "missing": self.missing,
            "rows": [row.as_dict() for row in self.rows],
        }


async def preview_keys(
    rows: Sequence[CsvKeyRow],
    *,
    environment: str,
    fetch_info: FetchInfo | None = None,
) -> PreviewResult:
    lookup = fetch_info or fetch_key_info
    out: list[PreviewRow] = []
    started_at = time.monotonic()
    logger.info("batch preview start rows=%s environment=%s", len(rows), environment)
    for row in rows:
        if not row.api_key:
            out.append(
                PreviewRow(
                    row=row.row,
                    email=row.email,
                    name=row.name,
                    api_key="",
                    found=False,
                    key_alias=row.key_alias,
                    error="api_key boş",
                )
            )
            continue
        try:
            info = await lookup(api_key=row.api_key, environment=environment)
        except LiteLLMKeyError as exc:
            logger.warning("batch preview lookup failed row=%s: %s", row.row, exc)
            out.append(
                PreviewRow(
                    row=row.row,
                    email=row.email,
                    name=row.name,
                    api_key=row.api_key,
                    found=False,
                    key_alias=row.key_alias,
                    error=str(exc),
                )
            )
            continue
        if info is None:
            out.append(
                PreviewRow(
                    row=row.row,
                    email=row.email,
                    name=row.name,
                    api_key=row.api_key,
                    found=False,
                    key_alias=row.key_alias,
                    error="LiteLLM'de bulunamadı",
                )
            )
            continue
        out.append(
            PreviewRow(
                row=row.row,
                email=row.email,
                name=row.name,
                api_key=row.api_key,
                found=True,
                key_alias=info.key_alias or row.key_alias,
                team=info.team_id,
                models=list(info.models),
                max_parallel_requests=info.max_parallel_requests,
                blocked=info.blocked,
            )
        )
    with_key = sum(1 for item in out if item.api_key)
    found = sum(1 for item in out if item.found)
    duration = time.monotonic() - started_at
    logger.info(
        "batch preview done rows=%s with_api_key=%s found=%s missing=%s duration=%.2fs",
        len(out), with_key, found, len(out) - found, duration,
    )
    return PreviewResult(
        csv_rows=len(out),
        with_api_key=with_key,
        found=found,
        missing=len(out) - found,
        rows=out,
    )


async def update_keys(
    rows: Sequence[PreviewRow],
    *,
    environment: str,
    team: str | None = None,
    max_parallel_requests: int | None = None,
    models: list[str] | None = None,
    blocked: bool | None = None,
    clear_metadata: bool = False,
    strip_row_suffix: bool = False,
    resolve_team_per_row: bool = False,
    update_key: UpdateKey | None = None,
) -> list[MappingRow]:
    """Preview'daki (seçilen) key'lere form alanlarını uygular.

    ``clear_metadata=True`` → seçilen key'lerin ``metadata`` alanı (batch/
    webhook'tan kalan ``source``/``ticket`` vb.) LiteLLM'de boşaltılır.
    ``strip_row_suffix=True`` → alias'ı ``USERNAME<row>`` formatında olan
    (eski batch akışının eklediği satır numarasını taşıyan) key'lerin
    alias'ından o sayı temizlenip ``key_alias`` olarak LiteLLM'e gönderilir;
    zaten temiz olan alias'lar dokunulmadan kalır.

    ``resolve_team_per_row=True`` (yalnız global ``team`` boşken devreye
    girer) → her satırın **kendi** ``row.team`` değeri (preview'da LiteLLM
    `/key/info`'dan gelen — eski akışın hiç doğrulamadan `team_id` olarak
    kaydettiği ham string olabilir) LiteLLM'deki gerçek takımlarla adına
    göre eşleştirilir; eşleşme yoksa o isimle **gerçek bir takım
    oluşturulur** ve key oraya taşınır (``auto_create_team=True``). Bu
    sayede "team validation olmadan string ile oluşturulmuş" eski/bozuk
    key'ler tek tek düzeltilir; ``row.team`` boşsa o satırın takımına
    dokunulmaz.
    """
    apply = update_key or update_litellm_virtual_key
    results: list[MappingRow] = []
    started_at = time.monotonic()
    logger.info(
        "batch update start rows=%s team=%s parallel=%s models=%s blocked=%s "
        "clear_metadata=%s strip_row_suffix=%s resolve_team_per_row=%s",
        len(rows), team, max_parallel_requests, models, blocked,
        clear_metadata, strip_row_suffix, resolve_team_per_row,
    )
    for row in rows:
        if not row.found or not row.api_key:
            results.append(
                MappingRow(
                    email=row.email,
                    key_alias=row.key_alias,
                    status="skipped",
                    error=row.error or "preview'da bulunamadı",
                )
            )
            continue
        new_alias = strip_batch_row_suffix(row.key_alias) if strip_row_suffix and row.key_alias else row.key_alias
        alias_changed = strip_row_suffix and new_alias != row.key_alias
        # Global `team` her zaman önceliklidir (tüm seçili satırlara aynı
        # takım). Boşsa ve `resolve_team_per_row` açıksa, satırın kendi
        # (muhtemelen bozuk) team değeri kullanılır — bulunamazsa oluşturulur.
        row_team = (row.team or "").strip() if (resolve_team_per_row and not team) else ""
        target_team = (team or "").strip() or row_team or None
        auto_create = bool(row_team and not team)
        if (
            not alias_changed
            and clear_metadata is False
            and target_team is None
            and max_parallel_requests is None
            and models is None
            and blocked is None
        ):
            results.append(
                MappingRow(
                    email=row.email,
                    key_alias=row.key_alias,
                    status="skipped",
                    error="güncellenecek alan yok",
                )
            )
            continue
        try:
            await apply(
                api_key=row.api_key,
                environment=environment,
                team_id=target_team,
                max_parallel_requests=max_parallel_requests,
                models=models,
                blocked=blocked,
                clear_metadata=clear_metadata,
                key_alias=new_alias if alias_changed else None,
                auto_create_team=auto_create,
            )
        except LiteLLMKeyError as exc:
            logger.warning("batch update failed alias=%s: %s", row.key_alias, exc)
            results.append(
                MappingRow(
                    email=row.email,
                    key_alias=row.key_alias,
                    status="error",
                    error=str(exc),
                    team=row.team,
                )
            )
            continue
        results.append(
            MappingRow(
                email=row.email,
                key_alias=new_alias if alias_changed else row.key_alias,
                status="updated",
                team=target_team or row.team,
            )
        )
        logger.info(
            "batch update ok email=%s alias=%s alias_changed=%s team=%s auto_create_team=%s",
            row.email, new_alias if alias_changed else row.key_alias, alias_changed,
            target_team or row.team, auto_create,
        )
    succeeded = sum(1 for item in results if item.status == "updated")
    failed = sum(1 for item in results if item.status == "error")
    duration = time.monotonic() - started_at
    logger.info(
        "batch update done rows=%s succeeded=%s failed=%s skipped=%s duration=%.2fs",
        len(results), succeeded, failed, len(results) - succeeded - failed, duration,
    )
    return results


__all__ = [
    "PreviewResult",
    "PreviewRow",
    "preview_keys",
    "update_keys",
]
