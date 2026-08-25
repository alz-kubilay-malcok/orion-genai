"""Approval-mail placeholder sözleşmesi.

Şablonlar `string.Template` + `#if key` kullanır; bu modül worker'ın
`send_mail(..., inputs=...)` sözlüğünü tip olarak sabitler.

LiteLLM: Onayla / Revize et / Reddet (`revise_link` zorunlu).
MCP key / registry: Onayla / Reddet — `revise_link` yok (ADR-011).
"""

from __future__ import annotations

from typing import Mapping, TypedDict


class LitellmApprovalMailInputs(TypedDict):
    """`templates/litellm_key_approval.html` placeholder'ları."""

    approver_name: str
    ticket_id: str
    ticket_url: str
    requester_name: str
    requester_email: str
    department_name: str
    environment: str
    purpose: str
    models: object
    litellm_team_id: object
    max_concurrent_requests: object
    key_alias: object
    created_at: object
    approve_link: str
    reject_link: str
    revise_link: str
    request_version: object
    action_token_ttl_hours: object


class McpApprovalMailInputs(TypedDict, total=False):
    """`templates/mcp_key_approval.html` placeholder'ları. Revize yok."""

    approver_name: str
    ticket_id: str
    ticket_url: str
    requester_name: str
    requester_email: str
    department_name: str
    environment: str
    server_display_name: str
    server_slug: str
    all_tools_label: str
    created_at: object
    approve_link: str
    reject_link: str
    request_version: object
    action_token_ttl_hours: object
    tools_rows: str


def _s(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def litellm_approval_inputs(
    request: Mapping[str, object],
    *,
    recipient: str,
    approve_link: str,
    reject_link: str,
    revise_link: str,
    action_token_ttl_hours: object = 72,
) -> LitellmApprovalMailInputs:
    """LiteLLM onay maili için şablon girdileri.

    `revise_link` HMAC revise-token URL'sidir (`/approvals/{token}`).
    Boş string şablonda Revize butonunu gizler.
    """
    return {
        "approver_name": recipient.split("@")[0],
        "ticket_id": _s(request.get("genai_orion_panel_ticket_id")),
        "ticket_url": _s(request.get("genai_orion_panel_ticket_url")),
        "requester_name": _s(request.get("requester_name")),
        "requester_email": _s(request.get("requester_email")),
        "department_name": _s(request.get("department_name")),
        "environment": _s(request.get("environment")),
        "purpose": _s(request.get("purpose_text") or request.get("purpose_code")),
        "models": request.get("models") or "",
        "litellm_team_id": _s(request.get("litellm_team_id") or request.get("department_name")),
        "max_concurrent_requests": request.get("max_concurrent_requests") or "",
        "key_alias": _s(request.get("key_alias")),
        "created_at": request.get("created_at") or "",
        "approve_link": approve_link,
        "reject_link": reject_link,
        "revise_link": revise_link,
        "request_version": request.get("version") or 0,
        "action_token_ttl_hours": action_token_ttl_hours,
    }


def mcp_approval_inputs(
    request: Mapping[str, object],
    *,
    recipient: str,
    approve_link: str,
    reject_link: str,
    action_token_ttl_hours: object = 72,
) -> dict[str, object]:
    """MCP onay maili — approve/reject only; revise token yok."""
    return {
        "approver_name": recipient.split("@")[0],
        "ticket_id": _s(request.get("genai_orion_panel_ticket_id")),
        "ticket_url": _s(request.get("genai_orion_panel_ticket_url")),
        "requester_name": _s(request.get("requester_name")),
        "requester_email": _s(request.get("requester_email")),
        "department_name": _s(request.get("department_name")),
        "environment": _s(request.get("environment")),
        "server_display_name": _s(
            request.get("mcp_server_display_name") or request.get("server_display_name"),
        ),
        "server_slug": _s(request.get("mcp_server_slug") or request.get("server_slug")),
        "key_alias": _s(request.get("key_alias")),
        "all_tools_label": _s(request.get("all_tools_label")),
        "created_at": request.get("created_at") or "",
        "approve_link": approve_link,
        "reject_link": reject_link,
        "request_version": request.get("version") or 0,
        "action_token_ttl_hours": action_token_ttl_hours,
        "tools_rows": request.get("tools_rows") or "",
        "_unescaped": {"tools_rows"},
    }


__all__ = [
    "LitellmApprovalMailInputs",
    "McpApprovalMailInputs",
    "litellm_approval_inputs",
    "mcp_approval_inputs",
]
