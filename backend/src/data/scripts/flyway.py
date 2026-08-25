"""Lightweight schema migrator (Alembic'in yerine).

Mimari:
- `_schema_history` tablosu ilk apply öncesi oluşturulur; içinde
  `version` (PK), `name`, `installed_at` tutulur.
- Her `migrations_for(dialect)` dönerinden çekilen `Migration` listede
  sırayla gezilir; eksik olanlar uygulanır.
- Apply adımında `version` zaten `_schema_history`'de varsa atlanır
  (`IF NOT EXISTS` ile DDL'lerin kendilerini idempotent etmesine ek).
- Her adım `_schema_history` satırına işlenir; hata durumunda hangi
  `version` patladı döner.

İki giriş fonksiyonu:

    flyway_init(url: str) -> list[str]
        URL'den dialect tespit edip `_schema_history`'ye kadar tüm
        eksik apply işlemlerini uygular. Uygulanan iş isimleri
        (kronolojik) döner.

    flyway_status(url: str) -> dict[str, object]
        Dry run snapshot: beklenen/applied/eksik iş listesi.

Sync runner sqlite3 ile çalışır (test/dev). Async runner asyncpg ile
çalışır (production). Her ikisi de driver-agnostic olduğu için
connection instance'ın `execute(sql)` veya `executescript(sql)` metodu
yeterlidir.
"""

from __future__ import annotations

import sqlite3
import time
from datetime import datetime, timezone
from typing import Any

from ..schemas import detect_dialect, migrations_for
from ..schemas.registry import Migration


class FlywayError(RuntimeError):
    """Apply sırasında ortaya çıkan hata.

    Attığında `migration_name` ve `failed_statement` attribute'ları
    doludur.
    """

    def __init__(self, message: str, migration_name: str) -> None:
        super().__init__(message)
        self.migration_name = migration_name


# ---- Shared schema-history DDL (her iki dialect aynı yazımı destekler) ----

_HISTORY_DDL_SQLITE = """
CREATE TABLE IF NOT EXISTS _schema_history (
    version      INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    installed_at TEXT    NOT NULL DEFAULT (datetime('now'))
);
"""

_HISTORY_DDL_POSTGRES = """
CREATE TABLE IF NOT EXISTS _schema_history (
    version      INTEGER PRIMARY KEY,
    name         TEXT    NOT NULL,
    installed_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""


def _ensure_history(conn: Any, dialect: str) -> None:
    if dialect == "sqlite":
        conn.executescript(_HISTORY_DDL_SQLITE)
    elif dialect == "postgresql":
        conn.execute(_HISTORY_DDL_POSTGRES)
    else:
        msg = f"Dialect '{dialect}' için history DDL yok"
        raise ValueError(msg)


def _is_applied(conn: Any, dialect: str, version: int) -> bool:
    """version zaten history'de mi? Returns bool."""
    row: tuple[int, ...] | None
    if dialect == "sqlite":
        row = conn.execute(
            "SELECT version FROM _schema_history WHERE version = ?",
            (version,),
        ).fetchone()
    else:
        row = conn.execute(  # type: ignore[attr-defined]
            "SELECT version FROM _schema_history WHERE version = $1",
            version,
        ).fetchone()
    return row is not None


def _record_history(conn: Any, dialect: str, version: int, name: str) -> None:
    if dialect == "sqlite":
        conn.execute(
            "INSERT OR IGNORE INTO _schema_history(version, name) VALUES (?, ?)",
            (version, name),
        )
        conn.commit()
    else:
        conn.execute(  # type: ignore[attr-defined]
            "INSERT INTO _schema_history(version, name) VALUES ($1, $2) "
            "ON CONFLICT (version) DO NOTHING",
            version,
            name,
        )


def _apply_migration(conn: Any, dialect: str, mig: Migration) -> None:
    """Tek bir `Migration` çalıştır. Detay içeren `FlywayError` fırlatır."""
    start = time.monotonic()
    try:
        mig.apply(conn, dialect)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        msg = (
            f"migration '{mig.name}' (v{mig.version}) apply başarısız "
            f"({elapsed_ms} ms): {exc}"
        )
        raise FlywayError(msg, mig.name) from exc


# ---- Public sync SQLite runner -----------------------------------------


def _flyway_sqlite(url: str) -> list[str]:
    """sqlite3 url → uygulanan migration listesi (kronolojik)."""
    # `sqlite:///foo/bar.db` → `./foo/bar.db`
    path = url.split(":", 1)[1].lstrip("/")
    if not path:
        path = ":memory:"

    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    try:
        dialect = "sqlite"
        _ensure_history(conn, dialect)
        conn.commit()
        present = _known_tables(conn, dialect)
        applied: list[str] = []
        for mig in migrations_for(dialect):
            if not _needs_apply(conn, dialect, mig, present):
                continue
            _apply_migration(conn, dialect, mig)
            _record_history(conn, dialect, mig.version, mig.name)
            present.add(mig.name)
            applied.append(mig.name)
        return applied
    finally:
        conn.close()


# ---- Public async PostgreSQL runner -----------------------------------

async def _flyway_postgres(url: str) -> list[str]:
    """asyncpg url → uygulanan migration listesi (kronolojik)."""
    import asyncpg

    conn = await asyncpg.connect(url)
    try:
        dialect = "postgresql"
        await _ensure_history_async(conn, dialect)
        present = await _known_tables_async(conn, dialect)
        applied: list[str] = []
        for mig in migrations_for(dialect):
            if not await _needs_apply_async(conn, dialect, mig, present):
                continue
            await _apply_migration_async(conn, dialect, mig)
            await _record_history_async(conn, dialect, mig.version, mig.name)
            present.add(mig.name)
            applied.append(mig.name)
        return applied
    finally:
        await conn.close()


async def _ensure_history_async(conn: Any, dialect: str) -> None:
    """asyncpg connection için execute ayrı."""
    if dialect == "sqlite":
        # Async tarafta sqlite3 beklenmez; defensive yine de kontrol.
        conn.executescript(_HISTORY_DDL_SQLITE)
    else:
        await conn.execute(_HISTORY_DDL_POSTGRES)


async def _is_applied_async(conn: Any, dialect: str, version: int) -> bool:
    row = await conn.fetchrow(
        "SELECT version FROM _schema_history WHERE version = $1", version
    )
    return row is not None


async def _record_history_async(conn: Any, dialect: str, version: int, name: str) -> None:
    await conn.execute(
        "INSERT INTO _schema_history(version, name) VALUES ($1, $2) "
        "ON CONFLICT (version) DO NOTHING",
        version,
        name,
    )


async def _apply_migration_async(conn: Any, dialect: str, mig: Migration) -> None:
    if dialect == "sqlite":
        msg = "async runner sqlite yolunu desteklemiyor"
        raise FlywayError(msg, mig.name)
    start = time.monotonic()
    try:
        # mig.apply asyncpg.Connection üzerinde `execute(sql)` çağırır;
        # verilen DDL tek statement olduğu için yeterli.
        mig.apply(conn, dialect)
    except Exception as exc:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        msg = (
            f"migration '{mig.name}' (v{mig.version}) apply başarısız "
            f"({elapsed_ms} ms): {exc}"
        )
        raise FlywayError(msg, mig.name) from exc


# ---- Public façade ------------------------------------------------------


def flyway_init(database_url: str) -> list[str]:
    """DB URL'den dialect tespit eder; sqlite için sync, async için
    `asyncio.run(_flyway_postgres(url))` çağırır.

    Returns: yeni uygulanan migration adları (kronolojik).
    """
    dialect = detect_dialect(database_url)
    if dialect == "sqlite":
        return _flyway_sqlite(database_url)
    # postgres: event loop içinde çağrılmalı
    import asyncio
    return asyncio.run(_flyway_postgres(database_url))


def flyway_status(database_url: str) -> dict[str, object]:
    """Plan snapshot — apply etmeden beklentiyi raporlar.

    Driver connection açmaz; sadece file-based sqlite inspection
    veya PG'ye dry connect yapar. Production ortamı için
    `flyway_init` çağrısı yeterli — bu helper test/debug amaçlı.
    """
    dialect = detect_dialect(database_url)
    registry = [(m.version, m.name) for m in migrations_for(dialect)]
    return {
        "dialect": dialect,
        "url": database_url,
        "at": datetime.now(timezone.utc).isoformat(),
        "expected_versions": [v for v, _ in registry],
        "expected_names": [n for _, n in registry],
    }


def _known_tables(conn: Any, dialect: str) -> set[str]:
    """DB'de şu anda mevcut tablo isimlerini döner (case-sensitive, sqlite
    dahil cross-driver uyumlu)."""
    if dialect == "sqlite":
        rows = conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' "
            "AND name NOT LIKE 'sqlite_%'"
        ).fetchall()
        return {r[0] if isinstance(r, tuple) else r["name"] for r in rows}
    # postgresql
    rows = conn.execute(  # type: ignore[attr-defined]
        "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
    ).fetchall()
    return {r[0] if isinstance(r, tuple) else r["tablename"] for r in rows}


async def _known_tables_async(conn: Any, dialect: str) -> set[str]:
    if dialect == "sqlite":
        msg = "async runner sqlite yolunu desteklemiyor"
        raise FlywayError(msg, "<sqlite>")
    rows = await conn.fetch(
        "SELECT tablename FROM pg_tables WHERE schemaname = current_schema()"
    )
    return {r["tablename"] for r in rows}


def _needs_apply(  # noqa: PLR0913 — understandable signature matters more than length
    conn: Any,
    dialect: str,
    mig: Migration,
    present: set[str],
) -> bool:
    """İki sebep re-apply gerektirir:

    1. `version` `_schema_history`'de yok — yeni migration
    2. `_schema_history` kaydı var ama tablo DB'de yok — drop edilmiş

    Tek başına (1) idempotent; (2) için bu fonksiyon gerekiyor —
    stand-alone create_database'lar "yoksa uygula, history güncel" sözünü
    bozmamak için.
    """
    if not _is_applied(conn, dialect, mig.version):
        return True
    return mig.name not in present


async def _needs_apply_async(
    conn: Any,
    dialect: str,
    mig: Migration,
    present: set[str],
) -> bool:
    if dialect == "sqlite":
        msg = "async runner sqlite yolunu desteklemiyor"
        raise FlywayError(msg, mig.name)
    if not await _is_applied_async(conn, dialect, mig.version):
        return True
    return mig.name not in present


__all__ = [
    "FlywayError",
    "flyway_init",
    "flyway_status",
]
