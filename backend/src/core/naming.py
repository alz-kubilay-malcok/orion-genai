"""LiteLLM / MCP `key_alias` — baseline §6 naming.

LiteLLM: ``ALZ-{DEPARTMENT}-{NORMALIZED_TICKET}-{ENVIRONMENT}-{PURPOSE}``
  örn. ``ALZ-GENAI-HD12345-DEV-RAG``

MCP key: ``ALZ-MCP-{DEPARTMENT}-{NORMALIZED_TICKET}-{ENVIRONMENT}-{SERVER_SLUG}``
  örn. ``ALZ-MCP-HASAR-HD22334-TEST-HASAR-BILGI``
"""

from __future__ import annotations

import hashlib
import re
from typing import Mapping

_MAX_ALIAS_LEN = 128
_TR_FOLD = str.maketrans({
    "ç": "c", "Ç": "C",
    "ğ": "g", "Ğ": "G",
    "ı": "i", "İ": "I",
    "ö": "o", "Ö": "O",
    "ş": "s", "Ş": "S",
    "ü": "u", "Ü": "U",
})
_MULTI_DASH = re.compile(r"-{2,}")


def _fold(value: object) -> str:
    return str(value or "").translate(_TR_FOLD).upper().strip()


def _segment(value: object, *, alnum_only: bool = False) -> str:
    folded = _fold(value)
    if not folded:
        return "NA"
    if alnum_only:
        text = "".join(ch for ch in folded if ch.isalnum())
        return text or "NA"
    text = "".join(ch if ch.isalnum() else "-" for ch in folded)
    text = _MULTI_DASH.sub("-", text).strip("-")
    return text or "NA"


def _bound(alias: str) -> str:
    if len(alias) <= _MAX_ALIAS_LEN:
        return alias
    digest = hashlib.sha256(alias.encode("utf-8")).hexdigest()[:8]
    keep = _MAX_ALIAS_LEN - 9
    return f"{alias[:keep].rstrip('-')}-{digest}"


def build_litellm_key_alias(
    *,
    department: object,
    ticket: object,
    environment: object,
    purpose: object,
) -> str:
    return _bound("-".join((
        "ALZ",
        _segment(department),
        _segment(ticket, alnum_only=True),
        _segment(environment),
        _segment(purpose),
    )))


def build_mcp_key_alias(
    *,
    department: object,
    ticket: object,
    environment: object,
    server_slug: object,
) -> str:
    return _bound("-".join((
        "ALZ",
        "MCP",
        _segment(department),
        _segment(ticket, alnum_only=True),
        _segment(environment),
        _segment(server_slug),
    )))


def _pick(src: object, *names: str) -> object:
    if isinstance(src, Mapping):
        for name in names:
            value = src.get(name)
            if value not in (None, ""):
                return value
        return None
    for name in names:
        value = getattr(src, name, None)
        if value not in (None, ""):
            return value
    return None


def key_alias_for_request(src: object, request_type: str | None = None) -> str:
    """ORM satırı veya field dict → deterministic alias."""
    kind = request_type or str(_pick(src, "request_type") or "")
    department = _pick(src, "department_name")
    ticket = _pick(src, "genai_orion_panel_ticket_id")
    environment = _pick(src, "environment")
    if kind == "mcp_key":
        return build_mcp_key_alias(
            department=department,
            ticket=ticket,
            environment=environment,
            server_slug=_pick(src, "mcp_server_slug", "server_slug"),
        )
    return build_litellm_key_alias(
        department=department,
        ticket=ticket,
        environment=environment,
        purpose=_pick(src, "purpose_code", "purpose_text"),
    )


__all__ = [
    "build_litellm_key_alias",
    "build_mcp_key_alias",
    "key_alias_for_request",
]
