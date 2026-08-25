"""Backend `data.db` — SQLAlchemy ORM + repository katmanı.

Üst sıradaki `data.schemas.*` DDL ve `data.scripts.flyway` tabloları
`create_all` / `CREATE TABLE IF NOT EXISTS` ile apply eder; ORM katmanı
burada yalnızca **declarative mapping** ve repository için var.

`DB_MODE` env değerine göre (`sqlite`|`pg`) URL seçimi ve driver
seçimi `db.config` tarafından yapılır; repo katmanı iki dialekte de
aynı API sağlar.
"""

from .config import DBConfig
from .engine import build_async_engine, build_session_factory, dispose_engine, get_engine
from .db_init import BuiltSession, adb_init, db_init
# `Repository` import re-export'ı modelleri mount etmeden exclude edildi:
#   applications katmanı `Repository` + concrete repo'ları ayrıca
#   `data.db.repository` modülünden alır.
from .repository import (
    OutboxRepository,
    Repository,
    RequestRepository,
    WorkerHeartbeatRepository,
)
from . import repository

__all__ = [
    "BuiltSession",
    "DBConfig",
    "OutboxRepository",
    "Repository",
    "RequestRepository",
    "WorkerHeartbeatRepository",
    "adb_init",
    "build_async_engine",
    "build_session_factory",
    "db_init",
    "dispose_engine",
    "get_engine",
    "repository",
]
