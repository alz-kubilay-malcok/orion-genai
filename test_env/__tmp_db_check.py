"""Smoke test for `data.db` — engine + ORM + repository + db_init.

Senaryolar:
1. db_init() — schema uygulansın, engine kurulsun, session açılsın.
2. Request satırı ekle → get_by_ticket_id ile geri oku.
3. OutboxRepository.claim_next_pending — tek pending satırı versin.
4. Idempotent re-init — apply listesi boş, ORM session hâlâ aktif.
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "backend" / "src"))

from data.db import DBConfig, RequestRepository, OutboxRepository
from data.db.config import DBConfig
from data.db import db_init, build_async_engine, build_session_factory, dispose_engine
from data.db.models import Request as RequestModel, OutboxJob as OutboxJobModel
from data.db.repository import RequestRepository, OutboxRepository
from data.scripts import flyway_init


def _fresh_db() -> tuple[str, Path]:
    tmp = Path(tempfile.mkdtemp())
    db = tmp / "panel.db"
    return f"sqlite:///{db}", db


async def _all_tables(path: Path) -> set[str]:
    con = sqlite3.connect(path)
    try:
        rows = con.execute(
            "SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {r[0] for r in rows}
    finally:
        con.close()


async def scenario_init_and_crud() -> tuple[str, Path]:
    url, db = _fresh_db()
    os.environ["DB_MODE"] = "sqlite"
    os.environ["SQLITE_DATABASE_URL"] = url
    os.environ["DATABASE_URL"] = ""

    bs = db_init(DBConfig(url=url, dialect="sqlite", echo=False, pool_size=1, pool_recycle_seconds=1800))
    assert bs.applied, "hiç migration uygulanmadı"
    print(f"  [scenario 1] applied: {bs.applied}")

    sf = bs.session_factory
    engine = bs.engine

    async with sf() as s:
        repo = RequestRepository(s)
        rid = uuid4()
        await repo.save(RequestModel(
            id=rid,
            request_type="litellm_key",
            status="received",
            version=1,
            genai_orion_panel_ticket_id="ORION-9001",
            genai_orion_panel_ticket_url="https://orion/orion-9001",
            requester_name="Burak",
            requester_email="burak@a.com",
            genai_orion_panel_created_at=datetime.now(timezone.utc),
            raw_genai_orion_panel_payload="{}",
            models=["gpt-4o"],
            mcp_tool_names=["fetch_claim"],
            all_tools=False,
            registry_allows_all_tools=False,
        ))
        await s.commit()

        fetched = await repo.get_by_ticket_id("ORION-9001", "litellm_key")
        assert fetched is not None and str(fetched.id) == str(rid)
        assert fetched.models == ["gpt-4o"], f"list round-trip failed: {fetched.models!r}"
        assert fetched.mcp_tool_names == ["fetch_claim"]
        assert fetched.requester_name == "Burak"
        print("  [scenario 2] CRUD round-trip OK")

        of_repo = OutboxRepository(s)
        oid = uuid4()
        await of_repo.insert(OutboxJobModel(
            id=oid,
            job_type="SEND_APPROVAL_MAIL",
            aggregate_id=rid,
            payload='{"request_id":"' + str(rid) + '"}',
            dedupe_key=f"send-approval-{oid}",
            status="pending",
        ))
        await s.commit()
        pending = await of_repo.claim_next_pending()
        assert pending is not None and pending.job_type == "SEND_APPROVAL_MAIL"
        print("  [scenario 3] outbox claim_next_pending OK")

    await engine.dispose()
    return url, db


async def scenario_idempotent(url: str, db: Path) -> None:
    """Re-init: applied=[], tablo sayısı korundu."""
    bs2 = db_init(DBConfig(url=url, dialect="sqlite", echo=False, pool_size=1, pool_recycle_seconds=1800))
    assert bs2.applied == [], f"re-init beklenen boş, gelen: {bs2.applied}"
    print(f"  [scenario 4] idempotent re-init: applied=[] (boş)")

    tables = await _all_tables(db)
    assert "_schema_history" in tables
    expected = {
        "requests", "config_approvers", "worker_heartbeats",
        "config_mcp_servers", "config_mcp_tools",
        "approval_tokens", "secrets", "audit_events",
        "outbox_jobs", "mail_messages", "request_revisions",
    }
    assert expected.issubset(tables), f"eksik: {expected - tables}"
    print(f"  12 tables confirmed in sqlite_master: {len(tables)}")

    await bs2.engine.dispose()


async def amain() -> None:
    print("[scenario 1+2+3] init + insert + select + outbox claim")
    url, db = await scenario_init_and_crud()
    try:
        await scenario_idempotent(url, db)
    finally:
        await dispose_engine()
    print("\nPASS — db_init + ORM + repository: 4/4")


if __name__ == "__main__":
    asyncio.run(amain())
