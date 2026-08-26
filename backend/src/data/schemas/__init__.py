"""DDL registry — URL'den dialect tespit eder, ilgili provider listesini döndürür.

PostgreSQL flyway listesi tek DDL kaynağıdır (compose ``DB_MODE=pg``).
SQLite listesi dondurulmuştur: yeni tablo/kolon yalnız PG flyway + ORM
``create_all`` safety net ile gelir; sqlite kopyasını büyütme.
"""

from __future__ import annotations

from .postgresql import tables as pg_tables
from .registry import Migration
from .sqlite import tables as sqlite_tables


def detect_dialect(url: str) -> str:
    if not url:
        msg = "DATABASE_URL boş; dialect tespit edilemedi"
        raise ValueError(msg)
    head = url.split(":", 1)[0].lower()
    if "postgresql" in head:
        return "postgresql"
    if "sqlite" in head:
        return "sqlite"
    msg = f"Bilinmeyen dialect: {url}"
    raise ValueError(msg)


def migrations_for(dialect: str) -> list[Migration]:
    if dialect == "postgresql":
        return list(pg_tables.MIGRATIONS)
    if dialect == "sqlite":
        return list(sqlite_tables.MIGRATIONS)
    msg = f"Dialect '{dialect}' için registry yok"
    raise ValueError(msg)


__all__ = ["Migration", "detect_dialect", "migrations_for"]
