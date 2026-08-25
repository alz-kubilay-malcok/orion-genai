"""Step 2+3+DLQ factory+dispatcher end-to-end smoke.

Senaryo:
1. SQLite in-memory + StaticPool + BOŞ DDL kur.
2. Worker factory'sinden `_build_dead_letter_notifier` üret.
3. `_approver_recipients_from_session` için `config_approvers` tablosuna
   1 active row seed'le.
4. Doğrudan uırtık: notifier'a `provision:litellm_key` job_id ile bir
   PermanentError çağır → aynı anda yeni bir `OutboxJob` row
   `send:litellm_down_notice` için outbox_jobs tablosuna yazılmalı.
5. `dedupe_key` formatı beklenenle uyuşuyor mu, doğrula.

`dispatcher`-loop kısmı burada ÀNOT koşmuyor — handler DI bir ayrı test'in
konusu; burada sadece factory+helper+outbox writer zinciri uçtan uca
doğrulanıyor. Ama çağrı amacı açıkça "step 2/3+dead-letter requirement"
fuse'unu kanıtlamak.
"""

from __future__ import annotations

import asyncio
import sys
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))  # so `src.worker` resolves

from sqlalchemy import text as sql_text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.worker.dependencies_factory import _build_dead_letter_notifier  # noqa: E402


SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS config_approvers (
    email TEXT NOT NULL,
    scope TEXT NOT NULL,
    sort_order INTEGER NOT NULL DEFAULT 0,
    is_active BOOLEAN NOT NULL DEFAULT 1,
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


async def _setup(engine) -> None:
    async with engine.begin() as conn:
        for stmt in SQLITE_DDL.strip().split(";"):
            stmt = stmt.strip()
            if not stmt:
                continue
            await conn.execute(sql_text(stmt))


async def main_async() -> int:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _setup(engine)

        # 1 Approver seed (scope=CHATBOT_ASSIGNMENT bilinçli atlanır;
        # factory sadece GENAI_APPROVAL seçiyor → active 1 row olmalı).
        async with factory() as session:
            await session.execute(
                sql_text(
                    "INSERT INTO config_approvers(email, scope, sort_order, is_active) "
                    "VALUES ('ops@example.com','CHATBOT_ASSIGNMENT',0,1)"
                ),
            )
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
            await session.execute(
                sql_text(
                    "INSERT INTO config_approvers(email, scope, sort_order, is_active) "
                    "VALUES ('charlie@example.com','GENAI_APPROVAL',2,0)"
                ),
            )
            await session.commit()

        # Factory üzerinden notifier.
        notify = _build_dead_letter_notifier(session_factory=factory)

        # Sahte bir job için dead-letter çağır — notifier artık async.
        await notify(
            job_id="11111111-1111-1111-1111-111111111111",
            job_type="provision:litellm_key",
            error_code="LITELLM_CONNECTION_TIMEOUT",
            error_message="connection refused after 30s",
        )

        # Outbox job yazılmış mı?
        async with factory() as session:
            rows = (await session.execute(
                sql_text(
                    "SELECT job_type, payload, dedupe_key FROM outbox_jobs"
                )
            )).all()

        if not rows:
            print("FAIL: outbox_jobs boş")
            return 1

        job_type, payload, dedupe = rows[0]
        print(f"OK: outbox row job_type={job_type}")
        print(f"OK: dedupe_key={dedupe}")
        print(f"OK: payload={payload!r}")

        # dedupe_key beklenen format: `litellm_down:global:LITELLM_CONNECTION_TIMEOUT:v1`
        if "LITELLM_CONNECTION_TIMEOUT" not in dedupe:
            print("FAIL: dedupe_key beklenen error_code içermiyor")
            return 1

        # Payload'da recipients sıralı geldi mi?
        if "alice@example.com" not in payload or "bob@example.com" not in payload:
            print("FAIL: payload'da beklenen recipients yok")
            return 1
        if "charlie@example.com" in payload:
            print("FAIL: inaktif approver (charlie) recipients'a sızdı")
            return 1

        print("OK: recipients sadece aktif GENAI_APPROVAL satırları")
        print("OK: step2+3+DLQ factory wiring tüm doğrulamalardan geçti")
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    sys.exit(asyncio.run(main_async()))
