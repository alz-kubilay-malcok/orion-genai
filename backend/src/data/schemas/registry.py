"""Registry — `Migration` value object.

`Migration` sabit ve ufak; tablolar bu tipi döndürür, `flyway_init`
registry listesini sırayla gezerek tenant'ta uygular.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


@dataclass(frozen=True)
class Migration:
    """Tek tablo apply işi.

    - `version`: artan tamsayı (registry sırası)
    - `name`:    stabil isim (örn. `requests`) — `_schema_history` tablosuna
                 yazılır.
    - `apply`:   `(conn, dialect_name)` → None. Connection driver-agnostic
                 olmalı (sqlalchemy `Connection`, `asyncpg.Connection`, veya
                 sqlite3 `Connection` üzerinden `.execute(sql)` ile).
    """

    version: int
    name: str
    apply: Callable[[Any, str], None]


__all__ = ["Migration"]
