"""Hexagonal domain numaraları — application katmanının tek tanımı.

Legacy ``genai_orion_panel_core.domain.enums`` ve
``…/utils/VALID_ACTIONS_BY_TYPE`` referansları bu modülden karşılanır.

Kapsam (bu tur):

* :class:`RequestType` — talep tipi.
* :class:`RequestStatus` — durum yöneticisi (transitions modülü sonraki tur).
* :class:`ApprovalAction` — mail/UI tarafındaki capability tipi.
* :class:`OutboxJobType` — dispatcher condsumer key'leri.
* :class:`Environment` — TEST/PROD (yerel staging).
* :data:`VALID_ACTIONS_BY_TYPE` — tip → izinli eylemler eşlemesi.

Eklenecekler (sonraki tur):

* :func:`is_terminal` ve :func:`assert_action_allowed` →
  :mod:`backend.src.domain.transitions`.
* :class:`Request` / :class:`LiteLLMKeyDetail` / :class:`MCPKeyDetail` /
  :class:`RegistryDetail` → :mod:`backend.src.domain.entities.request`.
* :class:`RequestRevision` → :mod:`backend.src.domain.entities.request_revision`.
* :class:`ApprovalToken` → :mod:`backend.src.domain.entities.approval_token`.

Değer uyumu: refactor turu öncesi ``data/db/models/...`` içinde yazılı
sabit verilerle (``requests.status`` CHECK constraint'i gibi) bire bir
aynıdır. ``genai_orion_panel_request`` kolonundaki değerlerle de aynı.
"""

from __future__ import annotations

from enum import Enum
from typing import Mapping


class RequestType(str, Enum):
    """Panel tarafından alınan talebin tipi.

    Dış API'de string literal olarak dolaşır (``request_type`` alanı);
    Enum OR-equals kullanır → ``if x in RequestType.*``.
    """

    LITELLM_KEY = "litellm_key"
    MCP_KEY = "mcp_key"
    MCP_SERVER_REGISTRY = "mcp_server_registry"


class RequestStatus(str, Enum):
    """Talep durum yöneticisi (legacy durum makinesi bire bir)."""

    RECEIVED = "received"
    WAITING_APPROVAL = "waiting_approval"
    ASSIGNED = "assigned"
    PROVISIONING = "provisioning"
    COMPLETED = "completed"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"
    FAILED = "failed"


class ApprovalAction(str, Enum):
    """Approval capability token'ının içerdiği eylem."""

    APPROVE = "approve"
    REVISE = "revise"
    REJECT = "reject"


class OutboxJobType(str, Enum):
    """Worker dispatcher üzerinden worker'lara gönderilen iş tipleri.

    Legacy ``JOB_TYPE_*`` string sabitleriyle bire bir aynı; mapper'a
    gerek kalmadan doğrudan ``.value`` üzerinden tüketilir.
    """

    PROVISION_LITELLM_KEY = "provision:litellm_key"
    PROVISION_MCP_KEY = "provision:mcp_key"
    REGISTER_MCP_SERVER = "registry:mcp_server"
    SEND_RESULT_MAIL = "send:result_mail"
    SEND_APPROVAL_MAIL = "send:approval_mail"
    SEND_LITELLM_DOWN_NOTICE = "send:litellm_down_notice"


class Environment(str, Enum):
    """Web panelinden gelen ortam bilgisi (TEST/PROD)."""

    TEST = "TEST"
    PROD = "PROD"


# ---- Type → izinli eylemler eşlemesi -------------------------------------

VALID_ACTIONS_BY_TYPE: Mapping[RequestType, frozenset[ApprovalAction]] = {
    RequestType.LITELLM_KEY: frozenset({ApprovalAction.APPROVE, ApprovalAction.REVISE, ApprovalAction.REJECT}),
    RequestType.MCP_KEY: frozenset({ApprovalAction.APPROVE, ApprovalAction.REJECT}),
    RequestType.MCP_SERVER_REGISTRY: frozenset({ApprovalAction.APPROVE, ApprovalAction.REJECT}),
}


# ---- Generic access -----------------------------------------------------

def is_terminal(status: RequestStatus | str) -> bool:
    """Verilen durum terminallerden mi (handler tekrar çalışmamalı)?.

    Legacy ``genai_orion_panel_core.domain.transitions.is_terminal``'in
    birebir minimal karşılığı. Genişletildiğinde domain kuralları
    (pending→revision, vs.) bu modülden uygulanır.
    """
    if isinstance(status, str):
        try:
            status = RequestStatus(status)
        except ValueError:
            return False
    return status in _TERMINAL_STATUSES


_TERMINAL_STATUSES: frozenset[RequestStatus] = frozenset(
    {
        RequestStatus.COMPLETED,
        RequestStatus.REJECTED,
        RequestStatus.FAILED,
    }
)


__all__ = [
    "ApprovalAction",
    "Environment",
    "OutboxJobType",
    "RequestStatus",
    "RequestType",
    "VALID_ACTIONS_BY_TYPE",
    "is_terminal",
]
