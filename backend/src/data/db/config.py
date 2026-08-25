"""DB bağlantı ayarları — `DB_MODE` env'inden otomatik URL seçimi.

Env sözleşmesi (`.env`'deki tek kabul):
- `DB_MODE` : `sqlite` | `pg` (default `sqlite`).
- `SQLITE_ABS_PATH` : SQLite dialect'inde raw path ya da tam URL
  olabilir; URL değilse `sqlite:///` prefix'i ile sarılır. Boşsa
  `./panel.db`.
- `DB_HOST`, `DB_PORT`, `DB_USERNAME`, `DB_PASSWORD`, `DB_NAME` :
  `DB_MODE=pg` iken `postgresql+asyncpg://...` DSN kurmak için
  parça parça gelir. `DB_PORT` opsiyonel değil — boşsa `ValueError`.
- `CONN_POOL_SIZE` : PG pool boyutu (default 5); SQLite path'inde
  uygulanmaz.

`DB_MODE` kabul değerleri büyük/küçük harf duyarsız; tanınmayan
değer `ValueError` fırlatır.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Literal, cast

Dialect = Literal["sqlite", "postgresql"]


def _resolve_sqlite_path(default_sqlite_path: str) -> str:
    """`SQLITE_ABS_PATH` raw path ise URL'e sar; dolu ise geçir."""
    raw = os.getenv("SQLITE_ABS_PATH", "").strip()
    if not raw:
        return f"sqlite:///{default_sqlite_path}"
    if "://" in raw:
        return raw
    return f"sqlite:///{raw}"


def _build_pg_dsn() -> str:
    """Parça parça gelen PG env'lerini asyncpg URL'ine ziple."""
    parts = {
        "host": os.getenv("DB_HOST", "").strip(),
        "port": os.getenv("DB_PORT", "").strip(),
        "user": os.getenv("DB_USERNAME", "").strip(),
        "password": os.getenv("DB_PASSWORD", ""),
        "name": os.getenv("DB_NAME", "").strip(),
    }
    missing = [k for k, v in parts.items() if not v]
    if missing:
        msg = (
            "DB_MODE=pg için şu env'ler eksik: "
            + ", ".join(f"DB_{k.upper()}" for k in missing)
        )
        raise ValueError(msg)
    return (
        f"postgresql+asyncpg://{parts['user']}:{parts['password']}"
        f"@{parts['host']}:{parts['port']}/{parts['name']}"
    )


@dataclass(frozen=True)
class DBConfig:
    """Sabit bağlantı konfigürasyonu; engine kurulumu için tek giriş."""

    url: str
    dialect: Dialect
    pool_size: int

    @classmethod
    def from_env(cls, *, default_sqlite_path: str = "./panel.db") -> "DBConfig":
        raw_mode = os.getenv("DB_MODE", "sqlite").strip().lower()
        if raw_mode not in {"sqlite", "pg", "postgresql"}:
            msg = f"DB_MODE geçersiz: '{raw_mode}' (sqlite|pg bekleniyor)"
            raise ValueError(msg)
        dialect: Dialect = cast(
            Dialect, "postgresql" if raw_mode in {"pg", "postgresql"} else "sqlite"
        )

        if dialect == "sqlite":
            url = _resolve_sqlite_path(default_sqlite_path)
        else:
            url = _build_pg_dsn()

        return cls(
            url=url,
            dialect=dialect,
            pool_size=int(os.getenv("CONN_POOL_SIZE", "5")),
        )


__all__ = ["DBConfig", "Dialect"]
