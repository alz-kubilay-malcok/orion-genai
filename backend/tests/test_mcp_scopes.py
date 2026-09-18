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


def test_itsm_90487_all_tools_with_csv_tool_string():
    """Jira/n8n ITSM-90487: tum_araclara_erisim=true + virgüllü tek araç string.

    Eski kural bunu 422 yapıyordu (``true iken araclar boş olmalı``); n8n
    tarafında 500 gibi görünüyordu. Flag öncelikli, listedeki araçlar yoksayılır.
    """
    payload = McpKeyPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_erisim_anahtari",
            "talep_no": "ITSM-90487",
            "talep_url": "https://atlas.allianz.com.tr/jira/browse/ITSM-90487",
            "olusturulma_tarihi": "1789735064485",
            "departman_adi": "[Müşteri Değer Yönetimi Dönüşüm Takımı]",
            "ortam": "PROD",
            "mcp_sunucusu": "design",
            "araclar": [
                "list_ndbx_components,get_ndbx_doc,get_ndbx_css,push_design_html",
            ],
            "tum_araclara_erisim": True,
        }
    )
    scopes = payload.mcp_scopes()
    assert len(scopes) == 1
    assert scopes[0].server == "design"
    assert scopes[0].all_tools is True
    assert scopes[0].tools == ()
    stored = persist_fields(scopes)
    assert stored["mcp_server_slug"] == "design"
    assert stored["all_tools"] is True
    assert stored["mcp_tool_names"] == []


def test_csv_tool_string_split_when_not_all_tools():
    payload = McpKeyPayload.model_validate(
        {
            **SHARED,
            "talep_turu": "mcp_erisim_anahtari",
            "mcp_sunucusu": "design",
            "araclar": ["list_ndbx_components,get_ndbx_doc,get_ndbx_css,push_design_html"],
            "tum_araclara_erisim": False,
        }
    )
    assert list(payload.mcp_scopes()[0].tools) == [
        "list_ndbx_components",
        "get_ndbx_doc",
        "get_ndbx_css",
        "push_design_html",
    ]
