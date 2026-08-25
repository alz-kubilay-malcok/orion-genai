"""Admin panel için token'sız approve/revise/reject (pilot ekleme, baseline dışı).

Aynı domain kurallarını (`transitions.py`, `enums.py`) kullanır ancak
signed approval token yerine session-authenticated admin kullanıcısını
actor olarak kaydeder. `waiting_approval` dışı statüde no-op yerine hata
döner (panel zaten terminal talepleri göstermemelidir).
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from genai_orion_panel_core.application.ports.unit_of_work import UnitOfWork
from genai_orion_panel_core.domain.entities.request import LiteLLMKeyDetail
from genai_orion_panel_core.domain.entities.request_revision import (
    LITELLM_CLIENT_FACING_FIELDS,
    RequestRevision,
)
from genai_orion_panel_core.domain.enums import ApprovalAction, OutboxJobType, RequestStatus, RequestType
from genai_orion_panel_core.domain.errors import (
    ActionNotAllowedForTypeError,
    DomainError,
)
from genai_orion_panel_core.domain.transitions import assert_action_allowed, assert_awaiting_approval

_JOB_BY_TYPE: dict[RequestType, OutboxJobType] = {
    RequestType.LITELLM_KEY: OutboxJobType.PROVISION_LITELLM_KEY,
    RequestType.MCP_KEY: OutboxJobType.PROVISION_MCP_KEY,
    RequestType.MCP_SERVER_REGISTRY: OutboxJobType.REGISTER_MCP_SERVER,
}
_DEDUPE_PREFIX_BY_JOB: dict[OutboxJobType, str] = {
    OutboxJobType.PROVISION_LITELLM_KEY: "provision:litellm",
    OutboxJobType.PROVISION_MCP_KEY: "provision:mcp",
    OutboxJobType.REGISTER_MCP_SERVER: "registry:mcp",
}


class RequestNotFoundError(DomainError):
    error_code = "NOT_FOUND"


class OptimisticLockConflictError(DomainError):
    error_code = "OPTIMISTIC_LOCK_CONFLICT"


class LiteLLMEstimateMissingError(DomainError):
    error_code = "LITELLM_ESTIMATE_MISSING"


async def _load_for_action(
    uow: UnitOfWork, *, request_id: UUID, action: ApprovalAction, request_version: int
):
    request = await uow.requests.get_by_id(request_id, for_update=True)
    if request is None:
        msg = "talep bulunamadı"
        raise RequestNotFoundError(msg)
    assert_action_allowed(request.request_type, action)
    if request.version != request_version:
        msg = "request version optimistic lock uyuşmuyor"
        raise OptimisticLockConflictError(msg)
    assert_awaiting_approval(request.status)
    return request


async def admin_approve(
    uow: UnitOfWork,
    *,
    request_id: UUID,
    request_version: int,
    allows_all_tools: bool | None,
    actor_id: str,
    correlation_id: str | None,
) -> tuple[UUID, RequestStatus]:
    async with uow:
        request = await _load_for_action(
            uow, request_id=request_id, action=ApprovalAction.APPROVE, request_version=request_version
        )
        now = datetime.now(UTC)
        if request.request_type == RequestType.LITELLM_KEY:
            detail = request.detail
            if detail.estimated_peak_tpm <= 0 or detail.estimated_peak_rpm <= 0:
                msg = "estimate yok/zero; Approve gösterilemez, Revise kullanılmalı"
                raise LiteLLMEstimateMissingError(msg)
            detail.tpm_approved = detail.estimated_peak_tpm
            detail.rpm_approved = detail.estimated_peak_rpm
        elif request.request_type == RequestType.MCP_SERVER_REGISTRY:
            request.detail.registry_allows_all_tools = bool(allows_all_tools)

        request.apply_status(RequestStatus.PROVISIONING)
        request.updated_at = now
        await uow.requests.update(request)

        await uow.audit.record(
            request_id=request.id,
            event_type="request_approved",
            actor_type="admin_user",
            actor_id=actor_id,
            request_version=request.version,
            metadata={},
            correlation_id=correlation_id,
        )

        job_type = _JOB_BY_TYPE[request.request_type]
        prefix = _DEDUPE_PREFIX_BY_JOB[job_type]
        await uow.outbox.enqueue(
            job_type=job_type,
            aggregate_id=request.id,
            payload={"job_type": job_type.value, "request_id": str(request.id), "schema_version": 1},
            dedupe_key=f"{prefix}:{request.id}:v1",
        )

        await uow.commit()
        return request.id, request.status


async def admin_revise(
    uow: UnitOfWork,
    *,
    request_id: UUID,
    request_version: int,
    tpm_approved: int,
    rpm_approved: int,
    admin_note: str | None,
    models: list[str] | None,
    response_window: str | None,
    usage_frequency: str | None,
    actor_id: str,
    correlation_id: str | None,
) -> tuple[UUID, RequestStatus, bool]:
    """Admin panel revise akışı (token'sız).

    Client-facing alanlar için None geçilirse alana dokunulmaz; boş list/str
    ise bilinçli sıfırlama kabul edilir. Dönüş tuple'ı son eleman
    ``snapshot_taken``: True ise requestera diff maili çıkacak.
    """
    if tpm_approved <= 0 or rpm_approved <= 0:
        msg = "tpm_approved ve rpm_approved pozitif olmalı"
        raise ValueError(msg)
    updates: dict[str, object] = {}
    if models is not None:
        updates["models"] = tuple(models)
    if response_window is not None:
        updates["response_window"] = response_window
    if usage_frequency is not None:
        updates["usage_frequency"] = usage_frequency
    unknown = set(updates) - set(LITELLM_CLIENT_FACING_FIELDS)
    if unknown:
        msg = f"Bilinmeyen client-facing alanlar: {sorted(unknown)}"
        raise ValueError(msg)

    async with uow:
        request = await _load_for_action(
            uow, request_id=request_id, action=ApprovalAction.REVISE, request_version=request_version
        )
        if request.request_type != RequestType.LITELLM_KEY:
            msg = "Revise yalnız litellm_key için geçerlidir"
            raise ActionNotAllowedForTypeError(msg)
        detail = request.detail
        assert isinstance(detail, LiteLLMKeyDetail)  # noqa: S101

        now = datetime.now(UTC)
        snapshot_taken = False
        if updates:
            snapshot = {
                field_name: _read_detail_field(detail, field_name)
                for field_name in LITELLM_CLIENT_FACING_FIELDS
            }
            await uow.request_revisions.add(
                RequestRevision(
                    id=uuid.uuid4(),
                    request_id=request.id,
                    version=request.version,
                    snapshot=snapshot,
                )
            )
            snapshot_taken = True
            for field_name, value in updates.items():
                setattr(detail, field_name, value)

        detail.tpm_approved = tpm_approved
        detail.rpm_approved = rpm_approved

        request.apply_status(RequestStatus.PROVISIONING)
        request.updated_at = now
        await uow.requests.update(request)

        await uow.audit.record(
            request_id=request.id,
            event_type="request_revised",
            actor_type="admin_user",
            actor_id=actor_id,
            request_version=request.version,
            metadata=_admin_revise_audit_metadata(admin_note, updates),
            correlation_id=correlation_id,
        )

        job_type = _JOB_BY_TYPE[RequestType.LITELLM_KEY]
        prefix = _DEDUPE_PREFIX_BY_JOB[job_type]
        await uow.outbox.enqueue(
            job_type=job_type,
            aggregate_id=request.id,
            payload={"job_type": job_type.value, "request_id": str(request.id), "schema_version": 1},
            dedupe_key=f"{prefix}:{request.id}:v1",
        )

        await uow.commit()
        return request.id, request.status, snapshot_taken


def _admin_revise_audit_metadata(
    admin_note: str | None, updates: dict[str, object]
) -> dict[str, object]:
    meta: dict[str, object] = {}
    if admin_note is not None:
        meta["admin_note"] = admin_note
    if updates:
        meta["client_facing_updates"] = {
            key: list(value) if isinstance(value, tuple) else value
            for key, value in updates.items()
        }
    return meta


def _read_detail_field(detail: LiteLLMKeyDetail, field_name: str) -> object:
    if field_name == "models":
        return list(detail.models)
    if field_name == "response_window":
        return detail.response_window
    if field_name == "usage_frequency":
        return detail.usage_frequency
    msg = f"Desteklenmeyen client-facing alan: {field_name}"
    raise AssertionError(msg)


async def admin_reject(
    uow: UnitOfWork,
    *,
    request_id: UUID,
    request_version: int,
    reject_reason: str,
    actor_id: str,
    correlation_id: str | None,
) -> tuple[UUID, RequestStatus]:
    reason = reject_reason.strip()
    if not (1 <= len(reason) <= 2000):
        msg = "reject_reason 1..2000 karakter arasında olmalıdır"
        raise ValueError(msg)

    async with uow:
        request = await _load_for_action(
            uow, request_id=request_id, action=ApprovalAction.REJECT, request_version=request_version
        )
        now = datetime.now(UTC)
        request.apply_status(RequestStatus.REJECTED)
        request.reject_reason = reason
        request.updated_at = now
        await uow.requests.update(request)

        await uow.audit.record(
            request_id=request.id,
            event_type="request_rejected",
            actor_type="admin_user",
            actor_id=actor_id,
            request_version=request.version,
            metadata={"reject_reason": reason},
            correlation_id=correlation_id,
        )

        await uow.outbox.enqueue(
            job_type=OutboxJobType.SEND_RESULT_MAIL,
            aggregate_id=request.id,
            payload={
                "job_type": OutboxJobType.SEND_RESULT_MAIL.value,
                "request_id": str(request.id),
                "schema_version": 1,
            },
            dedupe_key=f"send_result_mail:{request.id}:v1",
        )

        await uow.commit()
        return request.id, request.status
