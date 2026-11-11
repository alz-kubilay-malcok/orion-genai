import asyncio
import json
from types import SimpleNamespace
from unittest.mock import AsyncMock, Mock

import httpx
import pytest
from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from backend.src.api.auth.dependencies import get_current_superuser, get_current_user
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
        "network_error": False, "empty_update": False,
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
                state["permissions"] = payload["object_permission"]
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
    app.dependency_overrides[get_current_superuser] = lambda: SimpleNamespace(username="admin")
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
    assert response.json()["notification"]["status"] == "smtp_accepted"
    send.assert_called_once()
    assert "private-key-token" not in response.text


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


@pytest.mark.parametrize("field", ["environment", "recipient_email"])
def test_explicit_target_and_recipient_required(endpoint, field):
    client, send = endpoint
    body = {name: value for name, value in BODY.items() if name != field}
    assert client.post("/admin/grant-mcp", json=body).status_code == 422
    send.assert_not_called()


def test_unauthenticated_request_is_rejected(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)

    async def anonymous_user():
        raise HTTPException(401, "Authentication required")

    app.dependency_overrides[get_current_user] = anonymous_user
    grant_mock = AsyncMock()
    monkeypatch.setattr(route, "grant_mcp_access", grant_mock)
    assert TestClient(app).post("/admin/grant-mcp", json=BODY).status_code == 401
    grant_mock.assert_not_called()


def test_non_superuser_cannot_grant(monkeypatch):
    app = FastAPI()
    app.include_router(route.router)
    app.dependency_overrides[get_current_user] = lambda: SimpleNamespace(is_superuser=False)
    grant_mock = AsyncMock()
    monkeypatch.setattr(route, "grant_mcp_access", grant_mock)
    assert TestClient(app).post("/admin/grant-mcp", json=BODY).status_code == 403
    grant_mock.assert_not_called()


def test_application_registers_protected_endpoint():
    operation = create_app().openapi()["paths"]["/admin/grant-mcp"]["post"]
    assert operation["security"] == [{"HTTPBearer": []}]


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