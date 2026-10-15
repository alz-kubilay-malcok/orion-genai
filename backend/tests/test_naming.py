from backend.src.core.naming import (
    build_litellm_key_alias,
    build_mcp_key_alias,
    key_alias_for_request,
    litellm_purpose_token,
)


def test_litellm_alias_shared_layout():
    alias = build_litellm_key_alias(
        department="GENAI",
        environment="PROD",
        project="HD-12345",
        purpose="AGENTIC",
    )
    assert alias == "ALZ-GENAI-PROD-HD12345-AGENTIC"


def test_project_segment_follows_migration_sheet():
    # api_key_migration.xlsx: sığıyorsa olduğu gibi, sığmıyorsa sesli harf atılır
    assert build_litellm_key_alias(
        department="MOTOR", environment="PROD", project="VoC", purpose="CHATBOT",
    ) == "ALZ-MOTOR-PROD-VOC-CHATBOT"
    assert build_litellm_key_alias(
        department="X", environment="DEV", project="internal-assistai-test",
        purpose="CHATBOT",
    ).split("-")[3] == "INTRNLASSSTTST"[:15]
    assert build_litellm_key_alias(
        department="X", environment="DEV", project="contact_center_profanity",
        purpose="CHATBOT",
    ).split("-")[3] == "CNTCTCNTRPRFNTY"
    assert build_litellm_key_alias(
        department="X", environment="DEV", project="Sağlık Parser", purpose="IDP",
    ).split("-")[3] == "SAGLIKPARSER"


def test_litellm_alias_bireysel_inserts_name():
    alias = build_litellm_key_alias(
        department="Motor",
        environment="bireysel",
        project="jupyter",
        purpose="OTHER",
        person="Ali Veli",
    )
    assert alias == "ALZ-MOTOR-BRYSL-ALI-VELI-JUPYTER-OTHER"


def test_litellm_alias_project_capped_at_15():
    alias = build_litellm_key_alias(
        department="GENAI",
        environment="DEV",
        project="healthcare-parser-extra",
        purpose="IDP",
    )
    project = alias.split("-", 3)[3].rsplit("-", 1)[0]
    assert len(project) <= 15
    assert alias.startswith("ALZ-GENAI-DEV-")
    assert alias.endswith("-IDP")


def test_purpose_mapping_and_coder_fallback():
    assert litellm_purpose_token("RAG") == "AGENTIC"
    assert litellm_purpose_token("CHAT") == "CHATBOT"
    assert litellm_purpose_token("AGENT") == "AGENTIC"
    assert litellm_purpose_token("DIGERI") == "OTHER"
    assert litellm_purpose_token("KUBEFLOW") == "KUBEFLOW"
    assert litellm_purpose_token("RAG", ["allianz-coder"]) == "AGENTIC"
    assert litellm_purpose_token("", ["text2test"]) == "CODER"
    assert litellm_purpose_token("", ["allianz-text"]) == "OTHER"


def test_key_alias_for_request_uses_ticket_when_project_missing():
    alias = key_alias_for_request(
        {
            "request_type": "litellm_key",
            "department_name": "GENAI",
            "environment": "PROD",
            "genai_orion_panel_ticket_id": "HD-12345",
            "purpose_code": "KUBEFLOW",
            "requester_name": "Kubilay",
            "models": ["allianz-text"],
        }
    )
    assert alias == "ALZ-GENAI-PROD-HD12345-KUBEFLOW"


def test_key_alias_for_request_bireysel_uses_requester_name():
    alias = key_alias_for_request(
        {
            "department_name": "GENAI",
            "environment": "BRYSL",
            "project_name": "n8n",
            "purpose_code": "CHAT",
            "requester_name": "Ayşe Yılmaz",
            "genai_orion_panel_ticket_id": "HD-9",
        }
    )
    assert alias == "ALZ-GENAI-BRYSL-AYSE-YILMAZ-N8N-CHATBOT"


def test_mcp_alias_unchanged():
    alias = build_mcp_key_alias(
        department="HASAR",
        ticket="HD22334",
        environment="TEST",
        server_slug="HASAR-BILGI",
    )
    assert alias == "ALZ-MCP-HASAR-HD22334-TEST-HASAR-BILGI"
    via_request = key_alias_for_request(
        {
            "request_type": "mcp_key",
            "department_name": "HASAR",
            "genai_orion_panel_ticket_id": "HD22334",
            "environment": "TEST",
            "mcp_server_slug": "HASAR-BILGI",
        },
        "mcp_key",
    )
    assert via_request == alias
