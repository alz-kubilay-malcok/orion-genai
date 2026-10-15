"""LiteLLM / MCP `key_alias` — baseline §6 naming.

LiteLLM (ortak)::

    ALZ-{DEPARTMENT}-{ENVIRONMENT}-{PROJECT}-{PURPOSE}
    örn. ``ALZ-GENAI-PROD-HD12345-AGENTIC``

LiteLLM (bireysel: ortam ``BIREYSEL`` / ``BRYSL`` / ``BRSYL``)::

    ALZ-{DEPARTMENT}-BRYSL-{ISIM}-{PROJECT}-{PURPOSE}

MCP key: ``ALZ-MCP-{DEPARTMENT}-{NORMALIZED_TICKET}-{ENVIRONMENT}-{SERVER_SLUG}``
  örn. ``ALZ-MCP-HASAR-HD22334-TEST-HASAR-BILGI``
"""

from __future__ import annotations

import hashlib
import re
from typing import Mapping

_MAX_ALIAS_LEN = 128
_MAX_PROJECT_LEN = 15
_TR_FOLD = str.maketrans({
    "ç": "c", "Ç": "C",
    "ğ": "g", "Ğ": "G",
    "ı": "i", "İ": "I",
    "ö": "o", "Ö": "O",
    "ş": "s", "Ş": "S",
    "ü": "u", "Ü": "U",
})
_MULTI_DASH = re.compile(r"-{2,}")
_BIREYSEL_ENVS = frozenset({"BIREYSEL", "BRYSL", "BRSYL"})
_CODER_MODELS = frozenset({"allianz-coder", "text2test"})
_PURPOSE_TOKENS = {
    "RAG": "AGENTIC",
    "CHAT": "CHATBOT",
    "AGENT": "AGENTIC",
    "DIGERI": "OTHER",
    "KUBEFLOW": "KUBEFLOW",
    "CODER": "CODER",
    "IDP": "IDP",
    "CHATBOT": "CHATBOT",
    "AGENTIC": "AGENTIC",
    "OTHER": "OTHER",
}


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


def _is_bireysel(environment: object) -> bool:
    token = "".join(ch for ch in _fold(environment) if ch.isalnum())
    return token in _BIREYSEL_ENVS


_NON_ALNUM = re.compile(r"[^A-Z0-9]+")
_VOWELS = re.compile(r"[AEIOU]")


def _project_segment(value: object) -> str:
    """Proje segmenti (api_key_migration.xlsx → api_key_alias kuralları).

    - Türkçe karakterler katlanır, büyük harf, sadece harf/rakam (tire yok).
    - En fazla 15 karakter. Sığıyorsa olduğu gibi kalır.
    - Sığmıyorsa her kelimenin ilk harfi korunup kalan sesli harfler atılır
      (``internal assistai`` → ``INTRNLASSST``), sonra 15'e kesilir.
    """
    words = [w for w in _NON_ALNUM.split(_fold(value)) if w]
    if not words:
        return "NA"
    joined = "".join(words)
    if len(joined) <= _MAX_PROJECT_LEN:
        return joined
    short = "".join(w[0] + _VOWELS.sub("", w[1:]) for w in words)
    return short[:_MAX_PROJECT_LEN]


def litellm_purpose_token(purpose: object, models: object = None) -> str:
    """Orion ``kullanim_amaci`` / model listesi → alias purpose segmenti.

    Bilinen amaç eşlenir. Eşlenmezse ve modellerde ``allianz-coder`` veya
    ``text2test`` varsa ``CODER``, aksi halde ``OTHER``.
    """
    mapped = _PURPOSE_TOKENS.get(_fold(purpose))
    if mapped:
        return mapped
    names: set[str] = set()
    if isinstance(models, (list, tuple)):
        names = {str(item).strip().casefold() for item in models if str(item).strip()}
    if names & _CODER_MODELS:
        return "CODER"
    return "OTHER"


def build_litellm_key_alias(
    *,
    department: object,
    environment: object,
    project: object,
    purpose: object,
    person: object = None,
) -> str:
    """Yeni LiteLLM alias. Bireyselde ortam yerine ``BRYSL-{ISIM}`` yazılır."""
    dept = _segment(department)
    proj = _project_segment(project)
    purp = _segment(purpose)
    if _is_bireysel(environment):
        parts = ("ALZ", dept, "BRYSL", _segment(person), proj, purp)
    else:
        parts = ("ALZ", dept, _segment(environment), proj, purp)
    return _bound("-".join(parts))


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
    project = _pick(src, "project_name")
    if project in (None, ""):
        project = _segment(ticket, alnum_only=True)
    return build_litellm_key_alias(
        department=department,
        environment=environment,
        project=project,
        purpose=litellm_purpose_token(
            _pick(src, "purpose_code", "purpose_text"),
            _pick(src, "models"),
        ),
        person=_pick(src, "requester_name"),
    )


__all__ = [
    "build_litellm_key_alias",
    "build_mcp_key_alias",
    "key_alias_for_request",
    "litellm_purpose_token",
]
