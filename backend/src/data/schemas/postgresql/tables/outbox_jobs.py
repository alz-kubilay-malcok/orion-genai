"""`outbox_jobs` — async mail/provisioning işleri için outbox pattern tablosu."""

from __future__ import annotations

from ...registry import Migration

DDL = """
CREATE TABLE IF NOT EXISTS outbox_jobs (
    id UUID PRIMARY KEY,
    job_type TEXT NOT NULL,
    aggregate_type TEXT NOT NULL DEFAULT 'request',
    aggregate_id UUID REFERENCES requests(id) ON DELETE CASCADE,
    payload JSONB NOT NULL,
    dedupe_key TEXT NOT NULL UNIQUE,
    status outbox_status NOT NULL DEFAULT 'pending',
    attempts INTEGER NOT NULL DEFAULT 0,
    max_attempts INTEGER NOT NULL DEFAULT 5,
    available_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    lease_owner TEXT,
    leased_until TIMESTAMPTZ,
    last_error_code TEXT,
    last_error_message TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at TIMESTAMPTZ,
    CONSTRAINT outbox_jobs_attempts_check CHECK (attempts >= 0),
    CONSTRAINT outbox_jobs_max_attempts_check CHECK (max_attempts >= 1),
    CONSTRAINT outbox_jobs_lease_check CHECK (
        (status = 'processing' AND lease_owner IS NOT NULL
         AND leased_until IS NOT NULL)
        OR status <> 'processing'
    )
);

-- Worker poll hot-path: pending/retry 'available_at <= now()' satırlar.
CREATE INDEX IF NOT EXISTS outbox_poll_idx
    ON outbox_jobs (available_at, created_at)
    WHERE status IN ('pending', 'retry');

-- Lease recovery (timed-out processing satırları için).
CREATE INDEX IF NOT EXISTS outbox_lease_recovery_idx
    ON outbox_jobs (leased_until)
    WHERE status = 'processing';
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


outbox_jobs_migration = Migration(version=10, name="outbox_jobs", apply=apply)
