"""Cross-dialect ORM tip katmanı.

Tek bir SQLAlchemy `Mapped[...]` annotation iki dialect altında da doğru
kolon tipine maplenir:

- `Uuid`           PG → native UUID, SQLite → CHAR(36) (native UUID yok).
- `JsonEncodedList` PG → ARRAY(TEXT), SQLite → JSON-encoded TEXT
                        (CHECK yerine runtime invariant).
- `JsonEncodedDict` PG → JSONB, SQLite → JSON-encoded TEXT
                        (serbest structural payload alanları için).
- `UtcDateTime`    PG → TIMESTAMPTZ, SQLite → tz-suz ISO-8601 TEXT.

DDL'ler zaten `_schema_history` book-keeping ile doğru tabloyu
uyguladığı için `Base.metadata.create_all(...)` yalnızca **idempotent**
deneme için var (`Base.metadata.tables` güncel değilse yeni kolonlar
eklenir). Production yolu `data.scripts.flyway.flyway_init`.
"""

from __future__ import annotations

import json
import uuid
from datetime import datetime
from typing import Optional

from sqlalchemy import DateTime, String, Text, TypeDecorator
from sqlalchemy.dialects import postgresql


class Uuid(TypeDecorator):
    """UUID alan — PG native, SQLite CHAR(36)."""

    impl = String(36)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                postgresql.UUID(as_uuid=True)
            )
        return dialect.type_descriptor(String(36))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            if isinstance(value, uuid.UUID):
                return value
            return uuid.UUID(str(value))
        if isinstance(value, uuid.UUID):
            return str(value)
        return str(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if isinstance(value, uuid.UUID):
            return value
        return uuid.UUID(str(value))


class JsonEncodedList(TypeDecorator):
    """`list[str]` PG ARRAY(TEXT) → SQLite JSON-encoded TEXT (örn. `["a","b"]`)."""

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.ARRAY(Text))
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        return json.dumps(list(value), ensure_ascii=False)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return list(value)
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return []
            return list(parsed) if isinstance(parsed, list) else []
        return list(value) if isinstance(value, (list, tuple)) else []


class JsonEncodedDict(TypeDecorator):
    """``dict[str, Any]`` — PG JSONB, SQLite JSON-encoded TEXT.

    ``audit_log.payload`` ve benzeri serbest structural payload alanları
    için kullanılır. ``JsonEncodedList`` ile aynı pattern ama dict şemasını
    varsayar; bind sırasında ``dict`` → JSON-encoded TEXT, result'ta
    ``str`` → ``dict`` parse edilir.
    """

    impl = Text
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(postgresql.JSONB())
        return dialect.type_descriptor(Text())

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        # PG: JSONB native olarak dict alır; sqlite: dumped TEXT.
        if dialect.name == "postgresql":
            return value
        return json.dumps(value, ensure_ascii=False, default=str)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            # psycopg/asyncpg JSONB otomatik deserialize eder; biz yine de
            # string gelirse patlamayalım.
            return value if isinstance(value, dict) else (value or {})
        if isinstance(value, str):
            try:
                parsed = json.loads(value)
            except json.JSONDecodeError:
                return {}
            return parsed if isinstance(parsed, dict) else {}
        return value if isinstance(value, dict) else []


class UtcDateTime(TypeDecorator):
    """TZ-aware datetime — PG TIMESTAMPTZ, SQLite tz-suz ISO-8601."""

    impl = DateTime(timezone=False)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                postgresql.TIMESTAMP(timezone=True)
            )
        return dialect.type_descriptor(DateTime(timezone=False))

    @staticmethod
    def _to_utc_naive(value: datetime) -> datetime:
        if value.tzinfo is not None:
            return value.astimezone().replace(tzinfo=None)
        return value

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return self._to_utc_naive(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        return value


class TzOptionalDateTime(TypeDecorator):
    """Nullable TZ-aware datetime — `completed_at` gibi sütunlar için."""

    impl = DateTime(timezone=False)
    cache_ok = True

    def load_dialect_impl(self, dialect):  # type: ignore[override]
        if dialect.name == "postgresql":
            return dialect.type_descriptor(
                postgresql.TIMESTAMP(timezone=True)
            )
        return dialect.type_descriptor(DateTime(timezone=False))

    def process_bind_param(self, value, dialect):  # type: ignore[override]
        if value is None:
            return None
        if dialect.name == "postgresql":
            return value
        return UtcDateTime._to_utc_naive(value)

    def process_result_value(self, value, dialect):  # type: ignore[override]
        return value


__all__ = [
    "Uuid",
    "JsonEncodedList",
    "JsonEncodedDict",
    "UtcDateTime",
    "TzOptionalDateTime",
]


# Re-export için Optional eklentisi (modeller `Optional[str]` kullanır)
_ = Optional
