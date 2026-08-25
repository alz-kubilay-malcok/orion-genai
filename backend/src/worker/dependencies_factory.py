"""Worker DI factory — local cipher + heartbeat; no legacy adapter packages."""

from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker

from ..data.db.models.config_approvers import ConfigApprover
from ..data.db.repository import WorkerHeartbeatRepository
from .config import WorkerConfig
from .dependencies import WorkerDependencies

logger = logging.getLogger(__name__)

WORKER_VERSION = "v1.0.0"
_ASYNC_NOTIFIER_MARKER: str = "async_dead_letter_notifier"


def _build_secret_cipher():
    import os

    key = os.getenv("KEY_ENCRYPTION_KEY", "").strip()
    key_version = int(os.getenv("KEY_ENCRYPTION_KEY_VERSION", "1"))
    try:
        from ._local_aes import LocalAesGcmSecretCipher, generate_dev_key_b64

        if not key:
            key = generate_dev_key_b64()
            logger.warning(
                "KEY_ENCRYPTION_KEY empty → generated ephemeral AES key (dev only)",
            )
        return LocalAesGcmSecretCipher(
            current_key_b64=key, current_key_version=key_version,
        )
    except (ImportError, ValueError) as exc:
        logger.warning("secret_cipher unavailable (%s)", exc)
        return None


async def _approver_recipients_from_session(session: AsyncSession) -> list[str]:
    rows = await session.scalars(
        select(ConfigApprover.email)
        .where(
            ConfigApprover.scope == "GENAI_APPROVAL",
            ConfigApprover.is_active.is_(True),
        )
        .order_by(ConfigApprover.sort_order.asc())
    )
    return list(rows.all())


def _build_dead_letter_notifier(
    session_factory: async_sessionmaker[AsyncSession],
):
    from ..core.mailing.outbox_helpers import enqueue_litellm_down_notice

    async def notify(
        *,
        job_id: str,
        job_type: str,
        error_code: str,
        error_message: str,
    ) -> None:
        async with session_factory() as session:
            recipients = await _approver_recipients_from_session(session)
            if not recipients:
                logger.warning("dead-letter notifier skipped: no approvers")
                return
            await enqueue_litellm_down_notice(
                session,
                recipients=recipients,
                request_id=None,
                error_code=error_code or "LITELLM_DOWN",
                error_message=(
                    f"job={job_type} (id={job_id}): {(error_message or '')[:500]}"
                ),
            )
            await session.commit()

    setattr(notify, _ASYNC_NOTIFIER_MARKER, True)
    return notify


def _build_heartbeat_callback(session_factory: async_sessionmaker):
    async def callback(*, worker_id: str, started_at, last_seen_at) -> None:  # noqa: ANN001
        async with session_factory() as session:
            await WorkerHeartbeatRepository(session).upsert(
                worker_id=str(worker_id),
                version=WORKER_VERSION,
                started_at=started_at,
                last_seen_at=last_seen_at,
            )
            await session.commit()

    return callback


def build_worker_dependencies(
    *,
    session_factory: async_sessionmaker,
    config: WorkerConfig,
    worker_version: str = WORKER_VERSION,
) -> WorkerDependencies:
    del config, worker_version
    return WorkerDependencies(
        session_factory=session_factory,
        secret_cipher=_build_secret_cipher(),
        litellm=None,
        mcp_provision=None,
        approval_token_issuer=None,
        heartbeat_callback=_build_heartbeat_callback(session_factory),
        dead_letter_notifier=_build_dead_letter_notifier(session_factory),
    )


def now_utc() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


__all__ = [
    "build_worker_dependencies",
    "now_utc",
    "_build_heartbeat_callback",
    "_build_dead_letter_notifier",
]
