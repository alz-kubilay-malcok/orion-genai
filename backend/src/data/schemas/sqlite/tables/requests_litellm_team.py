"""v17 — LiteLLM virtual key team assignment (SQLite)."""

from __future__ import annotations

from ...registry import Migration

DDL = """
ALTER TABLE requests ADD COLUMN litellm_team_id TEXT;
"""


def apply(conn: object, dialect_name: str) -> None:
    try:
        conn.execute(DDL)  # type: ignore[attr-defined]
    except Exception as exc:
        # Re-apply: kolon zaten varsa no-op (flyway name tabloda yok).
        if "duplicate column" not in str(exc).lower():
            raise


requests_litellm_team_migration = Migration(
    version=17, name="requests", apply=apply,
)
