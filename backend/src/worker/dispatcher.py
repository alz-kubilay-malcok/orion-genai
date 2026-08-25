"""Outbox dispatcher — bir job'ı claim edip handler'a verir; sonuç sınıfına göre schedule eder.

Akış (tek tick):
1. `OutboxRepository.claim_next_due` → `processing`'e çevirip lease al.
2. `OUTBOX_HANDLERS[job_type]('session', payload)'a dispatch.
3. Sonuç değerlendirmesi:
   - başarı → `mark_completed`
   - `RetryHeld` → `available_at = now + hold_minutes` + `mark_retry`
   - `TransientError` → eksponansiyel backoff, `max_attempts` aşılırsa dead-letter
   - `PermanentError` → doğrudan dead-letter
   - bilinmeyen exception → fail-safe: dead-letter (operatör-review)
4. Her job için committed transaction.

Concurrent worker pattern'ı: `claim_next_due` zaten UPDATE WHERE-clauses
ile race'i DB'ye bırakıyor. Tek instance gereksinimi yok; birden çok
worker `--worker-id A/B/C` ile aynı anda çalışabilir.
"""

from __future__ import annotations

import asyncio
import json
import logging
import os
import socket
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..data.db.repository import (
    OUTBOX_COMPLETED,
    OUTBOX_DEAD_LETTER,
    OUTBOX_RETRY,
    OutboxRepository,
)
from .dependencies import WorkerDependencies
from .errors import (
    PermanentError,
    RetryHeld,
    TransientError,
)
from .config import WorkerConfig
from .handlers import (
    JOB_TYPE_PROVISION_LITELLM,
    OUTBOX_HANDLERS,
    build_handlers,
)

logger = logging.getLogger(__name__)


def _make_worker_id() -> str:
    """Stable-per-process INSTANCE kimliği. Log + DB lease_owner için bilinebilir."""
    return f"{socket.gethostname()}-{os.getpid()}-{uuid.uuid4().hex[:8]}"


@dataclass(frozen=True, slots=True)
class DispatchOutcome:
    """Bir job için tek tick'te dispatch sonucu — log/metrics için."""

    job_id: str
    job_type: str
    final_status: str  # completed / retry / dead_letter
    error_code: str | None = None
    elapsed_ms: int = 0


class OutboxDispatcher:
    """Worker'ın polling döngüsünde kullandığı dispatcher."""

    def __init__(
        self,
        session_factory: async_sessionmaker[AsyncSession],
        config: WorkerConfig,
        *,
        worker_id: str | None = None,
        deps: WorkerDependencies | None = None,
        handlers: dict | None = None,
    ) -> None:
        self._session_factory = session_factory
        self._config = config
        self._worker_id = worker_id or _make_worker_id()
        self._deps = deps
        # Handler resolution sırası:
        # 1. explicit `handlers` argümanı (test injection için),
        # 2. `deps.tablosu varsa build_handlers(deps)`,
        # 3. legacy modül-load dispatch tablosu (geriye uyumlu).
        if handlers is not None:
            self._handlers = handlers
        elif deps is not None:
            self._handlers = build_handlers(deps)
        else:
            self._handlers = OUTBOX_HANDLERS
        self._stop = threading.Event()

    @property
    def worker_id(self) -> str:
        return self._worker_id

    def request_stop(self) -> None:
        self._stop.set()

    def tick(self) -> int:
        """Tek bir döngü adımı — claim + handle batch.

        Returns: dispatch edilen job sayısı.
        """
        lease = timedelta(seconds=self._config.lease_seconds)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        return asyncio.run(self._tick_async(lease, now))

    # ---- async iç iskelet ---------------------------------------------

    async def _tick_async(self, lease: timedelta, now: datetime) -> int:
        from ..observability.events import log_event

        async with self._session_factory() as session:
            repository = OutboxRepository(session)
            claimed = await repository.claim_next_due(
                worker_id=self._worker_id,
                lease_duration=lease,
                now=now,
                batch_size=self._config.batch_size,
            )
            if not claimed:
                await session.rollback()
                log_event(
                    logger, "outbox.claim.empty",
                    worker_id=self._worker_id,
                )
                return 0

            log_event(
                logger, "outbox.claim.batch",
                worker_id=self._worker_id,
                batch_size=len(claimed),
            )

            outcomes: list[DispatchOutcome] = []
            for job in claimed:
                outcome = await self._dispatch_one(session, repository, job)
                outcomes.append(outcome)

            await session.commit()

        # tick sonu özetini kompakt tek satıra indir.
        per_status: dict[str, int] = {}
        per_error: dict[str, int] = {}
        max_elapsed = 0
        for outcome in outcomes:
            per_status[outcome.final_status] = per_status.get(outcome.final_status, 0) + 1
            if outcome.error_code:
                per_error[outcome.error_code] = per_error.get(outcome.error_code, 0) + 1
            max_elapsed = max(max_elapsed, outcome.elapsed_ms)
        log_event(
            logger, "outbox.tick.completed",
            worker_id=self._worker_id,
            batch_size=len(outcomes),
            per_status=per_status,
            per_error=per_error,
            max_elapsed_ms=max_elapsed,
        )

        for outcome in outcomes:
            logger.info(
                "outbox tick",
                extra={
                    "worker_id": self._worker_id,
                    "job_id": outcome.job_id,
                    "job_type": outcome.job_type,
                    "final_status": outcome.final_status,
                    "elapsed_ms": outcome.elapsed_ms,
                    "error_code": outcome.error_code,
                },
            )
        return len(outcomes)

    # ---- tek job dispatch ---------------------------------------------

    async def _dispatch_one(
        self,
        session: AsyncSession,
        repository: OutboxRepository,
        job,
    ) -> DispatchOutcome:
        handler = self._handlers.get(job.job_type)
        started = time.monotonic()
        if handler is None:
            await repository.mark_dead_letter(
                job.id,
                error_code="UNHANDLED_JOB_TYPE",
                error_message=f"job_type dispatch edilmemiş: {job.job_type!r}",
            )
            await _notify_dead_letter(
                self._deps, job_id=job.id, job_type=job.job_type,
                error_code="UNHANDLED_JOB_TYPE",
                error_message=f"job_type dispatch edilmemiş: {job.job_type!r}",
            )
            return DispatchOutcome(
                job_id=str(job.id),
                job_type=job.job_type,
                final_status=OUTBOX_DEAD_LETTER,
                error_code="UNHANDLED_JOB_TYPE",
                elapsed_ms=_elapsed_ms(started),
            )

        # Payload parse — bozuk JSON = permanent
        try:
            payload = json.loads(job.payload) if isinstance(job.payload, str) else dict(job.payload)
        except (ValueError, TypeError) as exc:
            await repository.mark_dead_letter(
                job.id,
                error_code="BAD_PAYLOAD",
                error_message=str(exc),
            )
            await _notify_dead_letter(
                self._deps, job_id=job.id, job_type=job.job_type,
                error_code="BAD_PAYLOAD", error_message=str(exc),
            )
            return DispatchOutcome(
                job_id=str(job.id),
                job_type=job.job_type,
                final_status=OUTBOX_DEAD_LETTER,
                error_code="BAD_PAYLOAD",
                elapsed_ms=_elapsed_ms(started),
            )

        try:
            await handler(session=session, payload=payload)
        except RetryHeld as exc:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            held_available = now + timedelta(minutes=self._config.hold_minutes)
            # max_attempts aşımında dead-letter'a çek.
            if job.attempts >= self._config.max_attempts:
                await repository.mark_dead_letter(
                    job.id, error_code=exc.code, error_message=exc.message,
                )
                await _notify_dead_letter(
                    self._deps, job_id=job.id, job_type=job.job_type,
                    error_code=exc.code, error_message=exc.message,
                )
                return _outcome(job, OUTBOX_DEAD_LETTER, exc.code, started)
            await repository.mark_retry(
                job.id, available_at=held_available,
                error_code=exc.code, error_message=exc.message,
            )
            return _outcome(job, OUTBOX_RETRY, exc.code, started)
        except PermanentError as exc:
            await repository.mark_dead_letter(
                job.id, error_code=exc.code, error_message=exc.message,
            )
            await _notify_dead_letter(
                self._deps, job_id=job.id, job_type=job.job_type,
                error_code=exc.code, error_message=exc.message,
            )
            return _outcome(job, OUTBOX_DEAD_LETTER, exc.code, started)
        except TransientError as exc:
            now = datetime.now(timezone.utc).replace(tzinfo=None)
            if job.attempts >= self._config.max_attempts:
                await repository.mark_dead_letter(
                    job.id, error_code=exc.code, error_message=exc.message,
                )
                await _notify_dead_letter(
                    self._deps, job_id=job.id, job_type=job.job_type,
                    error_code=exc.code, error_message=exc.message,
                )
                return _outcome(job, OUTBOX_DEAD_LETTER, exc.code, started)
            backoff = _exp_backoff_seconds(job.attempts)
            available = now + timedelta(seconds=backoff)
            await repository.mark_retry(
                job.id, available_at=available,
                error_code=exc.code, error_message=exc.message,
            )
            return _outcome(job, OUTBOX_RETRY, exc.code, started)
        except Exception as exc:  # noqa: BLE001 — fail-safe
            await repository.mark_dead_letter(
                job.id,
                error_code="UNEXPECTED_EXCEPTION",
                error_message=repr(exc)[:2000],
            )
            await _notify_dead_letter(
                self._deps, job_id=job.id, job_type=job.job_type,
                error_code="UNEXPECTED_EXCEPTION",
                error_message=repr(exc)[:2000],
            )
            return _outcome(job, OUTBOX_DEAD_LETTER, "UNEXPECTED_EXCEPTION", started)
        else:
            await repository.mark_completed(job.id)
            return _outcome(job, OUTBOX_COMPLETED, None, started)


def _outcome(
    job, final_status: str, error_code: Optional[str], started: float,
) -> DispatchOutcome:
    return DispatchOutcome(
        job_id=str(job.id),
        job_type=job.job_type,
        final_status=final_status,
        error_code=error_code,
        elapsed_ms=_elapsed_ms(started),
    )


def _elapsed_ms(started: float) -> int:
    return int((time.monotonic() - started) * 1000)


def _exp_backoff_seconds(attempt: int) -> int:
    """`LITELLM_RETRY/10` varsayımıyla: 1, 2, 4, 8, 16 dakika.

    Cap yok (max_attempts buna da guard). المستخدم uygar: 2^attempt minute.
    """
    # `attempt` sayısı 1..n; ilk retry 1 dakika sonra.
    return int(60 * (2 ** max(0, attempt - 1)))


# Dead-letter hook'u hangi job_type'larda approver'a mail atar?
# Şu an sadece LiteLLM provision patlamaları (use-case: "litellm down").
_DLQ_NOTIFICATION_JOB_TYPES: frozenset[str] = frozenset(
    {JOB_TYPE_PROVISION_LITELLM}
)


async def _notify_dead_letter(
    deps: Optional[WorkerDependencies],
    *,
    job_id: str,
    job_type: str,
    error_code: str,
    error_message: str,
) -> None:
    """Dead-letter sonrası approver mail enqueue — best-effort.

    Test/CLI path'inde `deps=None` veya `dead_letter_notifier=None` ise
    sessizce pas geçer. Sadece `_DLQ_NOTIFICATION_JOB_TYPES` listedeki
    job_type'lar için notify yapar (diğerleri sadece DB'de dead-letter
    olarak işaretlenir).
    """
    if deps is None:
        return
    notifier = getattr(deps, "dead_letter_notifier", None)
    if notifier is None:
        return
    if job_type not in _DLQ_NOTIFICATION_JOB_TYPES:
        return

    try:
        result = notifier(
            job_id=str(job_id),
            job_type=job_type,
            error_code=error_code,
            error_message=error_message,
        )
        if asyncio.iscoroutine(result):
            await result
    except Exception as exc:  # noqa: BLE001 — notify non-fatal
        logger.warning(
            "dead_letter_notifier invoke başarısız",
            extra={"job_id": job_id, "job_type": job_type, "error": repr(exc)},
        )
