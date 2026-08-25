"""Declarative `Base` — tüm ORM modellerinin sınıf üstü."""

from __future__ import annotations

from sqlalchemy.orm import DeclarativeBase


class Base(DeclarativeBase):
    """SQLAlchemy 2.0 declarative base.

    Modeller `Mapped[...]` annotation'ı ve `mapped_column(...)` ile
    attribute'larını tanımlar. Tablo isimleri legacy migration'larla
    **birebir aynı** tutulur (lowercase, snake_case).
    """


__all__ = ["Base"]
