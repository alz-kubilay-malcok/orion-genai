"""Worker outbox handler facade.

Handler sözleşmesi: ``async def handle(*, session, payload) -> None``.
``OUTBOX_HANDLERS`` modül-load'da boştur; dispatcher her tick'te
``build_handlers(deps)`` ile tabloyu kurar.
"""

from __future__ import annotations

from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.domain.enums import OutboxJobType

from .dependencies import WorkerDependencies
from .jobs.mail import (
    _handle_send_approval_mail,
    _handle_send_litellm_down_notice,
    handle_send_result_mail,
)
from .jobs.n8n_lifecycle import handle_notify_n8n_lifecycle
from .jobs.provision import _handle_provision_litellm, _handle_provision_mcp
from .jobs.registry import handle_register_mcp

JOB_TYPE_PROVISION_LITELLM = OutboxJobType.PROVISION_LITELLM_KEY.value
JOB_TYPE_PROVISION_MCP = OutboxJobType.PROVISION_MCP_KEY.value
JOB_TYPE_SEND_RESULT_MAIL = OutboxJobType.SEND_RESULT_MAIL.value
JOB_TYPE_REGISTER_MCP = OutboxJobType.REGISTER_MCP_SERVER.value
JOB_TYPE_APPROVAL_MAIL = OutboxJobType.SEND_APPROVAL_MAIL.value
JOB_TYPE_LITELLM_DOWN_NOTICE = OutboxJobType.SEND_LITELLM_DOWN_NOTICE.value
JOB_TYPE_NOTIFY_N8N_LIFECYCLE = OutboxJobType.NOTIFY_N8N_LIFECYCLE.value


def build_handlers(deps: WorkerDependencies) -> dict[str, Callable[..., Awaitable[None]]]:
    """Per-process handler dispatch tablosu — `deps` injection'lı."""
    return {
        JOB_TYPE_PROVISION_LITELLM: _make_provision_litellm_handler(deps),
        JOB_TYPE_PROVISION_MCP: _make_provision_mcp_handler(deps),
        JOB_TYPE_SEND_RESULT_MAIL: _make_send_result_mail_handler(deps),
        JOB_TYPE_REGISTER_MCP: handle_register_mcp,
        JOB_TYPE_APPROVAL_MAIL: _make_send_approval_mail_handler(deps),
        JOB_TYPE_LITELLM_DOWN_NOTICE: _make_send_litellm_down_notice_handler(deps),
        JOB_TYPE_NOTIFY_N8N_LIFECYCLE: handle_notify_n8n_lifecycle,
    }


def _make_provision_litellm_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_provision_litellm(session=session, deps=deps, payload=payload)
    return handler


def _make_provision_mcp_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_provision_mcp(session=session, deps=deps, payload=payload)
    return handler


def _make_send_result_mail_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await handle_send_result_mail(session=session, deps=deps, payload=payload)
    return handler


def _make_send_approval_mail_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_send_approval_mail(session=session, deps=deps, payload=payload)
    return handler


def _make_send_litellm_down_notice_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_send_litellm_down_notice(
            session=session, deps=deps, payload=payload,
        )
    return handler


OUTBOX_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {}

__all__ = [
    "JOB_TYPE_APPROVAL_MAIL",
    "JOB_TYPE_LITELLM_DOWN_NOTICE",
    "JOB_TYPE_NOTIFY_N8N_LIFECYCLE",
    "JOB_TYPE_PROVISION_LITELLM",
    "JOB_TYPE_PROVISION_MCP",
    "JOB_TYPE_REGISTER_MCP",
    "JOB_TYPE_SEND_RESULT_MAIL",
    "OUTBOX_HANDLERS",
    "build_handlers",
    "handle_notify_n8n_lifecycle",
    "handle_register_mcp",
    "handle_send_result_mail",
]
