import asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch

import httpx
import pytest

from backend.src.core.n8n.lifecycle import (
    build_lifecycle_body,
    n8n_action_for_result_status,
    post_n8n_lifecycle,
)
from backend.src.domain.enums import OutboxJobType
from backend.src.worker.errors import PermanentError, RetryHeld
from backend.src.worker.jobs.n8n_lifecycle import (
    enqueue_n8n_after_result_mail,
    handle_notify_n8n_lifecycle,
)


def test_build_lifecycle_body_approved():
    assert build_lifecycle_body(jira_issue_key="ITSM-12345", action="approve") == {
        "jira_issue_key": "ITSM-12345",
        "status": "approved",
    }


def test_build_lifecycle_body_revise_is_approved():
    assert build_lifecycle_body(jira_issue_key="ITSM-12345", action="revise") == {
        "jira_issue_key": "ITSM-12345",
        "status": "approved",
    }


def test_build_lifecycle_body_rejected():
    body = build_lifecycle_body(jira_issue_key="  ITSM-99  ", action=" reject ")
    assert body == {"jira_issue_key": "ITSM-99", "status": "rejected"}


def test_build_lifecycle_body_empty():
    with pytest.raises(ValueError, match="boş"):
        build_lifecycle_body(jira_issue_key="  ", action="approve")


def test_build_lifecycle_body_unknown_action():
    with pytest.raises(ValueError, match="desteklenmeyen"):
        build_lifecycle_body(jira_issue_key="ITSM-1", action="maybe")


def test_notify_job_type_value():
    assert OutboxJobType.NOTIFY_N8N_LIFECYCLE.value == "notify:n8n_lifecycle"


def test_n8n_action_for_result_status():
    assert n8n_action_for_result_status("completed") == "approve"
    assert n8n_action_for_result_status("rejected") == "reject"
    assert n8n_action_for_result_status("provisioning") is None
    assert n8n_action_for_result_status("failed") is None


def test_enqueue_after_result_mail_skips_non_jira_type():
    async def _case():
        await enqueue_n8n_after_result_mail(
            MagicMock(),
            request_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
            request={
                "request_type": "chatbot_support",
                "status": "completed",
                "genai_orion_panel_ticket_id": "ITSM-1",
            },
        )

    _run(_case())


def test_enqueue_after_result_mail_completed():
    async def _case():
        with patch(
            "backend.src.worker.jobs.n8n_lifecycle.enqueue_notify_n8n_lifecycle",
            new=AsyncMock(),
        ) as enqueue:
            await enqueue_n8n_after_result_mail(
                MagicMock(),
                request_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                request={
                    "request_type": "litellm_key",
                    "status": "completed",
                    "genai_orion_panel_ticket_id": "ITSM-12345",
                },
            )
            enqueue.assert_awaited_once()
            kwargs = enqueue.await_args.kwargs
            assert kwargs["action"] == "approve"
            assert kwargs["ticket_id"] == "ITSM-12345"

    _run(_case())


def test_enqueue_after_result_mail_rejected():
    async def _case():
        with patch(
            "backend.src.worker.jobs.n8n_lifecycle.enqueue_notify_n8n_lifecycle",
            new=AsyncMock(),
        ) as enqueue:
            await enqueue_n8n_after_result_mail(
                MagicMock(),
                request_id=uuid.UUID("00000000-0000-0000-0000-000000000001"),
                request={
                    "request_type": "mcp_key",
                    "status": "rejected",
                    "genai_orion_panel_ticket_id": "ITSM-9",
                },
            )
            assert enqueue.await_args.kwargs["action"] == "reject"

    _run(_case())


def _run(coro):
    return asyncio.run(coro)


def test_post_skips_when_url_empty(monkeypatch):
    monkeypatch.delenv("N8N_LIFECYCLE_WEBHOOK_URL", raising=False)
    assert _run(post_n8n_lifecycle(jira_issue_key="ITSM-1", action="approve")) is None


def test_post_sends_json(monkeypatch):
    monkeypatch.setenv(
        "N8N_LIFECYCLE_WEBHOOK_URL",
        "https://int-n8n.allianz-tr.local/webhook/genai-approve",
    )
    response = httpx.Response(200, text="ok")
    mock_client = MagicMock()
    mock_client.post = AsyncMock(return_value=response)
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=None)

    with patch("httpx.AsyncClient", return_value=mock_client):
        out = _run(post_n8n_lifecycle(jira_issue_key="ITSM-12345", action="revise"))

    assert out is response
    mock_client.post.assert_awaited_once()
    args, kwargs = mock_client.post.await_args
    assert args[0] == "https://int-n8n.allianz-tr.local/webhook/genai-approve"
    assert kwargs["json"] == {
        "jira_issue_key": "ITSM-12345",
        "status": "approved",
    }


def test_handler_retry_on_503():
    request = {"genai_orion_panel_ticket_id": "ITSM-12345"}
    response = httpx.Response(503, text="busy")

    async def _case():
        with (
            patch(
                "backend.src.worker.jobs.n8n_lifecycle._load_request",
                new=AsyncMock(return_value=request),
            ),
            patch(
                "backend.src.worker.jobs.n8n_lifecycle.post_n8n_lifecycle",
                new=AsyncMock(return_value=response),
            ),
        ):
            await handle_notify_n8n_lifecycle(
                session=MagicMock(),
                payload={
                    "request_id": "00000000-0000-0000-0000-000000000001",
                    "action": "approve",
                },
            )

    with pytest.raises(RetryHeld, match="503"):
        _run(_case())


def test_handler_permanent_on_400():
    request = {"genai_orion_panel_ticket_id": "ITSM-12345"}
    response = httpx.Response(400, text="bad")

    async def _case():
        with (
            patch(
                "backend.src.worker.jobs.n8n_lifecycle._load_request",
                new=AsyncMock(return_value=request),
            ),
            patch(
                "backend.src.worker.jobs.n8n_lifecycle.post_n8n_lifecycle",
                new=AsyncMock(return_value=response),
            ),
        ):
            await handle_notify_n8n_lifecycle(
                session=MagicMock(),
                payload={
                    "request_id": "00000000-0000-0000-0000-000000000001",
                    "action": "reject",
                },
            )

    with pytest.raises(PermanentError, match="400"):
        _run(_case())


def test_handler_retry_on_connect_error():
    request = {"genai_orion_panel_ticket_id": "ITSM-12345"}

    async def _case():
        with (
            patch(
                "backend.src.worker.jobs.n8n_lifecycle._load_request",
                new=AsyncMock(return_value=request),
            ),
            patch(
                "backend.src.worker.jobs.n8n_lifecycle.post_n8n_lifecycle",
                new=AsyncMock(side_effect=httpx.ConnectError("down")),
            ),
        ):
            await handle_notify_n8n_lifecycle(
                session=MagicMock(),
                payload={
                    "request_id": "00000000-0000-0000-0000-000000000001",
                    "action": "approve",
                },
            )

    with pytest.raises(RetryHeld, match="unavailable"):
        _run(_case())


def test_handler_noop_when_url_empty():
    request = {"genai_orion_panel_ticket_id": "ITSM-12345"}

    async def _case():
        with (
            patch(
                "backend.src.worker.jobs.n8n_lifecycle._load_request",
                new=AsyncMock(return_value=request),
            ),
            patch(
                "backend.src.worker.jobs.n8n_lifecycle.post_n8n_lifecycle",
                new=AsyncMock(return_value=None),
            ),
        ):
            await handle_notify_n8n_lifecycle(
                session=MagicMock(),
                payload={
                    "request_id": "00000000-0000-0000-0000-000000000001",
                    "action": "approve",
                },
            )

    _run(_case())
