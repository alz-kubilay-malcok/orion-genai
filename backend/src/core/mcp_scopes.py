"""MCP key kapsamı — tek veya birden fazla sunucu.

Kalıcılık (migration yok):
  * ``mcp_server_slug`` virgülle birleşik sunucu adları
  * tek sunucu: ``mcp_tool_names`` düz liste (eski satırlar)
  * çoklu: ``mcp_tool_names`` ``sunucu::araç`` veya ``sunucu::*`` (tüm araçlar)
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping


SCOPE_SEP = "::"
ALL_TOOLS_MARK = "*"
SLUG_JOIN = ","


@dataclass(frozen=True, slots=True)
class McpScope:
    server: str
    tools: tuple[str, ...]
    all_tools: bool


def _clean_server(value: object) -> str:
    return str(value or "").strip()


def _clean_tools(value: object) -> tuple[str, ...]:
    if not isinstance(value, list):
        return ()
    out: list[str] = []
    seen: set[str] = set()
    for item in value:
        name = str(item).strip()
        if not name or name in seen:
            continue
        seen.add(name)
        out.append(name)
    return tuple(out)


def _as_server_list(mcp_sunucusu: object) -> list[str]:
    if mcp_sunucusu is None or mcp_sunucusu == "":
        return []
    if isinstance(mcp_sunucusu, str):
        name = mcp_sunucusu.strip()
        return [name] if name else []
    if isinstance(mcp_sunucusu, list):
        out: list[str] = []
        seen: set[str] = set()
        for item in mcp_sunucusu:
            name = _clean_server(item)
            if not name:
                continue
            key = name.casefold()
            if key in seen:
                raise ValueError(f"mcp_sunucusu tekrar ediyor: {name}")
            seen.add(key)
            out.append(name)
        return out
    raise ValueError("mcp_sunucusu string veya dizi olmalı")


def _scope_from_erisim(row: Mapping[str, Any]) -> McpScope:
    server = _clean_server(row.get("mcp_sunucusu"))
    if not server:
        raise ValueError("erisimler[].mcp_sunucusu boş olamaz")
    all_tools = bool(row.get("tum_araclara_erisim"))
    tools = _clean_tools(row.get("araclar"))
    if all_tools and tools:
        raise ValueError(
            f"{server}: tum_araclara_erisim=true iken araclar boş olmalı"
        )
    if not all_tools and not tools:
        raise ValueError(
            f"{server}: tum_araclara_erisim=false iken en az bir araç gerekli"
        )
    return McpScope(server=server, tools=() if all_tools else tools, all_tools=all_tools)


def normalize_scopes(
    *,
    mcp_sunucusu: object = None,
    araclar: object = None,
    tum_araclara_erisim: object = None,
    erisimler: object = None,
) -> list[McpScope]:
    """Orion wire → kanonik kapsam listesi. Hata = ValueError (422)."""
    if erisimler is not None:
        if not isinstance(erisimler, list) or not erisimler:
            raise ValueError("erisimler boş olamaz")
        if mcp_sunucusu not in (None, "", []) or araclar not in (None, [], {}):
            raise ValueError("erisimler varken mcp_sunucusu/araclar gönderme")
        scopes = [_scope_from_erisim(row) for row in erisimler if isinstance(row, Mapping)]
        if len(scopes) != len(erisimler):
            raise ValueError("erisimler öğeleri nesne olmalı")
        seen: set[str] = set()
        for scope in scopes:
            key = scope.server.casefold()
            if key in seen:
                raise ValueError(f"mcp_sunucusu tekrar ediyor: {scope.server}")
            seen.add(key)
        return scopes

    servers = _as_server_list(mcp_sunucusu)
    if not servers:
        raise ValueError("mcp_sunucusu zorunlu")

    all_map: dict[str, bool] = {}
    if isinstance(tum_araclara_erisim, dict):
        for key, flag in tum_araclara_erisim.items():
            name = _clean_server(key)
            if name:
                all_map[name.casefold()] = bool(flag)
        global_all = False
    else:
        global_all = bool(tum_araclara_erisim)

    tools_by_server: dict[str, tuple[str, ...]] = {}
    if isinstance(araclar, dict):
        for key, names in araclar.items():
            server = _clean_server(key)
            if not server:
                continue
            tools_by_server[server.casefold()] = _clean_tools(names)
    elif isinstance(araclar, list):
        if len(servers) > 1 and not global_all:
            raise ValueError(
                "birden fazla mcp_sunucusu için araclar nesne olmalı "
                "({sunucu: [araç, ...]}) veya erisimler kullan"
            )
        tools_by_server[servers[0].casefold()] = _clean_tools(araclar)
    elif araclar not in (None,):
        raise ValueError("araclar dizi veya {sunucu: [araç]} nesnesi olmalı")

    scopes: list[McpScope] = []
    for server in servers:
        folded = server.casefold()
        all_tools = global_all or all_map.get(folded, False)
        tools = tools_by_server.get(folded, ())
        if all_tools and tools:
            raise ValueError(
                f"{server}: tum_araclara_erisim=true iken araclar boş olmalı"
            )
        if not all_tools and not tools:
            raise ValueError(
                f"{server}: tum_araclara_erisim=false iken en az bir araç gerekli"
            )
        scopes.append(
            McpScope(server=server, tools=() if all_tools else tools, all_tools=all_tools)
        )
    extra = set(tools_by_server) - {s.casefold() for s in servers}
    if extra:
        raise ValueError(f"araclar içinde mcp_sunucusu olmayan sunucu: {sorted(extra)}")
    return scopes


def persist_fields(scopes: list[McpScope]) -> dict[str, Any]:
    if not scopes:
        raise ValueError("mcp kapsamı boş")
    slug = SLUG_JOIN.join(scope.server for scope in scopes)
    all_tools = all(scope.all_tools for scope in scopes)
    if len(scopes) == 1:
        scope = scopes[0]
        tools = [] if scope.all_tools else list(scope.tools)
        return {
            "mcp_server_slug": slug,
            "mcp_tool_names": tools,
            "all_tools": scope.all_tools,
        }
    encoded: list[str] = []
    for scope in scopes:
        if scope.all_tools:
            encoded.append(f"{scope.server}{SCOPE_SEP}{ALL_TOOLS_MARK}")
        else:
            encoded.extend(f"{scope.server}{SCOPE_SEP}{name}" for name in scope.tools)
    return {
        "mcp_server_slug": slug,
        "mcp_tool_names": encoded,
        "all_tools": all_tools,
    }


def scopes_from_row(
    slug: object,
    tools: object,
    all_tools: object = False,
) -> list[McpScope]:
    servers = [part.strip() for part in str(slug or "").split(SLUG_JOIN) if part.strip()]
    raw_tools = [str(item).strip() for item in (tools or []) if str(item).strip()]
    prefixed = [item for item in raw_tools if SCOPE_SEP in item]
    if prefixed:
        grouped: dict[str, list[str] | None] = {}
        order: list[str] = []
        for item in prefixed:
            server, _, name = item.partition(SCOPE_SEP)
            server = server.strip()
            name = name.strip()
            if not server:
                continue
            key = server.casefold()
            if key not in grouped:
                grouped[key] = []
                order.append(server)
            if name == ALL_TOOLS_MARK:
                grouped[key] = None
            elif grouped[key] is not None and name:
                grouped[key].append(name)
        for server in servers:
            if server.casefold() not in grouped:
                order.append(server)
                grouped[server.casefold()] = [] if not all_tools else None
        scopes: list[McpScope] = []
        for server in order:
            bucket = grouped[server.casefold()]
            if bucket is None:
                scopes.append(McpScope(server=server, tools=(), all_tools=True))
            else:
                scopes.append(McpScope(server=server, tools=tuple(bucket), all_tools=False))
        return scopes
    if not servers:
        return []
    if all_tools:
        return [McpScope(server=name, tools=(), all_tools=True) for name in servers]
    if len(servers) > 1:
        raise ValueError("çoklu mcp_sunucusu için araçlar sunucu::araç formatında olmalı")
    return [McpScope(server=servers[0], tools=tuple(raw_tools), all_tools=False)]


def scope_label(scopes: list[McpScope]) -> str:
    parts: list[str] = []
    for scope in scopes:
        if scope.all_tools:
            parts.append(f"{scope.server}: tüm araçlar")
        else:
            parts.append(f"{scope.server}: {', '.join(scope.tools)}")
    return "; ".join(parts)


__all__ = [
    "ALL_TOOLS_MARK",
    "McpScope",
    "SCOPE_SEP",
    "SLUG_JOIN",
    "normalize_scopes",
    "persist_fields",
    "scope_label",
    "scopes_from_row",
]
