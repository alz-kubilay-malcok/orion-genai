"""CSV preview (LiteLLM /key/info) + batch /key/update."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Sequence
from dataclasses import dataclass, field
from typing import Any

from backend.src.core.batch_keys.csv_io import CsvKeyRow, MappingRow
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
    update_key: UpdateKey | None = None,
) -> list[MappingRow]:
    apply = update_key or update_litellm_virtual_key
    results: list[MappingRow] = []
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
        try:
            await apply(
                api_key=row.api_key,
                environment=environment,
                team_id=team or None,
                max_parallel_requests=max_parallel_requests,
                models=models,
                blocked=blocked,
            )
        except LiteLLMKeyError as exc:
            logger.warning("batch update failed alias=%s: %s", row.key_alias, exc)
            results.append(
                MappingRow(
                    email=row.email,
                    key_alias=row.key_alias,
                    status="error",
                    error=str(exc),
                )
            )
            continue
        results.append(
            MappingRow(
                email=row.email,
                key_alias=row.key_alias,
                status="updated",
            )
        )
    return results


__all__ = [
    "PreviewResult",
    "PreviewRow",
    "preview_keys",
    "update_keys",
]
