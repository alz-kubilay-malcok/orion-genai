"""AsyncEngine + session factory — DB_MODE aware.

İki dialect için farklı driver pragmatik seçimleri:

- `postgresql` → `postgresql+asyncpg` (zaten legacy adapters kullanıyor)
- `sqlite`     → `sqlite+aiosqlite`

Sağlanan URL'de driver explicit verilmemişse dialect'e göre otomatik
eklenir. Pool ayarları:
- PG: `pool_size` `DBConfig`'ten; `pool_pre_ping` her durumda açık.
- SQLite: `poolclass=None` (in-process file lock'ı için normalize davranış).
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from .config import DBConfig


def _normalize_url(dialect: str, url: str) -> str:
    """Driver yoksa dialect'in default async driver'ını iliştir."""
    head = url.split(":", 1)[0].lower()
    if dialect == "sqlite":
        if "sqlite" not in head:
            return f"sqlite+aiosqlite:{url}"
        # `sqlite:///foo` → `sqlite+aiosqlite:///foo`
        if "+aiosqlite" not in head:
            return url.replace("sqlite:", "sqlite+aiosqlite:", 1)
        return url
    if dialect == "postgresql":
        if "postgresql" not in head:
            msg = f"PG URL bekleniyor, gelen: {url}"
            raise ValueError(msg)
        if "+asyncpg" in head:
            return url
        return url.replace("postgresql:", "postgresql+asyncpg:", 1)
    msg = f"Bilinmeyen dialect: {dialect}"
    raise ValueError(msg)


def build_async_engine(config: DBConfig) -> AsyncEngine:
    url = _normalize_url(config.dialect, config.url)
    if config.dialect == "sqlite":
        return create_async_engine(url, poolclass=None)
    return create_async_engine(
        url,
        pool_size=config.pool_size,
        pool_pre_ping=True,
    )


def build_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    return async_sessionmaker(
        bind=engine,
        expire_on_commit=False,
        autoflush=False,
        class_=AsyncSession,
    )


# ---- Convenience for tests/dev ----------------------------------------

_cached_engine: Optional[AsyncEngine] = None


async def get_engine() -> AsyncEngine:
    """Default engine (`DBConfig.from_env` + cache)."""
    from .config import DBConfig

    global _cached_engine
    if _cached_engine is None:
        _cached_engine = build_async_engine(DBConfig.from_env())
    return _cached_engine


async def dispose_engine() -> None:
    """Test teardown'ı için cache'lenmiş engine'i kapatır."""
    global _cached_engine
    if _cached_engine is not None:
        await _cached_engine.dispose()
        _cached_engine = None


__all__ = [
    "build_async_engine",
    "build_session_factory",
    "get_engine",
    "dispose_engine",
]
