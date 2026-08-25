"""Backend `data` — DB schemas ve migration runner.

Alt paketler:
- `schemas.postgresql` — Postgres-native DDL (UUID/CB/JSONB/ARRAY, PG trigger).
- `schemas.sqlite`     — Test/dev ortamı için portable DDL (CHAR(36), JSON,
  CHECK constraint ile enum invariant).
- `scripts.flyway`     — Alembic'in yerine kurulan lightweight migration
  runner: `_schema_history` tablosu ile versioned apply.

Açılışta app startup hook'u `flyway_init(config)` çağırır; sync bir
sağlayıcı, ama asyncpg/aiosqlite üzerinden tek-tek statement execute.
"""
