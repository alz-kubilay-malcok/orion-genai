from backend.src.api.utils.schemas.webhook import McpKeyPayload
from backend.src.api.utils.webhook_mapping import payload_to_request_fields
from backend.src.core.mcp_scopes import persist_fields, scopes_from_row


SHARED = {
    "talep_no": "HD-1",
    "talep_url": "https://atlassian.example/HD-1",
    "talep_eden_adi": "Kubilay",
    "talep_eden_eposta": "user@allianz.com.tr",
    "olusturulma_tarihi": "2026-08-17T11:00:00+03:00",
}


def test_persist_roundtrip_multi():
    payload = McpKeyPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_erisim_anahtari",
            "mcp_sunucusu": ["document-search", "jira-mcp"],
            "araclar": {
                "document-search": ["rag"],
                "jira-mcp": ["create_issue"],
            },
        }
    )
    stored = persist_fields(payload.mcp_scopes())
    assert stored["mcp_server_slug"] == "document-search,jira-mcp"
    assert "document-search::rag" in stored["mcp_tool_names"]
    decoded = scopes_from_row(
        stored["mcp_server_slug"],
        stored["mcp_tool_names"],
        stored["all_tools"],
    )
    assert [s.server for s in decoded] == ["document-search", "jira-mcp"]
    fields = payload_to_request_fields(payload, "mcp_key", payload.model_dump(mode="json"))
    assert fields["mcp_server_slug"] == "document-search,jira-mcp"
    assert isinstance(fields["mcp_tool_names"], list)
