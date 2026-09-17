"""Mock LiteLLM admin + MCP Gateway API.

Worker'ın çağırdığı yüzey:

* ``POST /key/generate``
* ``GET  /key/info``
* ``POST /key/update``
* ``GET  /team/list``
* ``POST /mcp/keys/create``
* ``PUT  /mcp/servers/upsert``
* ``GET  /v1/mcp/server``
* ``GET  /mcp-rest/tools/list``

Auth: ``Authorization: Bearer $LITELLM_ACCESS_KEY``.
``MOCK_LITELLM_AUTH_OFF=1`` ile kapatılır.
"""

from __future__ import annotations

import json
import os
import secrets
import threading
from collections.abc import Iterable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

DEFAULT_ACCESS_KEY = "asd123"
DEFAULT_KEY_TTL_DAYS = 90

_DATA_DIR = Path(__file__).resolve().parent / "_data"
_STATE_FILE = _DATA_DIR / "keys.json"


def _env_bool(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


# Process-local re-entrant lock guarding the in-memory + file state.
_STATE_RLOCK = threading.RLock()


def _load_state() -> dict[str, Any]:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    if not _STATE_FILE.exists():
        return {"llm_keys": {}, "mcp_keys": {}, "mcp_servers": {}, "log": []}
    with _STATE_FILE.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def _save_state(state: dict[str, Any]) -> None:
    _DATA_DIR.mkdir(parents=True, exist_ok=True)
    tmp = _STATE_FILE.with_suffix(".json.tmp")
    with tmp.open("w", encoding="utf-8") as handle:
        json.dump(state, handle, indent=2, sort_keys=True)
    tmp.replace(_STATE_FILE)


# ---------------------------------------------------------------------------
# Request / response models — must match what the adapters actually post.
# ---------------------------------------------------------------------------


class KeyGenerateRequest(BaseModel):
    key_alias: str = Field(min_length=1)
    models: list[str] = Field(default_factory=list)
    team_id: str | None = None
    max_parallel_requests: int | None = None
    duration: str = "90d"
    key_type: str = "llm_api"
    metadata: dict[str, Any] = Field(default_factory=dict)
    tags: list[str] = Field(default_factory=list)


class KeyUpdateRequest(BaseModel):
    key: str = Field(min_length=1)
    team_id: str | None = None
    max_parallel_requests: int | None = None
    models: list[str] | None = None
    blocked: bool | None = None
    key_alias: str | None = None


class MCPKeyCreateRequest(BaseModel):
    key_alias: str = Field(min_length=1)
    server_slug: str = Field(min_length=1)
    tool_names: list[str] = Field(default_factory=list)
    all_tools: bool = False
    requester_email: str | None = None


class MCPServerUpsertRequest(BaseModel):
    environment: str
    slug: str = Field(min_length=1)
    display_name: str = Field(min_length=1)
    endpoint_url: str = Field(min_length=1)
    allows_all_tools: bool = False
    tools: list[str] = Field(default_factory=list)


class FailureInject(BaseModel):
    next_status: int | None = Field(default=None, ge=100, le=599)
    next_count: int = Field(default=1, ge=1)
    path_prefix: str = "/"


_INJECTED_FAILURES: list[dict[str, Any]] = []


def _consume_injected_failure(path: str) -> int | None:
    """Pop the next injected failure for this path if one is scheduled."""
    with _STATE_RLOCK:
        remaining: list[dict[str, Any]] = []
        chosen: int | None = None
        for item in _INJECTED_FAILURES:
            if chosen is None and path.startswith(item.get("path_prefix", "/")):
                item["next_count"] -= 1
                if item["next_count"] <= 0:
                    chosen = int(item["next_status"])
                else:
                    remaining.append(item)
            else:
                remaining.append(item)
        _INJECTED_FAILURES[:] = remaining
        return chosen


def _record_event(state: dict[str, Any], kind: str, **fields: Any) -> None:
    entry = {"ts": _utc_now_iso(), "kind": kind, **fields}
    state.setdefault("log", []).append(entry)
    # Cap log to 500 events so the JSON file does not grow unbounded during demos.
    if len(state["log"]) > 500:
        state["log"] = state["log"][-500:]


def _enforce_auth(request: Request) -> None:
    expected = os.getenv("LITELLM_ACCESS_KEY", DEFAULT_ACCESS_KEY)
    if _env_bool("MOCK_LITELLM_AUTH_OFF"):
        return
    header = request.headers.get("authorization", "")
    token = header.removeprefix("Bearer ").strip()
    if not token or (expected and token != expected):
        # Match real LiteLLM behavior: 401 on bad creds.
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, detail="Invalid master key")


def create_app() -> FastAPI:
    application = FastAPI(title="Mock LiteLLM", version="0.1.0")

    @application.middleware("http")
    async def _inject_failures_middleware(request: Request, call_next):  # type: ignore[no-untyped-def]
        status_code = _consume_injected_failure(request.url.path)
        if status_code is not None:
            return JSONResponse(
                status_code=status_code,
                content={"error": f"mock injected {status_code}"},
            )
        return await call_next(request)

    @application.get("/health/live")
    async def health_live() -> dict[str, str]:
        return {"status": "alive"}

    @application.post("/__mock/failures", status_code=status.HTTP_204_NO_CONTENT)
    async def set_failures(spec: FailureInject) -> None:
        _INJECTED_FAILURES.append(spec.model_dump())

    @application.post("/key/generate", dependencies=[Depends(_enforce_auth)])
    async def key_generate(payload: KeyGenerateRequest) -> dict[str, Any]:
        if not payload.models:
            # Mirror LiteLLM: 400 helps the adapter's `classify_http_error` land
            # in `LiteLLMValidationError`.
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="models cannot be empty")

        with _STATE_RLOCK:
            state = _load_state()
            token_id = "llm-key-" + secrets.token_hex(8)
            plaintext = f"sk-orion-mock-{secrets.token_hex(16)}"
            record = {
                "key_alias": payload.key_alias,
                "models": payload.models,
                "team_id": payload.team_id,
                "max_parallel_requests": payload.max_parallel_requests,
                "duration": payload.duration,
                "key_type": payload.key_type,
                "metadata": payload.metadata,
                "tags": payload.tags,
                "key": plaintext,
                "token_id": token_id,
                "blocked": False,
                "created_at": _utc_now_iso(),
            }
            state["llm_keys"][payload.key_alias] = record
            _record_event(
                state,
                "key.generate",
                key_alias=payload.key_alias,
                token_id=token_id,
                models=payload.models,
            )
            _save_state(state)
        return {
            "key": plaintext,
            "token_id": token_id,
            "key_name": payload.key_alias,
            "models": payload.models,
            "expires": _duration_to_iso(payload.duration),
        }

    @application.get("/team/list", dependencies=[Depends(_enforce_auth)])
    async def team_list() -> dict[str, Any]:
        """LiteLLM `GET /team/list` şekli — `{teams: [{team_id, team_alias}]}`."""
        with _STATE_RLOCK:
            state = _load_state()
            extra = list(state.get("teams") or [])
        teams = [
            {"team_id": "GENAI", "team_alias": "GENAI"},
            {"team_id": "demo-team", "team_alias": "Demo Team"},
            *extra,
        ]
        return {"teams": teams}

    @application.get("/key/info", dependencies=[Depends(_enforce_auth)])
    async def key_info(
        key: str | None = None,
        key_alias: str | None = None,
    ) -> dict[str, Any]:
        with _STATE_RLOCK:
            state = _load_state()
            records = list(state.get("llm_keys", {}).values())
        record = None
        needle = (key or "").strip()
        alias = (key_alias or "").strip()
        if needle:
            for item in records:
                if str(item.get("key") or "") == needle:
                    record = item
                    break
        elif alias:
            record = state.get("llm_keys", {}).get(alias)
        else:
            raise HTTPException(status.HTTP_400_BAD_REQUEST, detail="key or key_alias required")
        if not record:
            raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown key")
        info = {k: v for k, v in record.items() if k != "key"}
        return {"info": info}

    @application.post("/key/update", dependencies=[Depends(_enforce_auth)])
    async def key_update(payload: KeyUpdateRequest) -> dict[str, Any]:
        with _STATE_RLOCK:
            state = _load_state()
            found_alias = None
            record = None
            for alias, item in state.get("llm_keys", {}).items():
                if str(item.get("key") or "") == payload.key:
                    found_alias = alias
                    record = item
                    break
            if record is None:
                raise HTTPException(status.HTTP_404_NOT_FOUND, detail="unknown key")
            if payload.team_id is not None:
                record["team_id"] = payload.team_id
            if payload.max_parallel_requests is not None:
                record["max_parallel_requests"] = payload.max_parallel_requests
            if payload.models is not None:
                record["models"] = payload.models
            if payload.blocked is True:
                record["blocked"] = True
            if payload.key_alias:
                record["key_alias"] = payload.key_alias
            state["llm_keys"][found_alias] = record
            _record_event(
                state,
                "key.update",
                key_alias=record.get("key_alias"),
                token_id=record.get("token_id"),
            )
            _save_state(state)
        return {"info": {k: v for k, v in record.items() if k != "key"}}

    @application.post("/mcp/keys/create", dependencies=[Depends(_enforce_auth)])
    async def mcp_keys_create(payload: MCPKeyCreateRequest) -> dict[str, Any]:
        server_exists = False
        with _STATE_RLOCK:
            state = _load_state()
            server_exists = payload.server_slug in state["mcp_servers"]
            key_id = "mcp-key-" + secrets.token_hex(8)
            credential = f"mcp-{secrets.token_hex(20)}"
            record = {
                "key_id": key_id,
                "credential": credential,
                "key_alias": payload.key_alias,
                "server_slug": payload.server_slug,
                "tool_names": payload.tool_names,
                "all_tools": payload.all_tools,
                "requester_email": payload.requester_email,
                "server_known_to_gateway": server_exists,
                "created_at": _utc_now_iso(),
            }
            state["mcp_keys"][payload.key_alias] = record
            _record_event(
                state,
                "mcp.key.create",
                key_alias=payload.key_alias,
                key_id=key_id,
                server_slug=payload.server_slug,
                tool_count=len(payload.tool_names) if not payload.all_tools else "all",
            )
            _save_state(state)
        return record

    @application.put("/mcp/servers/upsert", dependencies=[Depends(_enforce_auth)])
    async def mcp_servers_upsert(payload: MCPServerUpsertRequest) -> dict[str, Any]:
        with _STATE_RLOCK:
            state = _load_state()
            existing = state["mcp_servers"].get(payload.slug)
            created = existing is None
            state["mcp_servers"][payload.slug] = {
                "server_id": existing["server_id"] if existing else "mcp-server-" + secrets.token_hex(6),
                "environment": payload.environment,
                "slug": payload.slug,
                "display_name": payload.display_name,
                "endpoint_url": payload.endpoint_url,
                "allows_all_tools": payload.allows_all_tools,
                "tools": list(payload.tools),
                "updated_at": _utc_now_iso(),
            }
            _record_event(
                state,
                "mcp.server.upsert",
                slug=payload.slug,
                environment=payload.environment,
                created=created,
                tool_count=len(payload.tools),
            )
            _save_state(state)
        return state["mcp_servers"][payload.slug] | {"created": created}

    # Admin / inspection endpoints — never called by the adapters but useful
    # for the Streamlit panel to demonstrate state.
    @application.get("/mcp/keys", dependencies=[Depends(_enforce_auth)])
    async def list_mcp_keys() -> list[dict[str, Any]]:
        with _STATE_RLOCK:
            return list(_load_state()["mcp_keys"].values())

    @application.get("/mcp/servers", dependencies=[Depends(_enforce_auth)])
    async def list_mcp_servers() -> list[dict[str, Any]]:
        with _STATE_RLOCK:
            return list(_load_state()["mcp_servers"].values())

    @application.get("/v1/mcp/server", dependencies=[Depends(_enforce_auth)])
    async def list_mcp_servers_v1() -> list[dict[str, Any]]:
        """Gerçek LiteLLM `GET /v1/mcp/server` şekli."""
        with _STATE_RLOCK:
            stored = list(_load_state()["mcp_servers"].values())
        return [
            {
                "server_id": row.get("server_id") or row.get("slug"),
                "server_name": row.get("slug") or row.get("server_name"),
                "alias": row.get("slug") or row.get("alias"),
                "display_name": row.get("display_name"),
                "url": row.get("endpoint_url"),
                "allowed_tools": list(row.get("tools") or []),
            }
            for row in stored
        ]

    @application.get("/mcp-rest/tools/list", dependencies=[Depends(_enforce_auth)])
    async def list_mcp_tools(server_id: str | None = None) -> dict[str, Any]:
        """Gerçek LiteLLM `GET /mcp-rest/tools/list` şekli."""
        with _STATE_RLOCK:
            stored = list(_load_state()["mcp_servers"].values())
        tools: list[dict[str, Any]] = []
        needle = (server_id or "").strip().casefold()
        for row in stored:
            slug = str(row.get("slug") or "")
            sid = str(row.get("server_id") or slug)
            if needle and needle not in {sid.casefold(), slug.casefold()}:
                continue
            for name in row.get("tools") or []:
                tools.append(
                    {
                        "name": name,
                        "mcp_info": {
                            "server_id": sid,
                            "server_name": slug,
                            "alias": slug,
                        },
                    }
                )
        return {"tools": tools, "error": None, "message": "Successfully retrieved tools"}

    @application.get("/__mock/log", dependencies=[Depends(_enforce_auth)])
    async def dump_log(limit: int = 50) -> list[dict[str, Any]]:
        with _STATE_RLOCK:
            log: Iterable[dict[str, Any]] = _load_state().get("log", [])
            return list(log)[-limit:]

    @application.delete("/__mock/state", dependencies=[Depends(_enforce_auth)])
    async def clear_state() -> dict[str, str]:
        with _STATE_RLOCK:
            _save_state({"llm_keys": {}, "mcp_keys": {}, "mcp_servers": {}, "log": []})
        return {"status": "cleared"}

    return application


def _duration_to_iso(duration: str) -> str:
    """Render "Nd" style durations the way LiteLLM does for `expires`."""
    days = DEFAULT_KEY_TTL_DAYS
    if duration.endswith("d") and duration[:-1].isdigit():
        days = int(duration[:-1])
    from datetime import timedelta

    expires = datetime.now(timezone.utc) + timedelta(days=days)
    return expires.isoformat(timespec="seconds")


def run() -> None:  # pragma: no cover - convenience entry point
    import uvicorn

    uvicorn.run(
        "mock_litellm.app:create_app",
        factory=True,
        host=os.getenv("MOCK_LITELLM_HOST", "127.0.0.1"),
        port=int(os.getenv("MOCK_LITELLM_PORT", "8200")),
    )


app = create_app()
