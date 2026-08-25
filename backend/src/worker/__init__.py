"""Worker package init."""

from .config import WorkerConfig
from .dependencies import WorkerDependencies
from .dispatcher import OutboxDispatcher, DispatchOutcome
from .errors import PermanentError, RetryHeld, TransientError, WorkerError
from .handlers import (
    OUTBOX_HANDLERS,
    build_handlers,
    JOB_TYPE_APPROVAL_MAIL,
    JOB_TYPE_PROVISION_LITELLM,
    JOB_TYPE_PROVISION_MCP,
    JOB_TYPE_REGISTER_MCP,
    JOB_TYPE_SEND_RESULT_MAIL,
)
from .runner import WorkerRunner

__all__ = [
    "DispatchOutcome",
    "JOB_TYPE_APPROVAL_MAIL",
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
