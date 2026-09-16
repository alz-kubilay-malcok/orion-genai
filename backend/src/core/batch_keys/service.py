"""Excel satırları → LiteLLM key + opsiyonel sonuç maili."""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass
from typing import Any

from backend.src.core.batch_keys.excel import BatchRow
from backend.src.core.litellm.generate_key import LiteLLMKeyError, generate_litellm_virtual_key

logger = logging.getLogger(__name__)

GenerateKey = Callable[..., Awaitable[tuple[str, str]]]
SendMail = Callable[..., bool]


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
) -> list[BatchRowResult]:
    generate = generate_key or generate_litellm_virtual_key
    results: list[BatchRowResult] = []
    for row in rows:
        try:
            plaintext, _provider_id = await generate(
                key_alias=row.key_alias,
                models=[model_name],
                team_id=row.team or None,
                max_parallel_requests=max_parallel_requests,
                environment=row.environment,
                metadata=dict(metadata or {}),
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
                    error = "mail gönderilemedi"
            except Exception as exc:
                logger.exception("batch mail failed row=%s", row.row)
                error = f"mail hata: {exc}"
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
    return results


def _default_mailer(**kwargs: Any) -> bool:
    from backend.src.core.mailing.mailer import send_mail

    return send_mail(**kwargs)


__all__ = ["BatchRowResult", "process_batch"]
