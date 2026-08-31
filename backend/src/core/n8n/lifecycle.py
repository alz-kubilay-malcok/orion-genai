"""Approve / revise / reject sonrası n8n webhook POST.

n8n 2.31 webhook gövdesi ``$json.body`` altında durur. Auth yok, şema yok.
URL boşsa ``None`` döner (local/test no-op).

Wire contract::

    {"jira_issue_key": "ITSM-12345", "status": "approved"}
    {"jira_issue_key": "ITSM-12345", "status": "rejected"}

``status`` yalnız ``approved`` | ``rejected``. Revise+approve → ``approved``.

Tetik: sonuç maili (key mail / red mail) gittikten sonra; onay tıklanınca değil.
"""

from __future__ import annotations

import logging
import os

import httpx

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT_SECONDS = 15.0

LIFECYCLE_APPROVED = "approved"
LIFECYCLE_REJECTED = "rejected"
_STATUS_BY_ACTION = {
    "approve": LIFECYCLE_APPROVED,
    "revise": LIFECYCLE_APPROVED,
    "reject": LIFECYCLE_REJECTED,
    LIFECYCLE_APPROVED: LIFECYCLE_APPROVED,
    LIFECYCLE_REJECTED: LIFECYCLE_REJECTED,
}


def lifecycle_status(action: str) -> str:
    """Panel action → n8n ``status`` (approved | rejected)."""
    key = (action or "").strip().casefold()
    status = _STATUS_BY_ACTION.get(key)
    if status is None:
        raise ValueError(f"desteklenmeyen lifecycle action: {action!r}")
    return status


def n8n_action_for_result_status(status: str) -> str | None:
    """Request status → outbox action. Sonuç maili olmayan durumlar None."""
    key = (status or "").strip().casefold()
    if key == "rejected":
        return "reject"
    if key == "completed":
        return "approve"
    return None


def build_lifecycle_body(*, jira_issue_key: str, action: str) -> dict[str, str]:
    """n8n webhook JSON. Ticket id Jira key formatında (ör. ITSM-12345)."""
    ticket = (jira_issue_key or "").strip()
    if not ticket:
        raise ValueError("jira_issue_key boş")
    return {
        "jira_issue_key": ticket,
        "status": lifecycle_status(action),
    }


def webhook_url() -> str:
    return (os.getenv("N8N_LIFECYCLE_WEBHOOK_URL") or "").strip()


def _tls_verify() -> bool:
    raw = (os.getenv("N8N_LIFECYCLE_TLS_VERIFY") or "false").strip().lower()
    return raw in {"1", "true", "yes", "on"}


def _timeout_seconds() -> float:
    raw = (os.getenv("N8N_LIFECYCLE_TIMEOUT_SECONDS") or "").strip()
    if not raw:
        return DEFAULT_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError:
        return DEFAULT_TIMEOUT_SECONDS
    return value if value > 0 else DEFAULT_TIMEOUT_SECONDS


async def post_n8n_lifecycle(*, jira_issue_key: str, action: str) -> httpx.Response | None:
    """Ticket id + approved/rejected'i n8n lifecycle webhook'una POST et. URL yoksa None."""
    url = webhook_url()
    if not url:
        logger.warning("n8n lifecycle webhook URL boş; atlandı")
        return None

    body = build_lifecycle_body(jira_issue_key=jira_issue_key, action=action)
    timeout = _timeout_seconds()
    verify = _tls_verify()
    async with httpx.AsyncClient(
        timeout=timeout, verify=verify, trust_env=False,
    ) as client:
        response = await client.post(
            url,
            headers={"Content-Type": "application/json"},
            json=body,
        )
    logger.info(
        "n8n lifecycle POST %s → HTTP %s ticket=%s status=%s",
        url, response.status_code, body["jira_issue_key"], body["status"],
    )
    return response


__all__ = [
    "LIFECYCLE_APPROVED",
    "LIFECYCLE_REJECTED",
    "build_lifecycle_body",
    "lifecycle_status",
    "n8n_action_for_result_status",
    "post_n8n_lifecycle",
    "webhook_url",
]
