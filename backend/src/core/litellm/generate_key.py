"""LiteLLM Proxy `/key/generate` gövdesi.

Docs:
  https://docs.litellm.ai/docs/proxy/virtual_keys
  GenerateKeyRequest: `team_id`, `max_parallel_requests`, `models`, `key_alias`.

`max_parallel_requests`: eşzamanlı (in-flight) istek tavanı; aşınca 429.
`team_id`: key'i LiteLLM team satırına bağlar. UI "team adı" verir;
`GET /team/list` içinden `team_alias` veya `team_id` eşleşmesi çözülür.
TPM/RPM (`tpm_limit` / `rpm_limit`) bu üründe gönderilmez.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping

TEAM_LIST_PATH = "/team/list"
TEAM_NEW_PATH = "/team/new"

# Orion form / DB değeri → LiteLLM proxy `model_name`.
# `text2test` katalog alias; proxy route `allianz-text`.
LITELLM_MODEL_ROUTES: dict[str, str] = {
    "text2test": "allianz-text",
}


def route_models_for_litellm(models: list[str] | None) -> list[str]:
    """LiteLLM'e gidecek model listesi. Alias'ları route eder, sırayı korur, tekilleştirir."""
    routed: list[str] = []
    seen: set[str] = set()
    for raw in models or []:
        name = str(raw).strip()
        if not name:
            continue
        mapped = LITELLM_MODEL_ROUTES.get(name.casefold(), name)
        if mapped in seen:
            continue
        seen.add(mapped)
        routed.append(mapped)
    return routed


def parse_team_list(payload: object) -> list[dict[str, Any]]:
    """`GET /team/list` hem `{teams: [...]}` hem düz liste dönebilir."""
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)]
    if isinstance(payload, dict):
        for key in ("teams", "data", "result"):
            value = payload.get(key)
            if isinstance(value, list):
                return [row for row in value if isinstance(row, dict)]
    return []


def teams_for_ui(rows: list[Mapping[str, Any]]) -> list[dict[str, str]]:
    """Dropdown: ``[{team_id, team_alias}]``, boş/tekrar yok."""
    out: list[dict[str, str]] = []
    seen: set[str] = set()
    for row in rows:
        team_id = str(row.get("team_id") or "").strip()
        alias = str(
            row.get("team_alias") or row.get("team_name") or team_id
        ).strip()
        key = (team_id or alias).casefold()
        if not key or key in seen:
            continue
        seen.add(key)
        out.append({"team_id": team_id or alias, "team_alias": alias or team_id})
    out.sort(key=lambda item: item["team_alias"].casefold())
    return out


async def fetch_litellm_teams(ortam: str | None) -> list[dict[str, str]]:
    """LiteLLM ``GET /team/list`` — UI dropdown. Hata/timeout → boş liste."""
    import httpx

    from backend.src.core.litellm.target import resolve_litellm_http

    base, credential = resolve_litellm_http(ortam, kind="litellm")
    if not base or not credential:
        return []
    url = f"{base.rstrip('/')}{TEAM_LIST_PATH}"
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            response = await client.get(
                url,
                headers={"Authorization": f"Bearer {credential}"},
            )
    except (httpx.ConnectError, httpx.TimeoutException, OSError):
        return []
    if response.status_code >= 400:
        return []
    try:
        payload = response.json()
    except ValueError:
        return []
    return teams_for_ui(parse_team_list(payload))


class LiteLLMKeyError(Exception):
    """LiteLLM `/key/generate` başarısız. ``retryable`` geçici ağ/5xx."""

    def __init__(self, message: str, *, retryable: bool = False) -> None:
        super().__init__(message)
        self.retryable = retryable


async def resolve_or_create_team_id(
    *,
    base: str,
    credential: str,
    name: str,
    auto_create: bool = False,
) -> str:
    """Team adı/alias → gerçek LiteLLM ``team_id``.

    LiteLLM ``/key/generate`` ve ``/key/update`` yalnız **var olan**
    ``team_id`` kabul eder; rastgele bir string göndermek proxy'de hata
    aldırır. Bu fonksiyon önce ``GET /team/list`` ile alias/id eşleşmesi
    arar; bulamazsa ``auto_create=True`` ise ``POST /team/new`` ile gerçek
    bir team oluşturup dönen id'yi kullanır, aksi halde
    :class:`LiteLLMKeyError` fırlatır (ham isim asla provider'a geçmez).
    """
    import httpx

    needle = (name or "").strip()
    if not needle:
        return ""
    list_url = f"{base.rstrip('/')}{TEAM_LIST_PATH}"
    async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
        try:
            listed = await client.get(
                list_url, headers={"Authorization": f"Bearer {credential}"},
            )
        except (httpx.ConnectError, httpx.TimeoutException, OSError):
            listed = None
        teams: list[dict[str, Any]] = []
        if listed is not None and listed.status_code < 400:
            try:
                teams = parse_team_list(listed.json())
            except ValueError:
                teams = []
        matched = match_team_id(teams, needle)
        if matched:
            return matched
        if not auto_create:
            raise LiteLLMKeyError(
                f"LiteLLM'de '{needle}' adında bir team yok; önce team oluşturun/seçin",
                retryable=False,
            )
        try:
            created = await client.post(
                f"{base.rstrip('/')}{TEAM_NEW_PATH}",
                headers={"Authorization": f"Bearer {credential}"},
                json={"team_alias": needle},
            )
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise LiteLLMKeyError(f"LiteLLM team oluşturulamadı: {exc}", retryable=True) from exc
        snippet = (created.text or "")[:500]
        if created.status_code in {429, 502, 503, 504}:
            raise LiteLLMKeyError(f"LiteLLM team/new http {created.status_code}: {snippet}", retryable=True)
        if created.status_code >= 400:
            raise LiteLLMKeyError(f"LiteLLM team/new http {created.status_code}: {snippet}", retryable=False)
        try:
            payload = created.json()
        except ValueError as exc:
            raise LiteLLMKeyError("LiteLLM team/new non-json response", retryable=True) from exc
        new_id = str(payload.get("team_id") or "").strip()
        if not new_id:
            raise LiteLLMKeyError("LiteLLM team/new response'da team_id yok", retryable=False)
        return new_id


async def create_litellm_team(*, environment: str | None, team_alias: str) -> dict[str, str]:
    """Admin panelden 'yeni team oluştur' — var olan alias'ı reuse eder (idempotent)."""
    from backend.src.core.litellm.target import resolve_litellm_http

    alias = (team_alias or "").strip()
    if not alias:
        raise LiteLLMKeyError("team_alias boş", retryable=False)
    base, credential = resolve_litellm_http(environment, kind="litellm")
    if not base or not credential:
        raise LiteLLMKeyError("LiteLLM base URL veya master key yok", retryable=False)
    team_id = await resolve_or_create_team_id(
        base=base, credential=credential, name=alias, auto_create=True,
    )
    return {"team_id": team_id, "team_alias": alias}


def match_team_id(teams: list[Mapping[str, Any]], name: str) -> str | None:
    """`team_alias` veya `team_id` (casefold) → LiteLLM `team_id`."""
    needle = name.strip().casefold()
    if not needle:
        return None
    for team in teams:
        team_id = str(team.get("team_id") or "").strip()
        alias = str(
            team.get("team_alias") or team.get("team_name") or "",
        ).strip()
        if team_id.casefold() == needle or alias.casefold() == needle:
            return team_id or alias
    return None


def build_key_generate_body(
    *,
    key_alias: str,
    models: list[str] | None,
    team_id: str | None,
    max_parallel_requests: int | None,
    metadata: Mapping[str, object] | None = None,
) -> dict[str, object]:
    """`POST /key/generate` JSON. TPM/RPM yok."""
    body: dict[str, object] = {
        "key_alias": key_alias,
        "models": route_models_for_litellm(list(models or [])),
        "metadata": dict(metadata or {}),
    }
    if team_id and team_id.strip():
        body["team_id"] = team_id.strip()
    if max_parallel_requests is not None:
        body["max_parallel_requests"] = int(max_parallel_requests)
    return body


# MCP key LLM modellerine düşmesin.
MCP_NO_LLM_MODELS = ["no-default-models"]
_LEGACY_MCP_KEY_PATHS = {"/mcp/keys/create", "/mcp/keys"}


def mcp_key_generate_path(raw: str | None) -> str:
    """Eski mock path `/mcp/keys/create` gerçek LiteLLM'de yok → `/key/generate`."""
    path = (raw or "").strip() or "/key/generate"
    if not path.startswith("/"):
        path = "/" + path
    if path.rstrip("/") in _LEGACY_MCP_KEY_PATHS:
        return "/key/generate"
    return path


def build_mcp_key_generate_body(
    *,
    key_alias: str,
    server_slug: str = "",
    tool_names: list[str] | None = None,
    all_tools: bool = False,
    scopes: list[Any] | None = None,
    metadata: Mapping[str, object] | None = None,
    team_id: str | None = None,
) -> dict[str, object]:
    """LiteLLM MCP scoped virtual key — `POST /key/generate`.

    https://docs.litellm.ai/docs/mcp_control
    ``mcp_servers`` birden fazla sunucu alabilir; ``mcp_tool_permissions``
    sunucu → araç listesi. Listede olup permissions'ta olmayan sunucu = tüm araçlar.
    """
    from backend.src.core.mcp_scopes import McpScope, scopes_from_row

    resolved: list[McpScope]
    if scopes is not None:
        resolved = list(scopes)
    else:
        resolved = scopes_from_row(server_slug, tool_names, all_tools)
    servers = [scope.server for scope in resolved if scope.server]
    if not servers:
        server = (server_slug or "").strip()
        servers = [server] if server else []
    permission: dict[str, object] = {"mcp_servers": servers}
    tool_perm: dict[str, list[str]] = {}
    for scope in resolved:
        if scope.all_tools or not scope.server:
            continue
        tool_perm[scope.server] = list(scope.tools)
    if tool_perm:
        permission["mcp_tool_permissions"] = tool_perm
    body: dict[str, object] = {
        "key_alias": key_alias,
        "models": list(MCP_NO_LLM_MODELS),
        "object_permission": permission,
        "metadata": dict(metadata or {}),
    }
    if team_id and team_id.strip():
        body["team_id"] = team_id.strip()
    return body


async def generate_litellm_virtual_key(
    *,
    key_alias: str,
    models: list[str] | None,
    team_id: str | None,
    max_parallel_requests: int | None = None,
    environment: str | None = None,
    metadata: Mapping[str, object] | None = None,
    auto_create_team: bool = False,
) -> tuple[str, str]:
    """Canlı ``POST /key/generate``. Dönüş: ``(plaintext_key, provider_id)``.

    ``auto_create_team=True`` ise eşleşmeyen ``team_id``/isim için LiteLLM'de
    gerçek bir team oluşturulur (batch create akışı); ``False`` ise eşleşmeyen
    isim :class:`LiteLLMKeyError` fırlatır (ham string provider'a geçmez).
    """
    import os

    import httpx

    from backend.src.core.litellm.target import resolve_litellm_http

    base, credential = resolve_litellm_http(environment, kind="litellm")
    path = os.getenv("LITELLM_KEY_GENERATE_PATH", "/key/generate").strip() or "/key/generate"
    if not path.startswith("/"):
        path = "/" + path
    if not base or not credential:
        raise LiteLLMKeyError("LiteLLM base URL veya master key yok", retryable=False)

    resolved_team = ""
    if team_id and team_id.strip():
        resolved_team = await resolve_or_create_team_id(
            base=base, credential=credential, name=team_id, auto_create=auto_create_team,
        )

    url = f"{base.rstrip('/')}{path}"
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        body = build_key_generate_body(
            key_alias=key_alias,
            models=list(models or []),
            team_id=resolved_team or None,
            max_parallel_requests=max_parallel_requests,
            metadata=metadata,
        )
        try:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {credential}"},
                json=body,
            )
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise LiteLLMKeyError(f"LiteLLM unreachable: {exc}", retryable=True) from exc
        snippet = (response.text or "")[:500]
        if response.status_code in {429, 502, 503, 504}:
            raise LiteLLMKeyError(
                f"LiteLLM http {response.status_code}: {snippet}",
                retryable=True,
            )
        if response.status_code >= 400:
            raise LiteLLMKeyError(
                f"LiteLLM http {response.status_code}: {snippet}",
                retryable=False,
            )
        try:
            data = response.json()
        except ValueError as exc:
            raise LiteLLMKeyError("LiteLLM non-json response", retryable=True) from exc
    plaintext = str(data.get("key") or data.get("token") or "").strip()
    provider_id = str(data.get("token_id") or data.get("key_id") or "")
    if not plaintext:
        raise LiteLLMKeyError("LiteLLM response missing key", retryable=False)
    return plaintext, provider_id


def parse_key_info_payload(payload: object) -> dict[str, Any]:
    """`GET /key/info` hem düz dict hem `{info: {...}}` dönebilir."""
    if not isinstance(payload, dict):
        return {}
    info = payload.get("info")
    if isinstance(info, dict):
        return info
    return payload


def _models_from_info(raw: object) -> list[str]:
    if isinstance(raw, (list, tuple)):
        return [str(item).strip() for item in raw if str(item).strip()]
    text = str(raw or "").strip()
    if not text:
        return []
    return [part.strip() for part in text.split(",") if part.strip()]


@dataclass
class LiteLLMKeyInfo:
    key_alias: str
    team_id: str
    models: list[str]
    max_parallel_requests: int | None
    blocked: bool


def key_info_from_payload(payload: object) -> LiteLLMKeyInfo:
    info = parse_key_info_payload(payload)
    parallel_raw = info.get("max_parallel_requests")
    parallel: int | None
    try:
        parallel = int(parallel_raw) if parallel_raw not in (None, "") else None
    except (TypeError, ValueError):
        parallel = None
    return LiteLLMKeyInfo(
        key_alias=str(info.get("key_alias") or info.get("key_name") or "").strip(),
        team_id=str(info.get("team_id") or info.get("team_alias") or "").strip(),
        models=_models_from_info(info.get("models")),
        max_parallel_requests=parallel,
        blocked=bool(info.get("blocked")),
    )


async def fetch_key_info(
    *,
    api_key: str,
    environment: str | None,
) -> LiteLLMKeyInfo | None:
    """`GET /key/info?key=`. 404 → None."""
    import httpx

    from backend.src.core.litellm.target import resolve_litellm_http

    token = (api_key or "").strip()
    if not token:
        return None
    base, credential = resolve_litellm_http(environment, kind="litellm")
    if not base or not credential:
        raise LiteLLMKeyError("LiteLLM base URL veya master key yok", retryable=False)
    url = f"{base.rstrip('/')}/key/info"
    try:
        async with httpx.AsyncClient(timeout=15.0, trust_env=False) as client:
            response = await client.get(
                url,
                params={"key": token},
                headers={"Authorization": f"Bearer {credential}"},
            )
    except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
        raise LiteLLMKeyError(f"LiteLLM unreachable: {exc}", retryable=True) from exc
    if response.status_code == 404:
        return None
    snippet = (response.text or "")[:500]
    if response.status_code in {429, 502, 503, 504}:
        raise LiteLLMKeyError(f"LiteLLM http {response.status_code}: {snippet}", retryable=True)
    if response.status_code >= 400:
        raise LiteLLMKeyError(f"LiteLLM http {response.status_code}: {snippet}", retryable=False)
    try:
        payload = response.json()
    except ValueError as exc:
        raise LiteLLMKeyError("LiteLLM non-json response", retryable=True) from exc
    return key_info_from_payload(payload)


def build_key_update_body(
    *,
    api_key: str,
    team_id: str | None = None,
    max_parallel_requests: int | None = None,
    models: list[str] | None = None,
    blocked: bool | None = None,
    clear_metadata: bool = False,
    key_alias: str | None = None,
) -> dict[str, object]:
    """`POST /key/update` — yalnız set edilen alanlar.

    ``clear_metadata=True`` → ``metadata: {}`` gönderilir; LiteLLM
    `UpdateKeyRequest.metadata` alanı **tamamen değiştirir** (merge etmez),
    yani key'in eski metadata'sı (batch/webhook'tan gelen ``source``,
    ``ticket`` vb.) böylece silinir.

    ``key_alias`` verilirse `key_alias` set edilir — LiteLLM alias'ları
    global olarak unique tutar, çakışan bir alias 400 döner.
    """
    body: dict[str, object] = {"key": api_key.strip()}
    if team_id and team_id.strip():
        body["team_id"] = team_id.strip()
    if max_parallel_requests is not None:
        body["max_parallel_requests"] = int(max_parallel_requests)
    if models is not None:
        body["models"] = route_models_for_litellm(list(models))
    if blocked is True:
        body["blocked"] = True
    if clear_metadata:
        body["metadata"] = {}
    if key_alias and key_alias.strip():
        body["key_alias"] = key_alias.strip()
    return body


async def update_litellm_virtual_key(
    *,
    api_key: str,
    environment: str | None,
    team_id: str | None = None,
    max_parallel_requests: int | None = None,
    models: list[str] | None = None,
    blocked: bool | None = None,
    auto_create_team: bool = False,
    clear_metadata: bool = False,
    key_alias: str | None = None,
) -> dict[str, Any]:
    """Canlı ``POST /key/update``.

    ``team_id`` verilip LiteLLM'de eşleşen bir team bulunamazsa, ham string
    provider'a **gönderilmez**; ``auto_create_team=True`` değilse
    :class:`LiteLLMKeyError` fırlatılır (dropdown'dan gerçek id seçilmeli).
    ``clear_metadata=True`` → key'in ``metadata`` alanı boşaltılır.
    ``key_alias`` verilirse key'in alias'ı güncellenir (örn. batch'te eklenen
    satır numarasını temizlemek için — bkz. ``strip_batch_row_suffix``).
    """
    import httpx

    from backend.src.core.litellm.target import resolve_litellm_http

    token = (api_key or "").strip()
    if not token:
        raise LiteLLMKeyError("api_key boş", retryable=False)
    base, credential = resolve_litellm_http(environment, kind="litellm")
    if not base or not credential:
        raise LiteLLMKeyError("LiteLLM base URL veya master key yok", retryable=False)

    resolved_team = ""
    if team_id and team_id.strip():
        resolved_team = await resolve_or_create_team_id(
            base=base, credential=credential, name=team_id, auto_create=auto_create_team,
        )

    url = f"{base.rstrip('/')}/key/update"
    async with httpx.AsyncClient(timeout=30.0, trust_env=False) as client:
        body = build_key_update_body(
            api_key=token,
            team_id=resolved_team or None,
            max_parallel_requests=max_parallel_requests,
            models=models,
            blocked=blocked,
            clear_metadata=clear_metadata,
            key_alias=key_alias,
        )
        if set(body.keys()) == {"key"}:
            raise LiteLLMKeyError("güncellenecek alan yok", retryable=False)
        try:
            response = await client.post(
                url,
                headers={"Authorization": f"Bearer {credential}"},
                json=body,
            )
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise LiteLLMKeyError(f"LiteLLM unreachable: {exc}", retryable=True) from exc
        snippet = (response.text or "")[:500]
        if response.status_code == 404:
            raise LiteLLMKeyError("key not found", retryable=False)
        if response.status_code in {429, 502, 503, 504}:
            raise LiteLLMKeyError(f"LiteLLM http {response.status_code}: {snippet}", retryable=True)
        if response.status_code >= 400:
            raise LiteLLMKeyError(f"LiteLLM http {response.status_code}: {snippet}", retryable=False)
        try:
            return response.json() if response.content else {}
        except ValueError:
            return {}


__all__ = [
    "LITELLM_MODEL_ROUTES",
    "MCP_NO_LLM_MODELS",
    "TEAM_LIST_PATH",
    "TEAM_NEW_PATH",
    "LiteLLMKeyError",
    "LiteLLMKeyInfo",
    "build_key_generate_body",
    "build_key_update_body",
    "build_mcp_key_generate_body",
    "create_litellm_team",
    "fetch_key_info",
    "fetch_litellm_teams",
    "generate_litellm_virtual_key",
    "key_info_from_payload",
    "match_team_id",
    "mcp_key_generate_path",
    "parse_key_info_payload",
    "parse_team_list",
    "resolve_or_create_team_id",
    "route_models_for_litellm",
    "teams_for_ui",
    "update_litellm_virtual_key",
]
