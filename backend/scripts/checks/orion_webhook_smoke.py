"""`POST /webhooks/orion` integration smoke (Step 2 helper + Request insert).

Senaryo:
1. SQLite in-memory + StaticPool + minimal DDL (`requests`, `config_approvers`,
   `outbox_jobs`).
2. 1 active GENAI_APPROVER approver seed'le.
3. `fastapi.testclient.TestClient` ile route'u çalıştır; `talep_turu=
   litellm_api_anahtari` ve geçerli payload gönder.
4. Beklenti:
   - 202 ACCEPTED
   - `requests` tablosunda 1 satır, request_type='litellm_key'
   - `outbox_jobs` tablosunda tam 1 satır, dedupe_key='approval_mail:<id>:v1'
   - Job payload'ında recipient seed edilen email olmalı
5. Aynı payload tekrar → ikinci çağrı `duplicate=True` dönmeli,
   `outbox_jobs` hâlâ 1 satır olmalı.
"""

from __future__ import annotations

import sys
import uuid
from datetime import UTC, datetime, timedelta
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]  # backend/
sys.path.insert(0, str(ROOT))


from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402
from sqlalchemy import text as sql_text  # noqa: E402
from sqlalchemy.ext.asyncio import (  # noqa: E402
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.pool import StaticPool  # noqa: E402

from src.api.routes import orion_webhook  # noqa: E402


SQLITE_DDL = """
CREATE TABLE IF NOT EXISTS requests (
    id CHAR(36) PRIMARY KEY,
    request_type TEXT NOT NULL,
    status TEXT NOT NULL,
    version INTEGER NOT NULL,
    genai_orion_panel_ticket_id TEXT NOT NULL,
    genai_orion_panel_ticket_url TEXT NOT NULL,
    requester_name TEXT NOT NULL,
    requester_email TEXT NOT NULL,
    genai_orion_panel_created_at TEXT NOT NULL,
    raw_genai_orion_panel_payload TEXT NOT NULL,
    department_name TEXT NULL,
    environment TEXT NULL,
    request_description TEXT NULL,
    purpose_code TEXT NULL,
    purpose_text TEXT NULL,
    use_case TEXT NULL,
    models TEXT NULL,
    response_window TEXT NULL,
    usage_frequency TEXT NULL,
    estimated_daily_requests INTEGER NULL,
    max_concurrent_requests INTEGER NULL,
    input_pages REAL NULL,
    output_pages REAL NULL,
    estimated_tokens_per_request INTEGER NULL,
    estimated_peak_rpm INTEGER NULL,
    estimated_peak_tpm INTEGER NULL,
    tpm_approved INTEGER NULL,
    rpm_approved INTEGER NULL,
    key_alias TEXT NULL,
    mcp_server_slug TEXT NULL,
    mcp_tool_names TEXT NULL,
    all_tools INTEGER NULL,
    registry_allows_all_tools INTEGER NULL,
    mcp_server_display_name TEXT NULL,
    project_name TEXT NULL,
    technical_owner_email TEXT NULL,
    repo_platform TEXT NULL,
    repo_url TEXT NULL,
    devops_jira_key TEXT NULL,
    mcp_endpoint_url TEXT NULL,
    minimum_evaluation_score INTEGER NULL,
    additional_notes TEXT NULL,
    brief TEXT NULL,
    channel_or_use_case TEXT NULL,
    priority TEXT NULL,
    target_date TEXT NULL,
    assignee_email TEXT NULL,
    reject_reason TEXT NULL,
    error_code TEXT NULL,
    error_message TEXT NULL,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL,
    completed_at TEXT NULL
);

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

CREATE UNIQUE INDEX IF NOT EXISTS requests_ticket_type_uidx
    ON requests(genai_orion_panel_ticket_id, request_type);
"""


def _app_state_factory(factory):
    """Route'un `state.session_factory` çağrısı için shim."""

    class _Container:
        def __init__(self, factory):
            self.session_factory = factory

    return _Container(factory)


def _make_payload(talep_no: str | None = None) -> dict:
    if talep_no is None:
        talep_no = f"OPS-{uuid.uuid4().hex[:8]}"
    now = datetime.now(UTC).replace(tzinfo=None).isoformat()
    return {
        "talep_turu": "litellm_api_anahtari",
        "talep_no": talep_no,
        "talep_url": "https://orion.example.com/tickets/123",
        "talep_eden_adi": "Test Kullanıcısı",
        "talep_eden_eposta": "tester@example.com",
        "olusturulma_tarihi": now,
        "departman_adi": "Platform",
        "talep_aciklamasi": "smoke amacıyla",
        "kullanim_senaryosu": "test",
        "modeller": ["gpt-4o-mini"],
        "yanit_suresi": "online",
        "kullanim_sikligi": "gunluk",
        "tahmini_gunluk_istek": 100,
        "maksimum_es_zamanli_istek": 5,
        "ortalama_girdi_sayfasi": 1.5,
        "ortalama_cikti_sayfasi": 2.0,
    }


def main() -> int:
    import asyncio

    async def _setup():
        engine = create_async_engine(
            "sqlite+aiosqlite:///:memory:",
            poolclass=StaticPool,
            connect_args={"check_same_thread": False},
        )
        async with engine.begin() as conn:
            for stmt in SQLITE_DDL.strip().split(";"):
                stmt = stmt.strip()
                if not stmt:
                    continue
                await conn.execute(sql_text(stmt))
        factory = async_sessionmaker(engine, expire_on_commit=False)
        async with factory() as session:
            await session.execute(
                sql_text(
                    "INSERT INTO config_approvers(email, scope, sort_order, is_active) "
                    "VALUES ('approver@example.com','GENAI_APPROVAL',0,1)"
                ),
            )
            await session.commit()
        return engine, factory

    engine, factory = asyncio.run(_setup())
    try:
        app = FastAPI()
        app.include_router(
            orion_webhook.router, prefix="/webhooks",
        )
        app.state.container = _app_state_factory(factory)
        client = TestClient(app)

        payload = _make_payload()
        r1 = client.post("/webhooks/orion", json=payload)
        if r1.status_code != 202:
            print(f"FAIL: status={r1.status_code} body={r1.text}")
            return 1
        body1 = r1.json()
        print(f"OK: 202 first request_id={body1['request_id']} enqueued={body1['approver_mails_enqueued']}")
        if body1["status"] != "received":
            print("FAIL: status not received")
            return 1
        if body1["approver_mails_enqueued"] != 1:
            print("FAIL: approver_mails_enqueued != 1")
            return 1

        # Second call → duplicate branch
        r2 = client.post("/webhooks/orion", json=payload)
        if r2.status_code != 202:
            print(f"FAIL: dup status={r2.status_code}")
            return 1
        body2 = r2.json()
        if not body2.get("duplicate"):
            print("FAIL: duplicate flag missing")
            return 1
        if body2["request_id"] != body1["request_id"]:
            print("FAIL: dup returned different request_id")
            return 1
        print(f"OK: duplicate branch second call same id={body2['request_id']}")

        # DB inspect
        async def _inspect():
            async with factory() as s:
                reqs = (await s.execute(sql_text(
                    "SELECT id, request_type, status FROM requests",
                ))).all()
                objs = (await s.execute(sql_text(
                    "SELECT job_type, dedupe_key, payload FROM outbox_jobs",
                ))).all()
            return reqs, objs

        reqs, objs = asyncio.run(_inspect())

        if len(reqs) != 1:
            print(f"FAIL: requests count={len(reqs)} expected 1")
            return 1
        if reqs[0][1] != "litellm_key":
            print(f"FAIL: request_type={reqs[0][1]} expected litellm_key")
            return 1
        if reqs[0][2] != "received":
            print(f"FAIL: status={reqs[0][2]} expected received")
            return 1
        print(f"OK: requests row id={reqs[0][0]} type={reqs[0][1]} status={reqs[0][2]}")

        if len(objs) != 1:
            print(f"FAIL: outbox count={len(objs)} expected 1")
            return 1
        job_type, dedupe, payload_str = objs[0]
        if job_type != "send:approval_mail":
            print(f"FAIL: outbox.job_type={job_type}")
            return 1
        if dedupe != f"approval_mail:{reqs[0][0]}:v1":
            print(f"FAIL: dedupe={dedupe}")
            return 1
        if "approver@example.com" not in payload_str:
            print("FAIL: payload'da seed edilen approver yok")
            return 1
        print(f"OK: outbox row job_type={job_type} dedupe={dedupe}")

        # Validation failure case
        bad = {"talep_turu": "foo_bar", "talep_no": "x"}
        r3 = client.post("/webhooks/orion", json=bad)
        if r3.status_code != 422:
            print(f"FAIL: bad talep_turu status={r3.status_code}")
            return 1
        print(f"OK: unknown talep_turu -> 422 ({r3.json()['error_code']})")

        print("OK: /webhooks/orion end-to-end smoke tüm doğrulamalardan geçti")
        return 0
    finally:
        asyncio.run(engine.dispose())


if __name__ == "__main__":
    sys.exit(main())
