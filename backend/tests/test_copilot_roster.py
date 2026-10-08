import asyncio

import httpx
import pytest

from backend.src.core.copilot_roster import register_roster_member


def test_roster_skips_when_unconfigured(monkeypatch):
    monkeypatch.delenv("COPILOT_ROSTER_BASE_URL", raising=False)
    monkeypatch.delenv("COPILOT_ROSTER_ADMIN_TOKEN", raising=False)

    called = False

    class FakeClient:
        def __init__(self, **_kwargs):
            nonlocal called
            called = True

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    ok = asyncio.run(
        register_roster_member(
            api_key="sk-secret",
            full_name="Ali",
            team_id="GENAI",
            email="ali@allianz.com.tr",
        )
    )
    assert ok is False
    assert called is False


def test_roster_posts_body_without_added_at(monkeypatch):
    monkeypatch.setenv("COPILOT_ROSTER_BASE_URL", "http://roster.test")
    monkeypatch.setenv("COPILOT_ROSTER_ADMIN_TOKEN", "token")
    seen: dict = {}

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers=None, json=None):
            seen["url"] = url
            seen["headers"] = headers
            seen["json"] = json
            return httpx.Response(200, json={"row_count": 1, "rows": []})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    ok = asyncio.run(
        register_roster_member(
            api_key="sk-secret",
            full_name="Ali Veli",
            team_id="GENAI",
            email="ali@allianz.com.tr",
        )
    )
    assert ok is True
    assert seen["url"] == "http://roster.test/roster"
    assert seen["headers"]["X-Admin-Token"] == "token"
    assert seen["json"] == {
        "api_key": "sk-secret",
        "full_name": "Ali Veli",
        "team_id": "GENAI",
        "email": "ali@allianz.com.tr",
    }
    assert "added_at" not in seen["json"]


def test_roster_http_error_does_not_raise(monkeypatch):
    monkeypatch.setenv("COPILOT_ROSTER_BASE_URL", "http://roster.test/")
    monkeypatch.setenv("COPILOT_ROSTER_ADMIN_TOKEN", "token")

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers=None, json=None):
            return httpx.Response(401, json={"detail": "no"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    ok = asyncio.run(
        register_roster_member(api_key="sk-secret", full_name="Ali", team_id="GENAI")
    )
    assert ok is False


def test_roster_connect_error_does_not_raise(monkeypatch):
    monkeypatch.setenv("COPILOT_ROSTER_BASE_URL", "http://roster.test")
    monkeypatch.setenv("COPILOT_ROSTER_ADMIN_TOKEN", "token")

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def post(self, url, headers=None, json=None):
            raise httpx.ConnectError("down")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    ok = asyncio.run(
        register_roster_member(api_key="sk-secret", full_name="Ali", team_id="GENAI")
    )
    assert ok is False


def test_process_batch_registers_roster(monkeypatch):
    from backend.src.core.batch_keys.excel import BatchRow
    from backend.src.core.batch_keys.service import process_batch

    seen: dict = {}

    async def generate(**kwargs):
        return "sk-batch", "kid"

    async def fake_register(**kwargs):
        seen.update(kwargs)
        return True

    monkeypatch.setattr(
        "backend.src.core.copilot_roster.register_roster_member",
        fake_register,
    )
    results = asyncio.run(
        process_batch(
            [BatchRow(2, "ali@allianz.com.tr", "Ali", "ALZ-X", "GENAI", "DEV")],
            model_name="allianz-text",
            send_mail=False,
            generate_key=generate,
        )
    )
    assert results[0].ok is True
    assert seen == {
        "api_key": "sk-batch",
        "full_name": "Ali",
        "team_id": "GENAI",
        "email": "ali@allianz.com.tr",
    }


def test_provision_source_registers_only_litellm():
    import inspect

    from backend.src.worker.jobs import provision as provision_module

    source = inspect.getsource(provision_module._provision_credential)
    assert "register_roster_member" in source
    assert 'if kind == "litellm"' in source
