"""DB bootstrap — flyway (DDL authoritatitive) + ORM init.

Sözleşme:
1. `db_init.url_from_env` veya `db_init(DBConfig())` çağrıldığında önce
   `flyway_init` ile eksik tablolar uygulanır (forward-only authoritative).
2. Sonra `Base.metadata` ORM modelleriyle dolu olduğundan
   `Base.metadata.create_all` **no-op** olur: yalnızca hatalı bir
   migration sonrası model/tablo drift'i durumunda yeni kolonları
   eklemek için kullanılır.

Tek satırlık giriş:

    from data.db import db_init
    db_init()  # default: DB_MODE=sqlite, ./panel.db
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Coroutine
from dataclasses import dataclass

from .config import DBConfig
from .engine import build_async_engine, build_session_factory, dispose_engine
from ..schemas.registry import Migration
from ..scripts.flyway import FlywayError, flyway_init

logger = logging.getLogger(__name__)


def _ensure_schema(database_url: str) -> list[str]:
    """DDL apply: return applied migration names (or empty list)."""
    applied = flyway_init(database_url)
    if applied:
        logger.info(
            "flyway_init: %d migration uygulandı: %s",
            len(applied), applied,
        )
    return applied


async def _create_all_safety() -> None:
    """`Base.metadata.tables` içindeki eksikleri tamamla.

    Flyway authoritative olduğu için bu fonksiyon çoğu zaman no-op;
    production'da kullanılmaz, ama yeni development ortamlarında
    `data_science stilinde` hızlı bootstrap için değerlidir.
    """
    from .base import Base
    from .models import (  # noqa: F401 — `Base.metadata` kayıt için
        ApprovalToken, AuditEvent, ConfigApprover, ConfigMCPServer,
        ConfigMCPTool, MailMessage, OutboxJob, Request, RequestRevision,
        SchemaHistory, Secret, WorkerHeartbeat,
    )
    config = DBConfig.from_env()
    engine = build_async_engine(config)
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
    finally:
        await engine.dispose()


def db_init(
    config: DBConfig | None = None,
    *,
    run_create_all: bool = False,
) -> BuiltSession:
    """Sync wrapper: DDL apply + engine + session factory kurar.

    Returns: `BuiltSession` dataclass — `engine` ve `session_factory`
    çağıran tarafından `aclose()` edilebilir.
    """
    cfg = config or DBConfig.from_env()
    applied = _ensure_schema(cfg.url)
    engine = build_async_engine(cfg)
    sf = build_session_factory(engine)
    if run_create_all and not applied:
        try:
            asyncio.run(_create_all_safety())
        except RuntimeError:
            # Event loop zaten çalışıyorsa create_all skip
            logger.debug("db_init.create_all: event loop dolu, atlandı")
    return BuiltSession(engine=engine, session_factory=sf, applied=applied)


async def adb_init(config: DBConfig | None = None) -> BuiltSession:
    """Async alternatif — FastAPI lifespan içinden kullanılır.

    `flyway_init` asyncpg path'i zaten `asyncio.run` kullanıyor; burada
    çağıran loop açıksa onun içinde scheduler ile deriz.
    """
    cfg = config or DBConfig.from_env()
    applied = await asyncio.to_thread(_ensure_schema, cfg.url)
    engine = build_async_engine(cfg)
    sf = build_session_factory(engine)
    return BuiltSession(engine=engine, session_factory=sf, applied=applied)


@dataclass
class BuiltSession:
    """Init çıktısı — engine close için yardımcı."""
    engine: object
    session_factory: object
    applied: list[str]

    async def aclose(self) -> None:
        from .engine import dispose_engine

        # Bu instance'a ait engine'i kapatmak için:
        # 1) dispose engine, 2) global cache reset.
        await self.engine.dispose()  # type: ignore[attr-defined]
        await dispose_engine()


def run_db_bootstrap(database_url: str) -> list[str]:
    """Smoke test / CLI tool için en yalın giriş."""
    try:
        return flyway_init(database_url)
    except FlywayError as exc:
        logger.error(
            "Migration '%s' başarısız: %s",
            exc.migration_name, exc,
        )
        raise


__all__ = [
    "BuiltSession",
    "adb_init",
    "db_init",
    "run_db_bootstrap",
]
