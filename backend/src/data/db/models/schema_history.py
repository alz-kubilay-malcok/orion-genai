"""SchemaHistory ORM model — `flyway.py` `_schema_history` mirror.

DB'de tablo `_schema_history`, ORM'de `schema_history` adıyla; tablo
adını `__tablename__` ile bağlıyoruz. PK DB'deki gibi `version`
kolonudur, autoincrement değil.
"""

from __future__ import annotations

from sqlalchemy import Integer, String, text
from sqlalchemy.orm import Mapped, mapped_column

from ..base import Base
from ..types import UtcDateTime


class SchemaHistory(Base):
    __tablename__ = "_schema_history"

    version: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(64), nullable=False)
    installed_at: Mapped[UtcDateTime] = mapped_column(
        UtcDateTime, nullable=False, server_default=text("now()"),
    )


__all__ = ["SchemaHistory"]
