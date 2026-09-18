"""`worker/jobs/provision.py::_resolve_litellm_team_id` — hem `litellm_key`
hem `mcp_key` webhook akışının ortak takım çözümleme yolu.

Eskiden eşleşme bulunamazsa (veya `/team/list` hata verirse) ham isim
`team_id` olarak LiteLLM'e geçiriliyordu — istek her zaman "başarılı"
görünüyor, ama LiteLLM'de geçersiz bir `team_id` ile bozuk key oluşuyordu.
Artık :func:`resolve_or_create_team_id` üzerinden gerçek bir team bulunur/
oluşturulur; ağ hatası `RetryHeld`, gerçek hata `PermanentError` olarak
worker'a bildirilir.
"""

from __future__ import annotations

import asyncio

import httpx
import pytest

from backend.src.worker.errors import PermanentError, RetryHeld
from backend.src.worker.jobs.provision import _resolve_litellm_team_id


def test_resolve_team_id_blank_name_is_noop():
    result = asyncio.run(
        _resolve_litellm_team_id(None, base="http://x", credential="c", team_name="")
    )
    assert result == ""


def test_resolve_team_id_matches_existing_team(monkeypatch):
    calls: list[str] = []

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers=None):
            calls.append(url)
            return httpx.Response(
                200, json={"teams": [{"team_id": "abc-123", "team_alias": "GENAI"}]},
            )

        async def post(self, url, headers=None, json=None):  # pragma: no cover
            raise AssertionError("var olan team için /team/new çağrılmamalı")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(
        _resolve_litellm_team_id(
            None, base="http://litellm.test", credential="master", team_name="genai",
        )
    )
    assert result == "abc-123"
    assert calls == ["http://litellm.test/team/list"]


def test_resolve_team_id_auto_creates_missing_team(monkeypatch):
    """Eski (bozuk) davranış: isim bulunamazsa ham string döndürülürdü.
    Yeni davranış: gerçek bir team oluşturulup id'si kullanılır."""

    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers=None):
            return httpx.Response(200, json={"teams": []})

        async def post(self, url, headers=None, json=None):
            assert url.endswith("/team/new")
            assert json == {"team_alias": "MCP-HASAR-TAKIMI"}
            return httpx.Response(200, json={"team_id": "new-team-id-789"})

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    result = asyncio.run(
        _resolve_litellm_team_id(
            None,
            base="http://litellm.test",
            credential="master",
            team_name="MCP-HASAR-TAKIMI",
        )
    )
    assert result == "new-team-id-789"


def test_resolve_team_id_network_failure_raises_retry_held(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers=None):
            return httpx.Response(200, json={"teams": []})

        async def post(self, url, headers=None, json=None):
            raise httpx.ConnectError("boom")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(RetryHeld):
        asyncio.run(
            _resolve_litellm_team_id(
                None, base="http://litellm.test", credential="master", team_name="X",
            )
        )


def test_resolve_team_id_litellm_400_raises_permanent_error(monkeypatch):
    class FakeClient:
        def __init__(self, **_kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *_args):
            return None

        async def get(self, url, headers=None):
            return httpx.Response(200, json={"teams": []})

        async def post(self, url, headers=None, json=None):
            return httpx.Response(400, text="bad request")

    monkeypatch.setattr(httpx, "AsyncClient", FakeClient)
    with pytest.raises(PermanentError):
        asyncio.run(
            _resolve_litellm_team_id(
                None, base="http://litellm.test", credential="master", team_name="X",
            )
        )


def test_resolve_team_id_used_identically_for_litellm_and_mcp_kind():
    """`_provision_credential` her iki `kind` (litellm/mcp) için de AYNI
    `_resolve_litellm_team_id` çağrısını kullanır (bkz. provision.py L150-158) —
    yani takım çözümleme MCP anahtar taleplerinde de bu fonksiyondan geçer."""
    import inspect

    from backend.src.worker.jobs import provision as provision_module

    source = inspect.getsource(provision_module._provision_credential)
    assert "_resolve_litellm_team_id" in source
    assert 'kind == "litellm"' in source
