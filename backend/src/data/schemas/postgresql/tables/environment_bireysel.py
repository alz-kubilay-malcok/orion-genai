"""v18 — `environment` enum'una `BIREYSEL` (LiteLLM bireysel anahtar talebi).

Orion formu `ortam=BIREYSEL` gönderiyor; enum'da yoksa `requests` INSERT'i
`invalid input value for enum environment` ile patlıyordu.
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
ALTER TYPE environment ADD VALUE IF NOT EXISTS 'BIREYSEL';
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


environment_bireysel_migration = Migration(
    version=18, name="environment_bireysel", apply=apply,
)
