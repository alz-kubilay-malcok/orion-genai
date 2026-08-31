"""Admin panel: token'sız approve/revise/reject akışları (Bölüm 10.3).

Refactor (2026-08-25): legacy ``genai_orion_panel_core.UnitOfWork``
bağımlılığı sıfırlandı. Şu anki katman doğrudan
``backend.src.data.db.models.requests.Request`` ORM modeli üzerinden
çalışır; legacy ``req.detail``/``req.apply_status`` çağrıları bypass
edilir.

Davranış sözleşmesi:

* Token-based işlemler için ``approval_actions.py`` rotası kullanılır;
  bu modülde **token yok**, yalnız admin panel POST'ları.
* Aynı transaction sınırı: ``requests`` UPDATE + ``request_revisions``
  INSERT (revise ise) + ``outbox_jobs`` INSERT + ``audit_events`` INSERT.
  Commit çağıran rota yapar (mail token consume ile tek transaction).
* Hatalar :mod:`backend.src.domain.errors` üzerinden raise edilir;
  FastAPI route'ları ``DomainError`` → HTTP ``{401,409,422}`` eşlemesi
  yapar (ayrıntı: ``routes/admin.py::_DOMAIN_ERROR_STATUS``).

Notlar:

* Request lifecycle audit ``audit_events`` (request_id FK). LDAP mapping
  CRUD ayrı ``audit_log`` tablosuna yazar.
* RequestRevision tablosu ``snapshot`` TEXT — JSON-serialised string.
"""

from __future__ import annotations

import json
import logging
import uuid
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Mapping

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.src.data.db.models.audit_events import AuditEvent
from backend.src.data.db.models.outbox_jobs import OutboxJob
from backend.src.data.db.models.request_revisions import RequestRevision
from backend.src.data.db.models.requests import Request
from backend.src.domain.enums import (
    ApprovalAction,
    OutboxJobType,
    RequestStatus,
    RequestType,
)
from backend.src.domain.errors import (
    ActionNotAllowedForTypeError,
    OptimisticLockConflictError,
    RequestNotFoundError,
)

logger = logging.getLogger(__name__)

# ---- sabitler ---------------------------------------------------------

LITELLM_CLIENT_FACING_FIELDS: tuple[str, ...] = (
    "models", "response_window", "usage_frequency",
)

_JOB_BY_TYPE: dict[str, str] = {
    RequestType.LITELLM_KEY.value: OutboxJobType.PROVISION_LITELLM_KEY.value,
    RequestType.MCP_KEY.value: OutboxJobType.PROVISION_MCP_KEY.value,
    RequestType.MCP_SERVER_REGISTRY.value: OutboxJobType.REGISTER_MCP_SERVER.value,
}

_DEDUPE_PREFIX_BY_JOB: dict[str, str] = {
    OutboxJobType.PROVISION_LITELLM_KEY.value: "provision:litellm",
    OutboxJobType.PROVISION_MCP_KEY.value: "provision:mcp",
    OutboxJobType.REGISTER_MCP_SERVER.value: "registry:mcp",
    OutboxJobType.SEND_RESULT_MAIL.value: "result_mail",
}

# ---- result dataclass -------------------------------------------------


@dataclass(slots=True)
class _ActionResult:
    request_id: uuid.UUID
    new_status: str        # str (ORM'un kabul ettiği değer)
    snapshot_taken: bool = False


# ---- internal helpers -------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _valid_action_values(rtype: RequestType) -> frozenset[str]:
    from backend.src.domain.enums import VALID_ACTIONS_BY_TYPE
    return frozenset(a.value for a in VALID_ACTIONS_BY_TYPE.get(rtype, frozenset()))


async def _load_for_action(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    action: ApprovalAction,
    request_version: int,
    for_update: bool = True,
) -> Request:
    stmt = select(Request).where(Request.id == request_id)
    if for_update:
        stmt = stmt.with_for_update()
    req = (await session.execute(stmt)).scalar_one_or_none()
    if req is None:
        raise RequestNotFoundError("talep bulunamadı")

    try:
        rtype = RequestType(req.request_type)
    except ValueError as exc:
        raise ActionNotAllowedForTypeError(
            f"bilinmeyen talep tipi: {req.request_type!r}"
        ) from exc

    allowed = _valid_action_values(rtype)
    if action.value not in allowed:
        raise ActionNotAllowedForTypeError(
            f"{rtype.value} tipi için {action.value} eylemi geçerli değil"
        )

    if req.version != request_version:
        raise OptimisticLockConflictError("version uyuşmuyor (stale)")

    if req.status != RequestStatus.WAITING_APPROVAL.value:
        raise ActionNotAllowedForTypeError(
            f"talep durumu {req.status!r}; waiting_approval bekleniyor"
        )
    return req


def _dedupe_key_for(request_id: uuid.UUID, job_type_value: str) -> str:
    prefix = _DEDUPE_PREFIX_BY_JOB.get(job_type_value, "job")
    return f"{prefix}:{request_id}:v1"


async def _enqueue_request_job(
    session: AsyncSession, *,
    request_id: uuid.UUID,
    job_type_value: str,
    extra: Mapping[str, object] | None = None,
) -> None:
    payload: dict[str, object] = {
        "job_type": job_type_value,
        "request_id": str(request_id),
        "schema_version": 1,
    }
    if extra:
        payload.update(extra)
    job = OutboxJob(
        id=uuid.uuid4(),
        job_type=job_type_value,
        aggregate_type="request",
        aggregate_id=request_id,
        payload=json.dumps(payload),
        dedupe_key=_dedupe_key_for(request_id, job_type_value),
        status="pending",
        attempts=0,
        max_attempts=5,
        available_at=_utcnow(),
    )
    session.add(job)
    await session.flush()


async def _record_audit(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    event_type: str,
    actor_id: str,
    request_version: int,
    metadata: Mapping[str, object] | None = None,
    correlation_id: str | None = None,
) -> None:
    actor_type = "mail_token" if str(actor_id).startswith("token:") else "admin_user"
    entry = AuditEvent(
        id=uuid.uuid4(),
        request_id=request_id,
        event_type=event_type,
        actor_type=actor_type,
        actor_id=actor_id,
        request_version=request_version,
        metadata_json=json.dumps(dict(metadata or {}), default=str),
        correlation_id=correlation_id,
        created_at=_utcnow(),
    )
    session.add(entry)
    await session.flush()


# ---- public API -------------------------------------------------------


async def admin_approve(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    request_version: int,
    allows_all_tools: bool | None,
    actor_id: str,
    correlation_id: str | None,
) -> _ActionResult:
    """Approve akışı (token'sız, admin panel).

    * LITELLM_KEY: formdaki `max_concurrent_requests` LiteLLM
      `max_parallel_requests` olur; team yoksa key teamsiz üretilir.
    * MCP_SERVER_REGISTRY: ``registry_allows_all_tools`` mutate.
    * Status PROVISIONING; audit + outbox atomik.
    """
    req = await _load_for_action(
        session,
        request_id=request_id,
        action=ApprovalAction.APPROVE,
        request_version=request_version,
    )

    rtype = RequestType(req.request_type)
    now = _utcnow()

    if rtype is RequestType.LITELLM_KEY:
        if not (req.litellm_team_id or "").strip() and (req.department_name or "").strip():
            req.litellm_team_id = req.department_name.strip()
    elif rtype is RequestType.MCP_SERVER_REGISTRY:
        req.registry_allows_all_tools = bool(allows_all_tools)

    req.status = RequestStatus.PROVISIONING.value
    req.updated_at = now
    req.version = req.version + 1

    await _record_audit(
        session,
        request_id=req.id,
        event_type="request_approved",
        actor_id=actor_id,
        request_version=req.version,
        metadata={"allows_all_tools": allows_all_tools} if allows_all_tools is not None else {},
        correlation_id=correlation_id,
    )

    await _enqueue_request_job(
        session, request_id=req.id, job_type_value=_JOB_BY_TYPE[req.request_type],
    )

    return _ActionResult(
        request_id=req.id, new_status=RequestStatus.PROVISIONING.value,
    )


async def admin_revise(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    request_version: int,
    team_id: str,
    max_parallel_requests: int,
    admin_note: str | None,
    models: list[str] | None,
    response_window: str | None,
    usage_frequency: str | None,
    actor_id: str,
    correlation_id: str | None,
) -> _ActionResult:
    """Revise (sadece litellm_key): LiteLLM team + max_parallel_requests."""
    team = (team_id or "").strip()
    if not team:
        raise ValueError("team_id boş olamaz")
    if max_parallel_requests < 1:
        raise ValueError("max_parallel_requests en az 1 olmalı")

    updates: dict[str, object] = {
        "litellm_team_id": team,
        "max_concurrent_requests": max_parallel_requests,
    }
    if models is not None:
        updates["models"] = tuple(models)
    if response_window is not None:
        updates["response_window"] = response_window
    if usage_frequency is not None:
        updates["usage_frequency"] = usage_frequency

    req = await _load_for_action(
        session,
        request_id=request_id,
        action=ApprovalAction.REVISE,
        request_version=request_version,
    )
    if req.request_type != RequestType.LITELLM_KEY.value:
        raise ActionNotAllowedForTypeError("Revise yalnız litellm_key için geçerlidir")

    now = _utcnow()
    snapshot_fields = (
        "litellm_team_id",
        "max_concurrent_requests",
        *LITELLM_CLIENT_FACING_FIELDS,
    )
    snapshot: dict[str, object] = {}
    for field in snapshot_fields:
        value = getattr(req, field)
        snapshot[field] = list(value) if isinstance(value, tuple) else value
    revision = RequestRevision(
        id=uuid.uuid4(),
        request_id=req.id,
        version=req.version,
        snapshot=json.dumps(snapshot, ensure_ascii=False, default=str),
        created_at=now,
    )
    session.add(revision)
    for f, v in updates.items():
        setattr(req, f, v)

    req.status = RequestStatus.PROVISIONING.value
    req.updated_at = now
    req.version = req.version + 1

    audit_meta: dict[str, object] = {
        "team_id": team,
        "max_parallel_requests": max_parallel_requests,
    }
    if admin_note is not None:
        audit_meta["admin_note"] = admin_note
    client_facing = {
        k: list(v) if isinstance(v, tuple) else v
        for k, v in updates.items()
        if k in LITELLM_CLIENT_FACING_FIELDS
    }
    if client_facing:
        audit_meta["client_facing_updates"] = client_facing

    await _record_audit(
        session,
        request_id=req.id,
        event_type="request_revised",
        actor_id=actor_id,
        request_version=req.version,
        metadata=audit_meta,
        correlation_id=correlation_id,
    )

    await _enqueue_request_job(
        session,
        request_id=req.id,
        job_type_value=_JOB_BY_TYPE[RequestType.LITELLM_KEY.value],
    )

    return _ActionResult(
        request_id=req.id,
        new_status=RequestStatus.PROVISIONING.value,
        snapshot_taken=True,
    )


async def admin_reject(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    request_version: int,
    reject_reason: str,
    actor_id: str,
    correlation_id: str | None,
) -> _ActionResult:
    """Reject akışı (admin panel). Status -> REJECTED."""
    if not reject_reason or len(reject_reason) > 2000:
        raise ValueError("reject_reason 1..2000 karakter olmalı")

    req = await _load_for_action(
        session,
        request_id=request_id,
        action=ApprovalAction.REJECT,
        request_version=request_version,
    )

    now = _utcnow()
    req.reject_reason = reject_reason
    req.status = RequestStatus.REJECTED.value
    req.updated_at = now
    req.version = req.version + 1

    await _record_audit(
        session,
        request_id=req.id,
        event_type="request_rejected",
        actor_id=actor_id,
        request_version=req.version,
        metadata={"reject_reason": reject_reason},
        correlation_id=correlation_id,
    )

    await _enqueue_request_job(
        session,
        request_id=req.id,
        job_type_value=OutboxJobType.SEND_RESULT_MAIL.value,
    )

    return _ActionResult(
        request_id=req.id, new_status=RequestStatus.REJECTED.value,
    )


__all__ = [
    "admin_approve",
    "admin_reject",
    "admin_revise",
    "LITELLM_CLIENT_FACING_FIELDS",
]
