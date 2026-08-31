"""Worker package init."""

from backend.src.domain.enums import OutboxJobType
from .config import WorkerConfig
from .dependencies import WorkerDependencies
from .dispatcher import OutboxDispatcher, DispatchOutcome
from .errors import PermanentError, RetryHeld, TransientError, WorkerError
from .handlers import (
    OUTBOX_HANDLERS,
    build_handlers,
)
from .runner import WorkerRunner

JOB_TYPE_APPROVAL_MAIL = OutboxJobType.SEND_APPROVAL_MAIL.value
JOB_TYPE_PROVISION_LITELLM = OutboxJobType.PROVISION_LITELLM_KEY.value
JOB_TYPE_PROVISION_MCP = OutboxJobType.PROVISION_MCP_KEY.value
JOB_TYPE_REGISTER_MCP = OutboxJobType.REGISTER_MCP_SERVER.value
JOB_TYPE_SEND_RESULT_MAIL = OutboxJobType.SEND_RESULT_MAIL.value
JOB_TYPE_NOTIFY_N8N_LIFECYCLE = OutboxJobType.NOTIFY_N8N_LIFECYCLE.value

__all__ = [
    "DispatchOutcome",
    "JOB_TYPE_APPROVAL_MAIL",
    "JOB_TYPE_NOTIFY_N8N_LIFECYCLE",
    "JOB_TYPE_PROVISION_LITELLM",
    "JOB_TYPE_PROVISION_MCP",
    "JOB_TYPE_REGISTER_MCP",
    "JOB_TYPE_SEND_RESULT_MAIL",
    "OUTBOX_HANDLERS",
    "OutboxDispatcher",
    "PermanentError",
    "RetryHeld",
    "TransientError",
    "WorkerConfig",
    "WorkerDependencies",
    "WorkerError",
    "WorkerRunner",
    "build_handlers",
]
