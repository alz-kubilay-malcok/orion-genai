"""v17 — LiteLLM virtual key team assignment.

`/key/generate` `team_id` alır (`team_alias` `/team/list` ile çözülür).
TPM/RPM artık provision/revise yolu değil; kolonlar durur, yazılmaz.
"""

from __future__ import annotations

from ...registry import Migration

DDL = """
ALTER TABLE requests ADD COLUMN IF NOT EXISTS litellm_team_id TEXT;
"""


def apply(conn: object, dialect_name: str) -> None:
    conn.execute(DDL)  # type: ignore[attr-defined]


requests_litellm_team_migration = Migration(
    version=17, name="requests", apply=apply,
)
