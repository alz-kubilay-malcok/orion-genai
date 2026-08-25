"""Enum tipleri (PG native). Diğer DDL'lerden önce uygulanmalı."""

from __future__ import annotations

from ...registry import Migration

# Tek bir SQL bloğunda tüm enum'lar drop/create. `IF NOT EXISTS` Postgres
# 9.6+ için geçerli. Apply sırasında idempotent: iki kez çalıştırılırsa
# sessizce geçer; `_schema_history` aynı `name` ile duplicate insert'i
# önler (zaten flyway_init kontrol yapıyor).
DDL = """
DO $$ BEGIN
    CREATE TYPE request_type AS ENUM (
        'litellm_key', 'mcp_key', 'mcp_server_registry', 'chatbot_support'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE environment AS ENUM ('DEV', 'STG', 'TEST', 'PROD');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE request_status AS ENUM (
        'received', 'waiting_approval', 'assigned',
        'provisioning', 'completed', 'rejected', 'failed', 'expired'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE repo_platform AS ENUM ('GITHUB', 'BITBUCKET');
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;

DO $$ BEGIN
    CREATE TYPE outbox_status AS ENUM (
        'pending', 'processing', 'retry', 'completed', 'dead_letter'
    );
EXCEPTION
    WHEN duplicate_object THEN NULL;
END $$;
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


enums_migration = Migration(version=1, name="enums", apply=apply)
