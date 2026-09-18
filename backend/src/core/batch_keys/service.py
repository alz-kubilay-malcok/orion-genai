"""Excel satırları → LiteLLM key + opsiyonel sonuç maili."""

from __future__ import annotations

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.src.core.batch_keys.excel import BatchRow
from backend.src.core.litellm.generate_key import LiteLLMKeyError, generate_litellm_virtual_key

logger = logging.getLogger(__name__)

GenerateKey = Callable[..., Awaitable[tuple[str, str]]]
SendMail = Callable[..., bool]

# SMTP relay'i (mailenable.allianz-tr.local) art arda onlarca mail ile
# boğmamak için throttle: satır başına en fazla 1 mail/saniye. Batch 200
# satıra kadar çıkabildiğinden (bkz. MAX_BATCH_ROWS) mailsiz akışta bu
# limit devreye girmez, yalnızca ``send_mail=True`` iken uygulanır.
MAIL_MIN_INTERVAL_SECONDS = 1.0


@dataclass(slots=True)
class BatchRowResult:
    row: int
    email: str
    name: str
    key_alias: str
    team: str
    environment: str
    ok: bool
    api_key: str = ""
    mailed: bool = False
    error: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {
            "row": self.row,
            "email": self.email,
            "name": self.name,
            "key_alias": self.key_alias,
            "team": self.team,
            "environment": self.environment,
            "ok": self.ok,
            "api_key": self.api_key,
            "mailed": self.mailed,
            "error": self.error,
        }


def _send_result_mail(
    *,
    row: BatchRow,
    model_name: str,
    api_key: str,
    mailer: SendMail,
    max_parallel_requests: int | None,
) -> bool:
    from backend.src.core.mailing.result_inputs import litellm_result_inputs

    inputs = litellm_result_inputs(
        {
            "status": "completed",
            "requester_name": row.name,
            "genai_orion_panel_ticket_id": row.key_alias,
            "genai_orion_panel_ticket_url": "",
            "environment": row.environment,
            "models": [model_name],
            "key_alias": row.key_alias,
            "litellm_team_id": row.team,
            "max_concurrent_requests": max_parallel_requests,
        },
        api_key=api_key,
    )
    return mailer(
        recipients=[row.email],
        subject=f"[GenAi] {row.key_alias} — API anahtarı",
        template_name="litellm_key_result",
        inputs=inputs,
    )


async def process_batch(
    rows: Sequence[BatchRow],
    *,
    model_name: str,
    send_mail: bool,
    max_parallel_requests: int | None = None,
    generate_key: GenerateKey | None = None,
    mailer: SendMail | None = None,
    metadata: Mapping[str, object] | None = None,
    auto_create_team: bool = False,
) -> list[BatchRowResult]:
    """Excel satırlarından key üretir.

    ``auto_create_team=True`` ise Excel'deki ``team`` kolonu LiteLLM'de yoksa
    otomatik oluşturulur (gerçek ``team_id`` ile); aksi halde eşleşmeyen
    isim satırı hataya düşürür (bkz. ``generate_litellm_virtual_key``).

    ``send_mail=True`` iken satır başı mailler ``MAIL_MIN_INTERVAL_SECONDS``
    (1 saniye) ile throttle edilir — SMTP relay'i art arda onlarca mail ile
    boğmamak için. Key üretimi (LiteLLM çağrısı) throttle'a dahil değil.
    """
    generate = generate_key or generate_litellm_virtual_key
    results: list[BatchRowResult] = []
    started_at = time.monotonic()
    last_mail_at: float | None = None
    logger.info(
        "batch process start rows=%s model=%s send_mail=%s parallel=%s auto_create_team=%s",
        len(rows), model_name, send_mail, max_parallel_requests, auto_create_team,
    )
    for row in rows:
        try:
            plaintext, _provider_id = await generate(
                key_alias=row.key_alias,
                models=[model_name],
                team_id=row.team or None,
                max_parallel_requests=max_parallel_requests,
                environment=row.environment,
                metadata=dict(metadata or {}),
                auto_create_team=auto_create_team,
            )
        except LiteLLMKeyError as exc:
            logger.warning(
                "batch key failed row=%s email=%s: %s",
                row.row, row.email, exc,
            )
            results.append(
                BatchRowResult(
                    row=row.row,
                    email=row.email,
                    name=row.name,
                    key_alias=row.key_alias,
                    team=row.team,
                    environment=row.environment,
                    ok=False,
                    error=str(exc),
                )
            )
            continue
        except Exception as exc:
            logger.exception("batch key unexpected row=%s", row.row)
            results.append(
                BatchRowResult(
                    row=row.row,
                    email=row.email,
                    name=row.name,
                    key_alias=row.key_alias,
                    team=row.team,
                    environment=row.environment,
                    ok=False,
                    error=str(exc),
                )
            )
            continue

        mailed = False
        error = ""
        if send_mail:
            if last_mail_at is not None:
                elapsed = time.monotonic() - last_mail_at
                wait = MAIL_MIN_INTERVAL_SECONDS - elapsed
                if wait > 0:
                    logger.debug("batch mail throttle row=%s wait=%.2fs", row.row, wait)
                    await asyncio.sleep(wait)
            try:
                mailed = bool(
                    _send_result_mail(
                        row=row,
                        model_name=model_name,
                        api_key=plaintext,
                        mailer=mailer or _default_mailer,
                        max_parallel_requests=max_parallel_requests,
                    )
                )
                if not mailed:
                    logger.warning("batch mail not sent row=%s alias=%s", row.row, row.key_alias)
                    error = "mail gönderilemedi"
            except Exception as exc:
                logger.exception("batch mail failed row=%s", row.row)
                error = f"mail hata: {exc}"
            finally:
                last_mail_at = time.monotonic()
        results.append(
            BatchRowResult(
                row=row.row,
                email=row.email,
                name=row.name,
                key_alias=row.key_alias,
                team=row.team,
                environment=row.environment,
                ok=True,
                api_key=plaintext,
                mailed=mailed,
                error=error,
            )
        )
        logger.info(
            "batch key ok row=%s alias=%s mailed=%s",
            row.row, row.key_alias, mailed,
        )
    succeeded = sum(1 for item in results if item.ok)
    mailed_count = sum(1 for item in results if item.mailed)
    duration = time.monotonic() - started_at
    logger.info(
        "batch process done rows=%s succeeded=%s failed=%s mailed=%s duration=%.2fs",
        len(results), succeeded, len(results) - succeeded, mailed_count, duration,
    )
    return results


def _default_mailer(**kwargs: Any) -> bool:
    from backend.src.core.mailing.mailer import send_mail

    return send_mail(**kwargs)


__all__ = ["BatchRowResult", "process_batch"]
