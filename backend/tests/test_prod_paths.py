"""Production paths that previously had no direct tests.

Catalog parsing, LiteLLM target selection, approval/result mail,
action tokens, login lockout, and worker retry delay.
"""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from uuid import uuid4

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from backend.src.api.auth import rate_limit
from backend.src.api.routes import mcp_catalog
from backend.src.api.utils.action_tokens import (
    compact_of,
    hash_compact_token,
    issue_tokens_for_request,
)
from backend.src.api.utils.hmac_signer import HmacTokenSigner
from backend.src.core.litellm import mcp_catalog as catalog
from backend.src.core.litellm.target import litellm_env_for_ortam, resolve_litellm_http
from backend.src.core.mailing.approval_inputs import litellm_approval_inputs, mcp_approval_inputs
from backend.src.core.mailing.mailer import render_template
from backend.src.core.mailing.result_inputs import (
    litellm_result_inputs,
    litellm_revision_diff_html,
    mcp_result_inputs,
    result_template_name,
)
from backend.src.domain.enums import is_terminal
from backend.src.worker.dispatcher import _exp_backoff_seconds

REQUEST = {
    "genai_orion_panel_ticket_id": "HD-1",
    "genai_orion_panel_ticket_url": "https://orion.example/HD-1",
    "requester_name": "Ada <script>",
    "requester_email": "ada@allianz.com.tr",
    "department_name": "GENAI",
    "environment": "PROD",
    "purpose_text": "RAG",
    "models": ["allianz-text", "allianz-vision"],
    "max_concurrent_requests": 4,
    "key_alias": "ALZ-BRYSL-KEY",
    "created_at": "2026-11-12T00:00:00Z",
    "version": 2,
    "status": "completed",
    "response_window": "realtime",
    "usage_frequency": "100_1000",
    "mcp_server_slug": "search",
    "mcp_tool_names": ["query"],
    "all_tools": False,
    "reject_reason": "no <b>reason</b>",
}


def test_test_environment_uses_dev_litellm_and_ignores_mcp_gateway(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL_DEV", "https://dev.litellm")
    monkeypatch.setenv("LITELLM_MASTER_KEY_DEV", "dev-key")
    monkeypatch.setenv("MCP_GATEWAY_BASE_URL_TEST", "https://gateway")
    monkeypatch.setenv("MCP_GATEWAY_ADMIN_CREDENTIAL_TEST", "gateway-key")
    assert litellm_env_for_ortam("TEST") == "DEV"
    assert resolve_litellm_http("TEST", kind="litellm") == ("https://dev.litellm", "dev-key")
    assert resolve_litellm_http("TEST", kind="mcp") == ("https://gateway", "gateway-key")


def test_litellm_target_falls_back_when_suffixed_value_missing(monkeypatch):
    monkeypatch.delenv("LITELLM_BASE_URL_PROD", raising=False)
    monkeypatch.delenv("LITELLM_MASTER_KEY_PROD", raising=False)
    monkeypatch.setenv("LITELLM_BASE_URL", "https://fallback/")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "fallback-key")
    assert resolve_litellm_http("PROD", kind="litellm") == ("https://fallback", "fallback-key")


def test_terminal_status():
    assert is_terminal("completed")
    assert is_terminal("rejected")
    assert is_terminal("failed")
    assert not is_terminal("waiting_approval")
    assert not is_terminal("not-a-status")


def test_retry_delay_doubles_by_attempt():
    assert [_exp_backoff_seconds(n) for n in (0, 1, 2, 3)] == [60, 60, 120, 240]


def test_login_lockout_is_case_insensitive_and_success_clears(monkeypatch):
    monkeypatch.setattr(rate_limit, "get_settings", lambda: SimpleNamespace(
        login_rate_limit_window_seconds=60,
        login_rate_limit_max_attempts=2,
        login_rate_limit_lockout_seconds=30,
    ))
    limiter = rate_limit.LoginRateLimiter()
    assert limiter.check("10.1.1.1", "Ada") == (True, 0)
    limiter.record_failure("10.1.1.1", "ada")
    assert limiter.check("10.1.1.1", "ADA") == (True, 0)
    limiter.record_failure("10.1.1.1", "ADA")
    allowed, retry_after = limiter.check("10.1.1.1", "ada")
    assert allowed is False
    assert retry_after == 30
    limiter.record_success("10.1.1.1", "ada")
    assert limiter.check("10.1.1.1", "ada") == (True, 0)


def test_action_tokens_follow_request_type():
    signer = HmacTokenSigner("test-secret")
    request_id = uuid4()
    litellm = issue_tokens_for_request(
        signer, request_id=request_id, request_type="litellm_key", ttl_hours=72,
    )
    mcp = issue_tokens_for_request(
        signer, request_id=request_id, request_type="mcp_key", ttl_hours=72,
    )
    assert {row.action for row in litellm} == {"approve", "revise", "reject"}
    assert {row.action for row in mcp} == {"approve", "reject"}
    assert issue_tokens_for_request(
        signer, request_id=request_id, request_type="unknown", ttl_hours=1,
    ) == []
    for row in litellm:
        compact = compact_of(row)
        assert hash_compact_token(compact) == row.token_hash
        assert signer.verify(compact)["action"] == row.action
        assert signer.verify(compact)["request_id"] == str(request_id)


def test_approval_mail_escapes_requester_and_hides_revise_for_mcp():
    litellm = litellm_approval_inputs(
        REQUEST, recipient="approver@allianz.com.tr",
        approve_link="https://panel/approve", reject_link="https://panel/reject",
        revise_link="https://panel/revise",
    )
    rendered = render_template("litellm_key_approval", **litellm)
    assert "Ada &lt;script&gt;" in rendered
    assert "<script>" not in rendered
    assert "https://panel/revise" in rendered

    mcp = mcp_approval_inputs(
        REQUEST, recipient="approver@allianz.com.tr",
        approve_link="https://panel/approve", reject_link="https://panel/reject",
    )
    assert "revise_link" not in mcp
    mcp_rendered = render_template("mcp_key_approval", **{
        key: value for key, value in mcp.items() if key != "_unescaped"
    })
    assert "Revize" not in mcp_rendered
    assert "query" in mcp_rendered
    assert "<script>" not in mcp_rendered


def test_result_mail_shows_revision_and_withholds_empty_key():
    diff = litellm_revision_diff_html(
        {"models": ["allianz-text"], "max_concurrent_requests": 2,
         "response_window": "realtime", "usage_frequency": "0_10"},
        {"models": ["allianz-text", "allianz-vision"], "max_concurrent_requests": 4,
         "response_window": "realtime", "usage_frequency": "100_1000"},
    )
    assert "allianz-text → allianz-text, allianz-vision" in diff
    assert 'class="changed"' in diff
    assert "Gerçek zamanlı →" not in diff

    result = litellm_result_inputs(
        REQUEST, api_key="sk-secret", revision_before={"models": ["old"]},
    )
    assert result["approved"] is True
    assert result["was_revised"] is True
    assert result["outcome_label"] == "tamamlandı"
    rendered = render_template("litellm_key_result", **{
        key: value for key, value in result.items() if key != "_unescaped"
    })
    assert "sk-secret" in rendered
    assert "Red sebebi" not in rendered

    rejected = mcp_result_inputs({**REQUEST, "status": "rejected"}, api_key="")
    assert rejected["rejected"] is True
    assert rejected["api_key"] == ""
    rejected_html = render_template("mcp_key_result", **rejected)
    assert "reddedildi" in rejected_html
    assert "no &lt;b&gt;reason&lt;/b&gt;" in rejected_html
    assert "sk-secret" not in rejected_html
    assert result_template_name("litellm_key") == "litellm_key_result"
    assert result_template_name("mcp_key") == "mcp_key_result"


def _catalog_client(monkeypatch, responses):
    monkeypatch.setenv("LITELLM_BASE_URL_DEV", "https://litellm.test")
    monkeypatch.setenv("LITELLM_MASTER_KEY_DEV", "catalog-secret")
    for name in (
        "MCP_GATEWAY_BASE_URL_TEST", "MCP_GATEWAY_BASE_URL",
        "MCP_GATEWAY_ADMIN_CREDENTIAL_TEST", "MCP_GATEWAY_ADMIN_CREDENTIAL",
    ):
        monkeypatch.delenv(name, raising=False)

    def handle(request):
        assert request.headers["Authorization"] == "Bearer catalog-secret"
        return responses(request)

    constructor = httpx.AsyncClient
    monkeypatch.setattr(
        catalog.httpx, "AsyncClient",
        lambda **kwargs: constructor(transport=httpx.MockTransport(handle), **kwargs),
    )


def test_catalog_unwraps_servers_and_strips_tool_prefix(monkeypatch):
    def responses(request):
        if request.url.path == "/v1/mcp/server":
            return httpx.Response(200, json={"data": [
                {"server_name": "Search", "alias": "search", "server_id": "sid",
                 "allowed_tools": ["fallback"]},
                {"alias": "search"},
            ]})
        if request.url.path == "/mcp-rest/tools/list":
            return httpx.Response(200, json={"tools": [
                {"name": "search-query", "mcp_info": {"server_name": "Search"}},
            ]})
        raise AssertionError(request.url.path)

    _catalog_client(monkeypatch, responses)
    items = asyncio.run(catalog.list_mcp_servers_from_litellm("TEST"))
    assert [(item.server_name, item.tools) for item in items] == [("search", ["query"])]


def test_catalog_uses_allowed_tools_when_tool_list_fails(monkeypatch):
    def responses(request):
        if request.url.path == "/v1/mcp/server":
            return httpx.Response(200, json=[{"server_name": "Search", "allowed_tools": ["fallback"]}])
        return httpx.Response(500, text="catalog-secret")

    _catalog_client(monkeypatch, responses)
    items = asyncio.run(catalog.list_mcp_servers_from_litellm("TEST"))
    assert items[0].tools == ["fallback"]


def test_catalog_auth_failure_hides_upstream_body(monkeypatch):
    def responses(request):
        return httpx.Response(401, text="catalog-secret")

    _catalog_client(monkeypatch, responses)
    with pytest.raises(catalog.LiteLLMCatalogError) as error:
        asyncio.run(catalog.list_mcp_servers_from_litellm("TEST"))
    assert error.value.status == 502
    assert error.value.code == "LITELLM_AUTH"
    assert "catalog-secret" not in error.value.message


def test_catalog_missing_configuration(monkeypatch):
    monkeypatch.setattr(catalog, "resolve_litellm_http", lambda *args, **kwargs: ("", ""))
    with pytest.raises(catalog.LiteLLMCatalogError) as error:
        asyncio.run(catalog.list_mcp_servers_from_litellm("PROD"))
    assert error.value.status == 503
    assert error.value.code == "LITELLM_NOT_CONFIGURED"


def test_catalog_route_rejects_unknown_environment_and_reports_config(monkeypatch):
    app = FastAPI()
    app.include_router(mcp_catalog.router, prefix="/catalog")

    async def missing(ortam):
        raise catalog.LiteLLMCatalogError(503, "LITELLM_NOT_CONFIGURED", "missing")

    monkeypatch.setattr(mcp_catalog, "list_mcp_servers_from_litellm", missing)
    client = TestClient(app)
    assert client.get("/catalog/mcp-servers?ortam=STG").status_code == 422
    failed = client.get("/catalog/mcp-servers?ortam=PROD")
    assert failed.status_code == 503
    assert failed.json()["error_code"] == "LITELLM_NOT_CONFIGURED"
    assert "catalog-secret" not in failed.text
