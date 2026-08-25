"""ORM model registry — `Base.metadata`'ya modelleri implicit mount eder."""

from ..base import Base

# Import each model so SQLAlchemy metadata registers it.
from .approval_tokens import ApprovalToken  # noqa: F401
from .audit_events import AuditEvent  # noqa: F401
from .audit_log import AuditLog  # noqa: F401 — append-only LDAP mapping audit
from .config_approvers import ConfigApprover  # noqa: F401
from .config_mcp_servers import ConfigMCPServer  # noqa: F401
from .config_mcp_tools import ConfigMCPTool  # noqa: F401
from .mail_jwt_tokens import MailJwtToken  # noqa: F401
from .mail_messages import MailMessage  # noqa: F401
from .organizations import Namespace, Organization  # noqa: F401 — v16
from .outbox_jobs import OutboxJob  # noqa: F401
from .request_revisions import RequestRevision  # noqa: F401
from .requests import Request  # noqa: F401
from .role_bindings import (  # noqa: F401 — v16
    LdapGroupMapping,
    OrgMembership,
    RoleBinding,
    RoleBindingSource,
)
from .roles import Permission, Role, RolePermission  # noqa: F401
from .schema_history import SchemaHistory  # noqa: F401
from .secrets import Secret  # noqa: F401
from .users import User  # noqa: F401
from .worker_heartbeats import WorkerHeartbeat  # noqa: F401

__all__ = [
    "ApprovalToken",
    "AuditEvent",
    "AuditLog",
    "Base",
    "ConfigApprover",
    "ConfigMCPServer",
    "ConfigMCPTool",
    "MailJwtToken",
    "MailMessage",
    "Namespace",
    "Organization",
    "OutboxJob",
    "Request",
    "RequestRevision",
    "Role",
    "RoleBinding",
    "RoleBindingSource",
    "RolePermission",
    "Permission",
    "SchemaHistory",
    "Secret",
    "User",
    "WorkerHeartbeat",
]
