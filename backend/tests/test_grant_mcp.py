import asyncio
import hashlib
import hmac
import json
import logging
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.src.api.main import create_app
from backend.src.api.routes import grant_mcp as route
from backend.src.core.litellm import grant_mcp as service
from backend.src.core.mailing import mailer
from backend.src.core.mailing import mcp_access_granted as notification

BODY = {
    "key_alias": "ALZ-BRYSL-KEY", "mcp_name": "search", "environment": "PROD",
    "recipient_email": "extern.hamza-hacioglu@allianz.com.tr",
}


@pytest.fixture
def provider(monkeypatch):
    monkeypatch.setenv("LITELLM_BASE_URL_PROD", "https://litellm.test")
    monkeypatch.setenv("LITELLM_MASTER_KEY_PROD", "test-master-secret")
    state = {
        "permissions": {
            "object_permission_id": "permission-row-id",
            "mcp_servers": ["existing"],
            "mcp_access_groups": ["group"],
            "mcp_tool_permissions": {"existing": ["read"]},
            "models": [],
            "future_permission": False,
        },
        "calls": [], "updates": [], "verify": True,
        "servers": [{"server_name": "search", "alias": "search-alias", "server_id": "new"}],
        "keys": [{"key_alias": "ALZ-BRYSL-KEY", "token": "private-key-token"}],
        "error_path": None, "invalid_json": False,
        "network_error": False, "empty_update": False, "race_drops": 0,
    }

    def handle(request):
        path = request.url.path
        state["calls"].append(path)
        assert request.headers["Authorization"] == "Bearer test-master-secret"
        if state["network_error"]:
            raise httpx.ConnectError("private-key-token", request=request)
        if path == state["error_path"]:
            return httpx.Response(500, text="private-key-token test-master-secret")
        if state["invalid_json"]:
            return httpx.Response(200, text="not json")
        if path == "/v1/mcp/server":
            return httpx.Response(200, json=state["servers"])
        if path == "/key/list":
            assert request.url.params["key_alias"] == "ALZ-BRYSL-KEY"
            return httpx.Response(200, json={"keys": state["keys"]})
        if path == "/key/info":
            assert request.url.params["key"] == "private-key-token"
            return httpx.Response(200, json={"info": {
                "object_permission": state["permissions"], "models": ["model"],
            }})
        if path == "/key/update":
            payload = json.loads(request.content)
            state["updates"].append(payload)
            if state["verify"]:
                saved = dict(payload["object_permission"])
                if state["race_drops"] > 0:
                    state["race_drops"] -= 1
                    saved["mcp_servers"] = ["existing", "other-writer"]
                state["permissions"] = saved
            if state["empty_update"]:
                return httpx.Response(204)
            return httpx.Response(200, json={"status": "success"})
        raise AssertionError(path)

    constructor = httpx.AsyncClient
    monkeypatch.setattr(
        service.httpx, "AsyncClient",
        lambda **kwargs: constructor(transport=httpx.MockTransport(handle), **kwargs),
    )
    return state


def grant():
    return asyncio.run(service.grant_mcp_access(
        key_alias="ALZ-BRYSL-KEY", mcp_name="search", environment="PROD",
    ))


def test_grant_preserves_permissions_and_verifies(provider):
    result = grant()
    assert result["status"] == "granted"
    assert provider["updates"] == [{"key": "private-key-token", "object_permission": {
        "mcp_servers": ["existing", "new"],
        "mcp_access_groups": ["group"],
        "mcp_tool_permissions": {"existing": ["read"]},
        "models": [], "future_permission": False,
    }}]
    assert provider["calls"][-2:] == ["/key/update", "/key/info"]
    assert "private-key-token" not in json.dumps(result)


def test_already_granted_does_not_update(provider):
    provider["permissions"]["mcp_servers"].append("new")
    assert grant()["status"] == "already_granted"
    assert provider["updates"] == []


def test_verification_failure(provider):
    provider["verify"] = False
    with pytest.raises(service.McpGrantError, match="verification failed"):
        grant()
    assert len(provider["updates"]) == service.MAX_GRANT_ATTEMPTS


def test_concurrent_overwrite_is_merged_on_retry(provider):
    provider["race_drops"] = 1
    result = grant()
    assert result["status"] == "granted"
    assert [item["object_permission"]["mcp_servers"] for item in provider["updates"]] == [
        ["existing", "new"],
        ["existing", "new", "other-writer"],
    ]


@pytest.mark.parametrize("key", ["data", "servers", "mcp_servers", "result"])
def test_wrapped_server_list(provider, key):
    provider["servers"] = {key: provider["servers"]}
    assert grant()["mcp_server_id"] == "new"


def test_unrecognized_server_payload(provider):
    provider["servers"] = {"unexpected": provider["servers"]}
    with pytest.raises(service.McpGrantError, match="invalid MCP server list") as error:
        grant()
    assert error.value.status_code == 502
    assert provider["updates"] == []


@pytest.mark.parametrize("alias", ["BRYSL", "brysel-key", "B\u0130REYSEL", "b\u0131reysel"])
def test_allowed_aliases(alias):
    assert service.has_required_part(alias)


def test_disallowed_alias_never_calls_provider(provider):
    with pytest.raises(service.McpGrantError) as error:
        asyncio.run(service.grant_mcp_access(
            key_alias="OTHER", mcp_name="search", environment="PROD",
        ))
    assert error.value.status_code == 403
    assert provider["calls"] == []


@pytest.mark.parametrize("field", ["servers", "keys"])
def test_missing_or_ambiguous_match(provider, field):
    original = provider[field][0]
    provider[field] = []
    with pytest.raises(service.McpGrantError) as error:
        grant()
    assert error.value.status_code == 404
    provider[field] = [original, original]
    with pytest.raises(service.McpGrantError) as error:
        grant()
    assert error.value.status_code == 409
    assert provider["updates"] == []


def test_upstream_errors_do_not_expose_secrets(provider):
    provider["error_path"] = "/key/update"
    with pytest.raises(service.McpGrantError) as error:
        grant()
    assert error.value.status_code == 502
    assert "private-key-token" not in str(error.value)
    assert "test-master-secret" not in str(error.value)


def test_invalid_json(provider):
    provider["invalid_json"] = True
    with pytest.raises(service.McpGrantError, match="invalid JSON"):
        grant()


def test_network_error_is_safe(provider):
    provider["network_error"] = True
    with pytest.raises(service.McpGrantError) as error:
        grant()
    assert error.value.status_code == 502
    assert "private-key-token" not in str(error.value)


def test_update_can_have_empty_success_body(provider):
    provider["empty_update"] = True
    assert grant()["status"] == "granted"


def test_server_alias(provider):
    result = asyncio.run(service.grant_mcp_access(
        key_alias=BODY["key_alias"], mcp_name="search-alias", environment="PROD",
    ))
    assert result["mcp_server_id"] == "new"


def test_missing_configuration(monkeypatch, provider):
    monkeypatch.setattr(service, "resolve_litellm_http", lambda *args, **kwargs: ("", ""))
    with pytest.raises(service.McpGrantError) as error:
        grant()
    assert error.value.status_code == 503
    assert provider["calls"] == []


def test_malformed_permissions_never_update(provider):
    provider["permissions"] = {"mcp_servers": "not-a-list"}
    with pytest.raises(service.McpGrantError, match="invalid MCP permissions"):
        grant()
    assert provider["updates"] == []


@pytest.fixture
def endpoint(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[route._grant_actor] = lambda: "admin"
    send = Mock(return_value="smtp_accepted")
    monkeypatch.setattr(route, "send_mcp_access_granted", send)
    return TestClient(app), send


def test_endpoint_grants_then_notifies(endpoint, provider):
    client, send = endpoint

    def notify(**kwargs):
        assert provider["calls"][-2:] == ["/key/update", "/key/info"]
        assert kwargs == BODY
        return "smtp_accepted"

    send.side_effect = notify
    response = client.post("/admin/grant-mcp", json=BODY)
    assert response.status_code == 200
    assert response.json()["status"] == "granted"
    assert response.json()["resolved_alias"] == BODY["key_alias"]
    assert response.json()["notification"]["status"] == "smtp_accepted"
    send.assert_called_once()
    assert "private-key-token" not in response.text


def test_endpoint_resolves_old_alias_before_grant_and_notification(endpoint, provider, monkeypatch, caplog):
    client, send = endpoint
    monkeypatch.setattr(route, "ALIAS_MAPPING", {"old-alias": BODY["key_alias"]})
    with caplog.at_level(logging.INFO, logger=route.__name__):
        response = client.post("/admin/grant-mcp", json={**BODY, "key_alias": "old-alias"})
    assert response.status_code == 200
    assert response.json()["resolved_alias"] == BODY["key_alias"]
    assert response.json()["key_alias"] == BODY["key_alias"]
    send.assert_called_once_with(**BODY)
    assert f"eski alias \u00e7evrildi: old-alias -> {BODY['key_alias']}" in caplog.text


def test_resolved_alias_not_found_preserves_existing_error(endpoint, provider, monkeypatch):
    client, send = endpoint
    monkeypatch.setattr(route, "ALIAS_MAPPING", {"old-alias": BODY["key_alias"]})
    provider["keys"] = []
    response = client.post("/admin/grant-mcp", json={**BODY, "key_alias": "old-alias"})
    assert response.status_code == 404
    assert response.json()["detail"] == "Key alias not found"
    send.assert_not_called()


def test_resolve_unknown_alias_is_unchanged(monkeypatch):
    monkeypatch.setattr(route, "ALIAS_MAPPING", {"old-alias": "new-alias"})
    assert route.resolve_alias("already-new") == "already-new"


def test_static_alias_mapping_is_available_without_startup():
    original = "ALZ-YARDIM-MASASI-CEMENC351-PROD-ALLIANZ-CODER"
    resolved = "ALZ-YRDM-MSS-BRYSL-CEMENC351-COPILOT-CODER"
    assert route.resolve_alias(original) == resolved
    assert route.resolve_alias(resolved) == resolved


@pytest.mark.parametrize("error", ["verify", "upstream", "alias", "server", "key"])
def test_no_mail_on_failed_grant(endpoint, provider, error):
    client, send = endpoint
    body = dict(BODY)
    if error == "verify":
        provider["verify"] = False
    elif error == "upstream":
        provider["error_path"] = "/key/update"
    elif error == "alias":
        body["key_alias"] = "OTHER"
    elif error == "server":
        provider["servers"] = []
    else:
        provider["keys"] = []
    response = client.post("/admin/grant-mcp", json=body)
    assert response.status_code in {403, 404, 502}
    send.assert_not_called()


@pytest.mark.parametrize("mail_status", ["failed", "recorded"])
def test_mail_status_does_not_hide_successful_grant(endpoint, provider, mail_status):
    client, send = endpoint
    send.return_value = mail_status
    response = client.post("/admin/grant-mcp", json=BODY)
    assert response.status_code == 200
    assert response.json()["status"] == "granted"
    assert response.json()["notification"]["status"] == mail_status


def test_repeat_request_retries_notification_without_updating(endpoint, provider):
    client, send = endpoint
    assert client.post("/admin/grant-mcp", json=BODY).json()["status"] == "granted"
    assert client.post("/admin/grant-mcp", json=BODY).json()["status"] == "already_granted"
    assert len(provider["updates"]) == 1
    assert send.call_count == 2


@pytest.mark.parametrize("changes", [
    {"recipient_email": "not-an-email"}, {"key_alias": "   "},
    {"mcp_name": "search\r\nInjected: value"}, {"environment": "TYPO"},
    {"unexpected": True}, {"recipient_email": None},
])
def test_invalid_body_never_grants_or_mails(endpoint, monkeypatch, changes):
    client, send = endpoint
    grant_mock = AsyncMock()
    monkeypatch.setattr(route, "grant_mcp_access", grant_mock)
    assert client.post("/admin/grant-mcp", json={**BODY, **changes}).status_code == 422
    grant_mock.assert_not_called()
    send.assert_not_called()


def test_omitted_recipient_email_is_rejected(endpoint):
    client, send = endpoint
    body = {name: value for name, value in BODY.items() if name != "recipient_email"}
    assert client.post("/admin/grant-mcp", json=body).status_code == 422
    send.assert_not_called()


def test_environment_defaults_to_prod(endpoint, provider):
    client, send = endpoint
    body = {name: value for name, value in BODY.items() if name != "environment"}
    response = client.post("/admin/grant-mcp", json=body)
    assert response.status_code == 200
    assert response.json()["environment"] == "PROD"
    send.assert_called_once()


def test_unauthenticated_request_is_rejected(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    grant_mock = AsyncMock()
    monkeypatch.setattr(route, "grant_mcp_access", grant_mock)
    assert TestClient(app).post("/admin/grant-mcp", json=BODY).status_code == 401
    grant_mock.assert_not_called()


@pytest.mark.parametrize("is_superuser,expected", [(True, 200), (False, 403)])
def test_bearer_superuser_requirement_is_preserved(monkeypatch, is_superuser, expected):
    app = FastAPI()
    app.include_router(route.router)
    app.state.container = SimpleNamespace(session_factory=Mock(return_value=AsyncMock()))
    monkeypatch.setattr(route, "get_current_user", AsyncMock(return_value=SimpleNamespace(
        username="admin", is_superuser=is_superuser,
    )))
    grant_mock = AsyncMock(return_value={"status": "granted", "key_alias": BODY["key_alias"]})
    send = Mock(return_value="smtp_accepted")
    monkeypatch.setattr(route, "send_mcp_access_granted", send)
    monkeypatch.setattr(route, "grant_mcp_access", grant_mock)
    response = TestClient(app).post(
        "/admin/grant-mcp", json=BODY, headers={"Authorization": "Bearer example-token"},
    )
    assert response.status_code == expected
    if is_superuser:
        grant_mock.assert_awaited_once()
        send.assert_called_once()
    else:
        grant_mock.assert_not_called()
        send.assert_not_called()


def test_invalid_bearer_token_is_rejected(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.state.container = SimpleNamespace(session_factory=Mock(return_value=AsyncMock()))
    monkeypatch.setattr(route, "get_current_user", AsyncMock(side_effect=HTTPException(401, "Invalid token")))
    grant_mock = AsyncMock()
    monkeypatch.setattr(route, "grant_mcp_access", grant_mock)
    response = TestClient(app).post(
        "/admin/grant-mcp", json=BODY, headers={"Authorization": "Bearer invalid-token"},
    )
    assert response.status_code == 401
    grant_mock.assert_not_called()


@pytest.fixture
def signed_endpoint(monkeypatch):
    monkeypatch.setenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "hmac")
    monkeypatch.setenv("GENAI_ORION_PANEL_WEBHOOK_SECRET", "test-orion-secret")
    app = FastAPI()
    app.include_router(route.router)
    send = Mock(return_value="smtp_accepted")
    monkeypatch.setattr(route, "send_mcp_access_granted", send)
    body = json.dumps(BODY).encode("utf-8")
    signature = hmac.new(b"test-orion-secret", body, hashlib.sha256).hexdigest()
    headers = {"Content-Type": "application/json", "X-GenAi-Orion-Panel-Signature": signature}
    return TestClient(app), send, body, headers


def test_signed_integration_grants_without_login(signed_endpoint, provider):
    client, send, body, headers = signed_endpoint
    response = client.post("/admin/grant-mcp", content=body, headers=headers)
    assert response.status_code == 200
    assert response.json()["resolved_alias"] == BODY["key_alias"]
    send.assert_called_once_with(**BODY)
    assert len(provider["updates"]) == 1


@pytest.mark.parametrize("problem", ["invalid", "empty", "tampered", "missing_secret", "disabled"])
def test_invalid_integration_auth_never_grants_or_mails(signed_endpoint, monkeypatch, problem):
    client, send, body, headers = signed_endpoint
    if problem == "invalid":
        headers["X-GenAi-Orion-Panel-Signature"] = "bad-signature"
    elif problem == "empty":
        headers["X-GenAi-Orion-Panel-Signature"] = ""
    elif problem == "tampered":
        body += b" "
    elif problem == "missing_secret":
        monkeypatch.delenv("GENAI_ORION_PANEL_WEBHOOK_SECRET")
    else:
        monkeypatch.setenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "off")
    grant_mock = AsyncMock()
    monkeypatch.setattr(route, "grant_mcp_access", grant_mock)
    response = client.post("/admin/grant-mcp", content=body, headers=headers)
    assert response.status_code == (503 if problem in {"missing_secret", "disabled"} else 401)
    grant_mock.assert_not_called()
    send.assert_not_called()


def test_application_registers_endpoint_with_unchanged_request_contract():
    operation = create_app().openapi()["paths"]["/admin/grant-mcp"]["post"]
    assert operation["requestBody"]["content"]["application/json"]["schema"]["$ref"].endswith("/GrantMcpBody")


def test_notification_template_escapes_alias_and_has_no_unresolved_markers():
    rendered = mailer.render_template(
        "mcp_access_granted", key_alias="BRYSL-<script>&test", mcp_name="search",
        environment="PROD", completed_at="2026-11-10", test_message=False,
    )
    assert "BRYSL-&lt;script&gt;&amp;test" in rendered
    assert "Your MCP server access has been granted" in rendered
    assert "TEST NOTIFICATION" not in rendered
    assert "unresolved:" not in rendered


def test_mail_sink_records_expected_recipient_and_alias(monkeypatch, tmp_path):
    monkeypatch.setenv("MAIL_PROVIDER", "placeholder")
    monkeypatch.setenv("MAIL_SINK_DIR", str(tmp_path))
    assert notification.send_mcp_access_granted(**BODY) == "recorded"
    record = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert record["recipients"] == [BODY["recipient_email"]]
    assert BODY["key_alias"] in record["body_html"]
    assert "private-key-token" not in record["body_html"]


def test_mail_failure_is_reported_without_raising(monkeypatch):
    monkeypatch.setattr(notification, "send_mail", Mock(side_effect=OSError("relay unavailable")))
    assert notification.send_mcp_access_granted(**BODY) == "failed"


def test_mail_false_result_is_failure(monkeypatch):
    monkeypatch.setattr(notification, "send_mail", Mock(return_value=False))
    assert notification.send_mcp_access_granted(**BODY) == "failed"


def test_smtp_notification_uses_existing_mailer(monkeypatch):
    monkeypatch.setenv("MAIL_PROVIDER", "smtp")
    monkeypatch.delenv("MAIL_SINK_DIR", raising=False)
    smtp = Mock()
    monkeypatch.setattr(mailer.smtplib, "SMTP", smtp)
    assert notification.send_mcp_access_granted(**BODY) == "smtp_accepted"
    sent = smtp.return_value.sendmail.call_args.args
    assert sent[1] == [BODY["recipient_email"]]
    assert BODY["key_alias"] in sent[2]
    smtp.return_value.close.assert_called_once()


def test_test_message_cannot_be_confused_with_a_real_grant(monkeypatch, tmp_path):
    monkeypatch.setenv("MAIL_PROVIDER", "placeholder")
    monkeypatch.setenv("MAIL_SINK_DIR", str(tmp_path))
    assert notification.send_mcp_access_granted(**BODY, test_message=True) == "recorded"
    record = json.loads(next(tmp_path.glob("*.json")).read_text(encoding="utf-8"))
    assert record["subject"].startswith("[TEST - no access changed]")
    assert "TEST NOTIFICATION" in record["body_html"]
    assert "Your MCP server access has been granted" not in record["body_html"]