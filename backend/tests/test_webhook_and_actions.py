import pytest
from pydantic import ValidationError

from backend.src.api.utils.schemas.webhook import (
    LitellmKeyPayload,
    McpKeyPayload,
    McpRegistryPayload,
)
from backend.src.api.utils.webhook_mapping import payload_to_request_fields, resolve_request_type
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


def test_mcp_key_accepts_proje_adi_and_ignores_unknown_fields():
    payload = McpKeyPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_erisim_anahtari",
            "ortam": "prod",
            "proje_adi": "document-search",
            "unknown_orion_field": "ignore-me",
            "mcp_sunucusu": "document-search",
            "araclar": ["rag"],
            "tum_araclara_erisim": False,
        }
    )
    assert payload.proje_adi == "document-search"
    fields = payload_to_request_fields(payload, "mcp_key", payload.model_dump(mode="json"))
    assert fields["project_name"] == "document-search"
    assert fields["environment"] == "PROD"


def test_mcp_registry_normalizes_and_copies_slug():
    payload = McpRegistryPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_sunucu_kaydi",
            "ortam": "TEST",
            "proje_adi": "document-search",
            "mcp_sunucu_adi": "Doküman Arama MCP",
            "repo_platformu": "bitbucket",
            "extra_form_field": True,
        }
    )
    fields = payload_to_request_fields(
        payload, "mcp_server_registry", payload.model_dump(mode="json"),
    )
    assert fields["environment"] == "TEST"
    assert fields["repo_platform"] == "BITBUCKET"
    assert fields["mcp_server_slug"] == "document-search"


def test_mcp_registry_prod_requires_min_score():
    payload = McpRegistryPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_sunucu_kaydi",
            "ortam": "PROD",
            "proje_adi": "document-search",
        }
    )
    with pytest.raises(ValueError, match="minimum_evaluation_skoru"):
        payload_to_request_fields(
            payload, "mcp_server_registry", payload.model_dump(mode="json"),
        )


def test_revise_only_litellm():
    assert ApprovalAction.REVISE in VALID_ACTIONS_BY_TYPE[RequestType.LITELLM_KEY]
    assert ApprovalAction.REVISE not in VALID_ACTIONS_BY_TYPE[RequestType.MCP_KEY]
    assert ApprovalAction.REVISE not in VALID_ACTIONS_BY_TYPE[RequestType.MCP_SERVER_REGISTRY]
