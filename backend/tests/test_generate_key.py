from backend.src.core.litellm.generate_key import (
    build_key_generate_body,
    build_mcp_key_generate_body,
    match_team_id,
    parse_team_list,
    route_models_for_litellm,
)


def test_route_models_alias_and_dedupe():
    assert route_models_for_litellm(["text2test", "allianz-text", "text2test"]) == [
        "allianz-text",
    ]


def test_build_key_generate_body_no_tpm_rpm():
    body = build_key_generate_body(
        key_alias="ALZ-GENAI-HD1-DEV-RAG",
        models=["allianz-text"],
        team_id="GENAI",
        max_parallel_requests=5,
        metadata={"ticket": "HD-1"},
    )
    assert body["key_alias"] == "ALZ-GENAI-HD1-DEV-RAG"
    assert body["models"] == ["allianz-text"]
    assert body["team_id"] == "GENAI"
    assert body["max_parallel_requests"] == 5
    assert "tpm_limit" not in body
    assert "rpm_limit" not in body


def test_build_mcp_key_scoped_tools():
    body = build_mcp_key_generate_body(
        key_alias="mcp-key",
        server_slug="document-search",
        tool_names=["rag", "search"],
        all_tools=False,
    )
    perm = body["object_permission"]
    assert perm["mcp_servers"] == ["document-search"]
    assert perm["mcp_tool_permissions"] == {"document-search": ["rag", "search"]}
    assert body["models"] == ["no-default-models"]


def test_build_mcp_key_multi_server():
    from backend.src.core.mcp_scopes import McpScope

    body = build_mcp_key_generate_body(
        key_alias="mcp-key",
        scopes=[
            McpScope("document-search", ("rag",), False),
            McpScope("jira-mcp", (), True),
        ],
    )
    perm = body["object_permission"]
    assert perm["mcp_servers"] == ["document-search", "jira-mcp"]
    assert perm["mcp_tool_permissions"] == {"document-search": ["rag"]}


def test_teams_for_ui_dedupes():
    from backend.src.core.litellm.generate_key import teams_for_ui

    rows = teams_for_ui(
        [
            {"team_id": "abc", "team_alias": "GENAI"},
            {"team_id": "abc", "team_alias": "GENAI"},
            {"team_id": "demo", "team_name": "Demo"},
        ]
    )
    assert rows == [
        {"team_id": "demo", "team_alias": "Demo"},
        {"team_id": "abc", "team_alias": "GENAI"},
    ]


def test_match_team_id_by_alias():
    teams = parse_team_list({"teams": [{"team_id": "abc", "team_alias": "GENAI"}]})
    assert match_team_id(teams, "genai") == "abc"


def test_generate_litellm_virtual_key(monkeypatch):
    import asyncio

    import httpx

    from backend.src.core.litellm.generate_key import generate_litellm_virtual_key

    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm.test")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "master")

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers=None):
            return httpx.Response(200, json={"teams": [{"team_id": "abc", "team_alias": "GENAI"}]})

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/key/generate")
            assert json["key_alias"] == "ALZ-TEST"
            assert json["models"] == ["allianz-text"]
            assert json["team_id"] == "abc"
            return httpx.Response(200, json={"key": "sk-abc", "key_id": "k1"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    key, provider_id = asyncio.run(
        generate_litellm_virtual_key(
            key_alias="ALZ-TEST",
            models=["allianz-text"],
            team_id="GENAI",
            environment="DEV",
        )
    )
    assert key == "sk-abc"
    assert provider_id == "k1"


def test_key_info_from_payload_wraps_info():
    from backend.src.core.litellm.generate_key import key_info_from_payload

    info = key_info_from_payload(
        {
            "info": {
                "key_alias": "ALZ-X",
                "team_id": "GENAI",
                "models": ["allianz-text"],
                "max_parallel_requests": 5,
                "blocked": False,
            }
        }
    )
    assert info.key_alias == "ALZ-X"
    assert info.team_id == "GENAI"
    assert info.models == ["allianz-text"]
    assert info.max_parallel_requests == 5


def test_build_key_update_body_omits_empty():
    from backend.src.core.litellm.generate_key import build_key_update_body

    body = build_key_update_body(api_key="sk-1", team_id="GENAI", blocked=True)
    assert body == {"key": "sk-1", "team_id": "GENAI", "blocked": True}
    assert "max_parallel_requests" not in body
    assert "models" not in body


def test_fetch_key_info_404_is_none(monkeypatch):
    import asyncio

    import httpx

    from backend.src.core.litellm.generate_key import fetch_key_info

    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm.test")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "master")

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, params=None, headers=None):
            assert url.endswith("/key/info")
            assert params == {"key": "sk-missing"}
            return httpx.Response(404, json={"detail": "unknown key"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    assert asyncio.run(fetch_key_info(api_key="sk-missing", environment="DEV")) is None


def test_update_litellm_virtual_key(monkeypatch):
    import asyncio

    import httpx

    from backend.src.core.litellm.generate_key import update_litellm_virtual_key

    monkeypatch.setenv("LITELLM_BASE_URL", "http://litellm.test")
    monkeypatch.setenv("LITELLM_MASTER_KEY", "master")

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers=None):
            return httpx.Response(200, json={"teams": [{"team_id": "abc", "team_alias": "GENAI"}]})

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/key/update")
            assert json["key"] == "sk-aaa"
            assert json["team_id"] == "abc"
            assert json["max_parallel_requests"] == 8
            assert json["models"] == ["allianz-text"]
            assert json["blocked"] is True
            return httpx.Response(200, json={"info": {"key_alias": "ALZ-A"}})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    payload = asyncio.run(
        update_litellm_virtual_key(
            api_key="sk-aaa",
            environment="DEV",
            team_id="GENAI",
            max_parallel_requests=8,
            models=["allianz-text"],
            blocked=True,
        )
    )
    assert payload["info"]["key_alias"] == "ALZ-A"
