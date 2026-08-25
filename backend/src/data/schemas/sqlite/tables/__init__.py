"""SQLite DDL registry.

PG şemasından farklı olarak:
- UUID → CHAR(36) (client tarafı yerleştirilir)
- JSON/JSONB → JSON-encoded TEXT (sqlite 3.38 öncesi için portable)
- ARRAY → JSON-encoded TEXT (örn. `["a","b"]`)
- ENUM → CHECK constraint (apps tarafında invariant)
- application-side invariant `SecretRepository.insert_for_credential_request`
  PG `assert_secret_request_type` trigger'ının yerini alır.
- partial unique indexes (`WHERE is_active`) — SQLite 3.8+ destekler.
- `read_by_user_id` FK'sız (auth strip sonrası `users` tablosu kalktı,
  LDAP gelince tekrar bağlanacak).
"""

from __future__ import annotations

from ...registry import Migration
from .approval_tokens import approval_tokens_migration
from .audit_events import audit_events_migration
from .auth_security import auth_security_migration
from .config_approvers import config_approvers_migration
from .config_mcp_servers import config_mcp_servers_migration
from .config_mcp_tools import config_mcp_tools_migration
from .mail_jwt_tokens import mail_jwt_tokens_migration
from .mail_messages import mail_messages_migration
from .outbox_jobs import outbox_jobs_migration
from .request_revisions import request_revisions_migration
from .requests import requests_migration
from .requests_litellm_team import requests_litellm_team_migration
from .secrets import secrets_migration
from .worker_heartbeats import worker_heartbeats_migration

MIGRATIONS: list[Migration] = [
    requests_migration,
    config_approvers_migration,
    worker_heartbeats_migration,
    config_mcp_servers_migration,
    config_mcp_tools_migration,
    approval_tokens_migration,
    secrets_migration,
    audit_events_migration,
    outbox_jobs_migration,
    mail_messages_migration,
    request_revisions_migration,
    mail_jwt_tokens_migration,
    auth_security_migration,
    requests_litellm_team_migration,
]

__all__ = ["MIGRATIONS"]
