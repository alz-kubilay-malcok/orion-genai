import pytest
from pydantic import ValidationError

from backend.src.api.utils.schemas.webhook import LitellmKeyPayload, McpKeyPayload
from backend.src.api.utils.webhook_mapping import resolve_request_type
from backend.src.domain.enums import VALID_ACTIONS_BY_TYPE, ApprovalAction, RequestType


SHARED = {
    "talep_no": "HD-1",
    "talep_url": "https://atlassian.example/HD-1",
    "talep_eden_adi": "Kubilay",
    "talep_eden_eposta": "user@allianz.com.tr",
    "olusturulma_tarihi": "2026-08-17T11:00:00+03:00",
}


def test_extra_field_rejected():
    with pytest.raises(ValidationError):
        LitellmKeyPayload.model_validate(
            {
                **SHARED,
                "talep_turu": "litellm_api_anahtari",
                "unknown_field": "nope",
            }
        )


def test_resolve_request_type():
    assert resolve_request_type("litellm_api_anahtari") == "litellm_key"
    assert resolve_request_type("mcp_erisim_anahtari") == "mcp_key"
    with pytest.raises(ValueError):
        resolve_request_type("chatbot")


def test_mcp_payload_ok():
    payload = McpKeyPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_erisim_anahtari",
            "ortam": "PROD",
            "mcp_sunucusu": "document-search",
            "araclar": ["rag"],
            "tum_araclara_erisim": False,
        }
    )
    assert payload.mcp_sunucusu == "document-search"
    assert [s.server for s in payload.mcp_scopes()] == ["document-search"]


def test_mcp_payload_multi_server():
    payload = McpKeyPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_erisim_anahtari",
            "ortam": "PROD",
            "mcp_sunucusu": ["document-search", "jira-mcp"],
            "araclar": {
                "document-search": ["rag", "search"],
                "jira-mcp": ["create_issue"],
            },
            "tum_araclara_erisim": False,
        }
    )
    scopes = payload.mcp_scopes()
    assert [s.server for s in scopes] == ["document-search", "jira-mcp"]
    assert list(scopes[1].tools) == ["create_issue"]


def test_mcp_payload_erisimler_mixed():
    payload = McpKeyPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_erisim_anahtari",
            "ortam": "PROD",
            "erisimler": [
                {
                    "mcp_sunucusu": "document-search",
                    "araclar": ["rag"],
                    "tum_araclara_erisim": False,
                },
                {
                    "mcp_sunucusu": "jira-mcp",
                    "araclar": [],
                    "tum_araclara_erisim": True,
                },
            ],
        }
    )
    scopes = payload.mcp_scopes()
    assert scopes[0].all_tools is False
    assert scopes[1].all_tools is True


def test_mcp_payload_multi_flat_tools_rejected():
    with pytest.raises(ValidationError):
        McpKeyPayload.model_validate(
            {
                **SHARED,
                "talep_turu": "mcp_erisim_anahtari",
                "mcp_sunucusu": ["a", "b"],
                "araclar": ["rag"],
                "tum_araclara_erisim": False,
            }
        )


def test_revise_only_litellm():
    assert ApprovalAction.REVISE in VALID_ACTIONS_BY_TYPE[RequestType.LITELLM_KEY]
    assert ApprovalAction.REVISE not in VALID_ACTIONS_BY_TYPE[RequestType.MCP_KEY]
    assert ApprovalAction.REVISE not in VALID_ACTIONS_BY_TYPE[RequestType.MCP_SERVER_REGISTRY]
