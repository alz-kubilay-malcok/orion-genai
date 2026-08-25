"""Dispatcher DLQ hook smoke — bir job handler'da patlayınca approver mail
outbox'a düşer mi?

Senaryo:
1. SQLite in-memory + StaticPool + minimal `outbox_jobs` + `config_approvers` DDL.
2. 2 active GENAI_APPROVER approver seed'le.
3. `OutboxRepository.insert` ile sahte bir `provision:litellm_key` job
   pending olarak yaz.
4. `OutboxDispatcher` factory'den manuel kur; deps'e handler-PermanentError-raising
   closure + factory `_build_dead_letter_notifier(session_factory)` bağla.
5. `dispatcher.tick()` çağır → akış:
   - claim_next_due → pending → processing
   - handler PermanentError("LITELLM_OFFLINE: upstream unreachable after 30s") raise
   - mark_dead_letter → status=dead_letter, last_error_code='LITELLM_OFFLINE'
   - _notify_dead_letter coroutine → qualify (provision:litellm_key filter OK)
     → enqueue_litellm_down_notice → yeni outbox row 'send:litellm_down_notice'
   - session.commit
6. DB inspect:
   - jobs: 2 satır. (1) dead_letter, (2) pending send:litellm_down_notice
   - recipients payload'da 2 approver mail adresi
   - error_message job_type+id+reason içermeli

Bu test ``_dispatch_one``'un tam claim-mark_dl-notify-commit path'ini
çalıştırır; ``step2_3_dlq_smoke.py`'dan farkı dispatch döngüsünü de
bitişe kadar koşmasıdır.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime, timedelta, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))


from sqlalchemy import text as sql_text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.data.db.repository import OutboxRepository  # noqa: E402
from src.data.db.models.outbox_jobs import OutboxJob  # noqa: E402
from src.worker.config import WorkerConfig  # noqa: E402
from src.worker.dependencies import WorkerDependencies  # noqa: E402
from src.worker.dispatcher import OutboxDispatcher  # noqa: E402
from src.worker.errors import PermanentError  # noqa: E402
from src.worker.dependencies_factory import _build_dead_letter_notifier  # noqa: E402


SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS config_approvers (
    email TEXT NOT NULL,
    scope TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active INTEGER NOT NULL DEFAULT 1,
    UNIQUE(email, scope),
    CHECK(scope IN ('GENAI_APPROVAL','CHATBOT_ASSIGNMENT'))
);

CREATE TABLE IF NOT EXISTS outbox_jobs (
    id CHAR(36) PRIMARY KEY,
    job_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL DEFAULT 'request',
    aggregate_id CHAR(36) NULL,
    payload TEXT NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    status TEXT NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TEXT NOT NULL,
    lease_owner TEXT NULL,
    leased_until TEXT NULL,
    last_error_code TEXT NULL,
    last_error_message TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT NULL
);
"""


def _config() -> WorkerConfig:
    """Smoke konfigi: env üzerinden oku + batch_size=1 yap ki 1 job yeterli."""
    from dataclasses import replace
    base = WorkerConfig.from_env()
    return replace(base, batch_size=1, max_attempts=3, hold_minutes=5)


class _LitellmOfflineError(PermanentError):
    """Smoke için LITELLM_OFFLINE kodu yayan alt sınıf."""

    code = "LITELLM_OFFLINE"


async def _rising_handler_raises_litellm_offline(
    *, metric: dict,
):
    """Geçici bir handler factory — permanent raise, smoke evidence toplar."""
    async def _handler(*, session, payload):
        metric["invoked"] = metric.get("invoked", 0) + 1
        metric["payload"] = payload
        raise _LitellmOfflineError("upstream unreachable after 30s")
    return _handler


async def main_async() -> int:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        async with engine.begin() as conn:
            for stmt in SQLITE_DDL.strip().split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                await conn.execute(sql_text(stmt))

        async with factory() as session:
            await session.execute(
                sql_text(
                    "INSERT INTO config_approvers(email, scope, sort_order, is_active) "
                    "VALUES ('alice@example.com','GENAI_APPROVAL',0,1)"
                ),
            )
            await session.execute(
                sql_text(
                    "INSERT INTO config_approvers(email, scope, sort_order, is_active) "
                    "VALUES ('bob@example.com','GENAI_APPROVAL',1,1)"
                ),
            )
            await session.commit()

        # 1. Sahte job enqueue
        now = datetime.now(UTC).replace(tzinfo=None)
        job_id = "22222222-2222-2222-2222-222222222222"
        async with factory() as session:
            repo = OutboxRepository(session)
            job = OutboxJob(
                id=job_id,
                job_type="provision:litellm_key",
                aggregate_id=None,
                payload='{"schema_version":1,"request_id":"r1","requester_email":"u@x"}',
                dedupe_key=f"litellm_provision:{job_id}:v1",
                status="pending",
                attempts=0,
                max_attempts=3,
                available_at=now,
                created_at=now,
                updated_at=now,
            )
            await repo.insert(job)
            await session.commit()

        # 2. Dispatcher kur
        metric: dict = {}
        handler = await _rising_handler_raises_litellm_offline(metric=metric)
        deps = WorkerDependencies(
            session_factory=factory,
            secret_cipher=None,
            litellm=None,
            mcp_provision=None,
            approval_token_issuer=None,
            heartbeat_callback=None,
            dead_letter_notifier=_build_dead_letter_notifier(
                session_factory=factory,
            ),
        )
        dispatcher = OutboxDispatcher(
            session_factory=factory,
            config=_config(),
            worker_id="smoke-dispatch-001",
            deps=deps,
            handlers={"provision:litellm_key": handler},
        )

        # 3. Tick (smoke zaten async loop içinde → _tick_async doğrudan)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        processed = await dispatcher._tick_async(
            lease=timedelta(seconds=dispatcher._config.lease_seconds),
            now=now,
        )
        assert processed == 1, f"processed={processed}"

        if metric.get("invoked") != 1:
            print(f"FAIL: handler not invoked once (metric={metric})")
            return 1
        print(f"OK: handler invoked; payload={metric['payload']}")

        # 4. DB inspect
        async with factory() as session:
            rows = (await session.execute(sql_text(
                "SELECT id, job_type, status, last_error_code FROM outbox_jobs "
                "ORDER BY created_at ASC"
            ))).all()

        if len(rows) != 2:
            print(f"FAIL: outbox_jobs rows={len(rows)} expected 2")
            for r in rows:
                print(f"   → {r}")
            return 1

        prov_row, notice_row = rows
        if prov_row[1] != "provision:litellm_key":
            print(f"FAIL: first row job_type={prov_row[1]}")
            return 1
        if prov_row[2] != "dead_letter":
            print(f"FAIL: original job status={prov_row[2]} expected dead_letter")
            return 1
        if prov_row[3] != "LITELLM_OFFLINE":
            print(f"FAIL: original last_error_code={prov_row[3]}")
            return 1
        print(f"OK: original job -> dead_letter / last_error_code={prov_row[3]}")

        if notice_row[1] != "send:litellm_down_notice":
            print(f"FAIL: notice job_type={notice_row[1]}")
            return 1
        if notice_row[2] != "pending":
            print(f"FAIL: notice status={notice_row[2]} expected pending")
            return 1
        print(f"OK: notice job drafted (status={notice_row[2]} job_type={notice_row[1]})")

        # 5. Payload inspection
        async with factory() as session:
            payload = (await session.execute(sql_text(
                "SELECT payload FROM outbox_jobs WHERE id != :jid"
            ), {"jid": job_id})).scalar_one()

        if "alice@example.com" not in payload or "bob@example.com" not in payload:
            print(f"FAIL: payload recipients yetersiz → {payload[:300]}")
            return 1
        if "LITELLM_OFFLINE" not in payload:
            print(f"FAIL: payload error_code missing")
            return 1
        if "provision:litellm_key" not in payload:
            print(f"FAIL: payload job_type context missing")
            return 1
        print("OK: notice payload recipients + error_code + job_type all present")

        print("OK: dispatch DLQ smoke tüm doğrulamalardan geçti")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
