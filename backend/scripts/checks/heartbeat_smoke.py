"""Heartbeat smoke — `WorkerHeartbeatRepository.upsert` cross-dialect contract.

Bu test `dependencies_factory._build_heartbeat_callback` factory wrapper'ı
DEĞİL, repository'nin INSERT → UPDATE akışını doğrular. Factory wrapper
production runner scopes'unda `asyncio.run` ile koşar; nested-loop
problemi nedeniyle bu smoke'ta test edilmemekte.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime

from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import StaticPool

from src.data.db.repository import WorkerHeartbeatRepository


SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS worker_heartbeats (
    worker_id TEXT PRIMARY KEY,
    version TEXT NOT NULL,
    started_at TEXT NOT NULL,
    last_seen_at TEXT NOT NULL,
    active_job_id CHAR(36) NULL,
    scheduler_last_run_at TEXT NULL
);
"""


async def _setup(factory: async_sessionmaker, ddl: str) -> None:
    async with factory() as session:
        await session.execute(_DDL(ddl))
        await session.commit()


def _DDL(sql: str):
    from sqlalchemy import text as _text
    return _text(sql)


async def main_async() -> int:
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        poolclass=StaticPool,
        connect_args={"check_same_thread": False},
    )
    factory = async_sessionmaker(engine, expire_on_commit=False)
    try:
        await _setup(factory, SQLITE_DDL)

        worker_id = "smoke-w-001"
        started_at = datetime.now(UTC).replace(tzinfo=None)

        # 1. INSERT
        async with factory() as session:
            repo = WorkerHeartbeatRepository(session)
            row = await repo.upsert(
                worker_id=worker_id,
                version="v1.0.0",
                started_at=started_at,
                last_seen_at=started_at,
            )
            await session.commit()
            if row is None:
                print("FAIL: insert returned None")
                return 1

        # 2. UPDATE (same primary key, expect 1 row updated)
        later = datetime.now(UTC).replace(tzinfo=None)
        async with factory() as session:
            repo = WorkerHeartbeatRepository(session)
            row = await repo.upsert(
                worker_id=worker_id,
                version="v1.0.1",
                started_at=started_at,
                last_seen_at=later,
            )
            await session.commit()
            if row.last_seen_at != later:
                print("FAIL: last_seen_at update didn't persist")
                return 1

        # 3. Final readback
        async with factory() as session:
            row = await session.get(
                WorkerHeartbeatRepository.model, worker_id,
            )
            if row is None:
                print("FAIL: row not found")
                return 1
            if row.version != "v1.0.1":
                print("FAIL: version not updated")
                return 1
            if row.last_seen_at != later:
                print("FAIL: last_seen_at mismatch on readback")
                return 1

        print(
            "OK: worker_id=%s version=%s last_seen_at=%s"
            % (row.worker_id, row.version, row.last_seen_at),
        )
        return 0
    finally:
        await engine.dispose()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main_async()))
