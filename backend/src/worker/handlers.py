"""Worker outbox handler facade'leri.

Handler sözleşmesi: ``async def handle(*, session, payload) -> None``.
Success → exception yok; Failure → `WorkerError` alt sınıfı raise eder.

Handler dispatch edilirken dispatcher transaction'a girmez; handler'lar
kendi iç transaction sınırlarını kendileri yönetir (provision handler'ları
`run_provision_job` üzerinden kendi UoW'unu açar).

`OUTBOX_HANDLERS` modül-load sırasında boştur; dispatcher her tick'te
`build_handlers(deps)` callable'ı ile per-process handler tablosunu kurup
dispatch sırasında kullanır. Bu sayede adapter yükleme sırası dispatch'tan
ayrılmış olur.
"""

from __future__ import annotations

import json
import logging
import uuid
from typing import Awaitable, Callable

from sqlalchemy.ext.asyncio import AsyncSession

from .dependencies import WorkerDependencies
from .errors import PermanentError, RetryHeld

logger = logging.getLogger(__name__)

# Domain enum (`OutboxJobType`) editable-install break yüzünden
# bu turda import edilemiyor (packages/genai-orion-panel-core yolu
# diskte yok). String literal dispatch key'lerini burada
# daraltıyoruz; rationale:
#   - outbox_jobs.job_type TEXT; bu value'lar authoritative.
#   - `genai_orion_panel_core` editable broken; yeni backend bu tur
#     kapsamında reference etmiyoruz. Eski import patch outbox
#     dispatch refactor'u ile merge edilecek.
JOB_TYPE_PROVISION_LITELLM = "provision:litellm_key"
JOB_TYPE_PROVISION_MCP = "provision:mcp_key"
JOB_TYPE_SEND_RESULT_MAIL = "send:result_mail"
JOB_TYPE_REGISTER_MCP = "registry:mcp_server"
JOB_TYPE_APPROVAL_MAIL = "send:approval_mail"
JOB_TYPE_LITELLM_DOWN_NOTICE = "send:litellm_down_notice"


# ---- Closure-bindable HANDLERS -------------------------------------------


def build_handlers(deps: WorkerDependencies) -> dict[str, Callable[..., Awaitable[None]]]:
    """Per-process handler dispatch tablosu — `deps` injection'lı."""
    return {
        JOB_TYPE_PROVISION_LITELLM: _make_provision_litellm_handler(deps),
        JOB_TYPE_PROVISION_MCP: _make_provision_mcp_handler(deps),
        JOB_TYPE_SEND_RESULT_MAIL: _make_send_result_mail_handler(deps),
        JOB_TYPE_REGISTER_MCP: handle_register_mcp,
        JOB_TYPE_APPROVAL_MAIL: _make_send_approval_mail_handler(deps),
        JOB_TYPE_LITELLM_DOWN_NOTICE: _make_send_litellm_down_notice_handler(deps),
    }


def _make_provision_litellm_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_provision_litellm(session=session, deps=deps, payload=payload)
    return handler


def _make_provision_mcp_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_provision_mcp(session=session, deps=deps, payload=payload)
    return handler


def _make_send_result_mail_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await handle_send_result_mail(session=session, deps=deps, payload=payload)
    return handler


def _make_send_approval_mail_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_send_approval_mail(session=session, deps=deps, payload=payload)
    return handler


def _make_send_litellm_down_notice_handler(deps):
    async def handler(*, session: AsyncSession, payload: dict) -> None:
        await _handle_send_litellm_down_notice(
            session=session, deps=deps, payload=payload,
        )
    return handler


# Salt public yüz: legacy import'lar için. Modül load anında boş tablo;
# dispatcher `build_handlers(deps)` kullanır.
OUTBOX_HANDLERS: dict[str, Callable[..., Awaitable[None]]] = {}


# ---- Handlers -----------------------------------------------------------


async def handle_send_result_mail(
    *,
    session: AsyncSession,
    payload: dict,
    deps: WorkerDependencies | None = None,
    api_key: str = "",
) -> None:
    """Talep sonuç mailini talep sahibine atar.

    Payload: `{request_id, job_type, schema_version}`.
    `requests` tablosundan detaylar okunur; status türe göre template seçilir.
    Plaintext key outbox'ta yok; varsa `secrets` satırından decrypt edilir.
    """
    request_id = _require_uuid(payload, "request_id")
    from ..core.mailing.mailer import send_mail
    from ..core.mailing.result_inputs import (
        litellm_result_inputs,
        mcp_result_inputs,
        result_template_name,
    )
    request = await _load_request(session, request_id)
    if request is None:
        msg = f"request bulunamadı: {request_id}"
        raise PermanentError(msg)

    api_key = (api_key or "").strip()
    if not api_key:
        api_key = await _decrypt_request_secret(
            session, request_id=request_id, cipher=getattr(deps, "secret_cipher", None),
        )
    template = result_template_name(str(request["request_type"]))
    if request["request_type"] == "litellm_key":
        revision_before = await _load_latest_revision_snapshot(session, request_id)
        inputs = litellm_result_inputs(
            request, revision_before=revision_before, api_key=api_key,
        )
    else:
        inputs = mcp_result_inputs(request, api_key=api_key)
    subject = f"[GenAi] {request['genai_orion_panel_ticket_id']} — sonuç"
    try:
        ok = send_mail(
            recipients=[request["requester_email"]],
            subject=subject,
            template_name=template,
            inputs=inputs,
        )
    except FileNotFoundError as exc:
        raise PermanentError(str(exc)) from exc
    except Exception as exc:
        msg = f"smtp send failed: {exc}"
        raise RetryHeld(msg) from exc
    if not ok:
        msg = "mailer False döndü"
        raise RetryHeld(msg)
    logger.info(
        "send_result_mail: delivered",
        extra={"request_id": str(request_id), "to": request["requester_email"]},
    )


async def _handle_send_approval_mail(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    """Send one approval mail to the payload recipient using HMAC action URLs."""
    from ..core.mailing.mailer import send_mail

    request_id = _require_uuid(payload, "request_id")
    recipient = str(payload.get("recipient") or "").strip()
    if not recipient:
        msg = "approval mail payload'unda recipient eksik"
        raise PermanentError(msg)

    request = await _load_request(session, request_id)
    if request is None:
        msg = f"request bulunamadı: {request_id}"
        raise PermanentError(msg)

    action_urls = payload.get("action_urls") or {}
    token = str(payload.get("token") or "")
    viewer_base = str(payload.get("viewer_base") or "http://localhost:8058/approvals").rstrip("/")
    approve_link = action_urls.get("approve") or (f"{viewer_base}/{token}" if token else "")
    reject_link = action_urls.get("reject") or approve_link
    revise_link = action_urls.get("revise") or ""

    from ..core.mailing.approval_inputs import litellm_approval_inputs, mcp_approval_inputs

    is_mcp = request["request_type"] in {"mcp_key", "mcp_server_registry"}
    template = "mcp_key_approval" if is_mcp else "litellm_key_approval"
    inputs: dict[str, object]
    if is_mcp:
        inputs = mcp_approval_inputs(
            request,
            recipient=recipient,
            approve_link=approve_link,
            reject_link=reject_link,
        )
    else:
        inputs = dict(
            litellm_approval_inputs(
                request,
                recipient=recipient,
                approve_link=approve_link,
                reject_link=reject_link,
                revise_link=revise_link,
            )
        )
    try:
        ok = send_mail(
            recipients=[recipient],
            subject=f"[GenAi] {request['genai_orion_panel_ticket_id']} — onayınız bekleniyor",
            template_name=template,
            inputs=inputs,
        )
    except Exception as exc:
        msg = f"smtp send failed: {exc}"
        raise RetryHeld(msg) from exc
    if not ok:
        msg = "mailer False döndü"
        raise RetryHeld(msg)
    logger.info(
        "send_approval_mail: delivered",
        extra={"request_id": str(request_id), "to": recipient},
    )


async def _handle_send_litellm_down_notice(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    from ..core.mailing.mailer import send_mail

    recipients = list(payload.get("recipients") or [])
    if not recipients:
        msg = "litellm_down_notice recipients boş"
        raise PermanentError(msg)
    message = (
        payload.get("error_message")
        or payload.get("error_code")
        or "provisioning provider unavailable"
    )
    try:
        ok = send_mail(
            recipients=recipients,
            subject="[GenAi] provision/LiteLLM uyarısı",
            message=str(message),
        )
    except Exception as exc:
        msg = f"smtp send failed: {exc}"
        raise RetryHeld(msg) from exc
    if not ok:
        raise RetryHeld("mailer False döndü")
    logger.info("send_litellm_down_notice: delivered", extra={"to": recipients})


async def handle_register_mcp(*, session: AsyncSession, payload: dict) -> None:
    """Registry: env yoksa dry-run complete (secret yazılmaz)."""
    request_id = _require_uuid(payload, "request_id")
    await _complete_request(
        session,
        request_id,
        dry_run=True,
        write_secret=False,
        extra={"registry": "dry-run"},
    )


async def _handle_provision_litellm(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    request_id = _require_uuid(payload, "request_id")
    await _provision_credential(
        session,
        deps=deps,
        request_id=request_id,
        secret_type="litellm_key",
        kind="litellm",
    )


async def _handle_provision_mcp(
    *,
    session: AsyncSession,
    deps: WorkerDependencies,
    payload: dict,
) -> None:
    request_id = _require_uuid(payload, "request_id")
    await _provision_credential(
        session,
        deps=deps,
        request_id=request_id,
        secret_type="mcp_key",
        kind="mcp",
    )


async def _resolve_litellm_team_id(
    client: object,
    *,
    base: str,
    credential: str,
    team_name: str,
) -> str:
    """`GET /team/list` → alias/id eşleşmesi; yoksa adı `team_id` olarak geçir."""
    from ..core.litellm.generate_key import TEAM_LIST_PATH, match_team_id, parse_team_list

    name = team_name.strip()
    if not name:
        return ""
    url = f"{base.rstrip('/')}{TEAM_LIST_PATH}"
    try:
        response = await client.get(  # type: ignore[union-attr]
            url,
            headers={"Authorization": f"Bearer {credential}"},
        )
    except Exception:
        return name
    if response.status_code >= 400:
        return name
    try:
        payload = response.json()
    except ValueError:
        return name
    return match_team_id(parse_team_list(payload), name) or name


def _first_env(*names: str) -> str:
    import os

    for name in names:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return ""


def _litellm_env_for_request(environment: str | None) -> str:
    """MCP form `TEST` = LiteLLM `DEV`; STG/PROD aynı."""
    env = (environment or "DEV").upper()
    if env == "TEST":
        return "DEV"
    return env


def _provider_base(kind: str, environment: str | None) -> tuple[str, str, str]:
    """Return (base_url, credential, path). MCP keys de aynı LiteLLM proxy."""
    import os

    litellm_env = _litellm_env_for_request(environment)
    litellm_base = _first_env(f"LITELLM_BASE_URL_{litellm_env}", "LITELLM_BASE_URL")
    litellm_key = _first_env(f"LITELLM_MASTER_KEY_{litellm_env}", "LITELLM_MASTER_KEY")
    if kind == "litellm":
        path = os.getenv("LITELLM_KEY_GENERATE_PATH", "/key/generate").strip() or "/key/generate"
        return litellm_base.rstrip("/"), litellm_key, path
    env = (environment or "DEV").upper()
    base = (
        _first_env(f"MCP_GATEWAY_BASE_URL_{env}", "MCP_GATEWAY_BASE_URL")
        or litellm_base
    )
    key = (
        _first_env(f"MCP_GATEWAY_ADMIN_CREDENTIAL_{env}", "MCP_GATEWAY_ADMIN_CREDENTIAL")
        or litellm_key
    )
    path = os.getenv("MCP_GATEWAY_KEY_CREATE_PATH", "/mcp/keys/create").strip() or "/mcp/keys/create"
    return base.rstrip("/"), key, path


async def _provision_credential(
    session: AsyncSession,
    *,
    deps: WorkerDependencies,
    request_id: uuid.UUID,
    secret_type: str,
    kind: str,
) -> None:
    from sqlalchemy import select

    from ..data.db.models.requests import Request

    row = await session.scalar(select(Request).where(Request.id == request_id))
    if row is None:
        raise PermanentError(f"request bulunamadı: {request_id}")
    from ..domain.enums import is_terminal

    if is_terminal(row.status):
        logger.info("provision no-op: already terminal", extra={"request_id": str(request_id)})
        return

    from ..core.naming import key_alias_for_request

    alias = (row.key_alias or "").strip() or key_alias_for_request(row)
    if row.key_alias != alias:
        row.key_alias = alias
        await session.flush()

    base, credential, path = _provider_base(kind, row.environment)
    plaintext: str | None = None
    provider_id = f"dry-run-{request_id.hex[:12]}"
    if base and path and credential:
        import httpx

        from ..core.litellm.generate_key import build_key_generate_body

        url = f"{base}{path if path.startswith('/') else '/' + path}"
        metadata = {
            "request_id": str(request_id),
            "ticket": row.genai_orion_panel_ticket_id,
        }
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                if kind == "litellm":
                    team_name = (getattr(row, "litellm_team_id", None) or "").strip()
                    resolved_team = ""
                    if team_name:
                        resolved_team = await _resolve_litellm_team_id(
                            client,
                            base=base,
                            credential=credential,
                            team_name=team_name,
                        )
                    body = build_key_generate_body(
                        key_alias=alias,
                        models=list(row.models or []),
                        team_id=resolved_team or None,
                        max_parallel_requests=row.max_concurrent_requests,
                        metadata=metadata,
                    )
                else:
                    body = {
                        "key_alias": alias,
                        "models": row.models or [],
                        "metadata": metadata,
                    }
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {credential}"},
                    json=body,
                )
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            raise RetryHeld(f"{kind} unavailable: {exc}") from exc
        if response.status_code in {429, 502, 503, 504}:
            raise RetryHeld(f"{kind} http {response.status_code}")
        if response.status_code in {400, 401, 403}:
            raise PermanentError(f"{kind} http {response.status_code}")
        try:
            data = response.json()
        except ValueError as exc:
            raise RetryHeld(f"{kind} non-json response") from exc
        plaintext = str(data.get("key") or data.get("token") or "")
        provider_id = str(data.get("token_id") or data.get("key_id") or provider_id)
        if not plaintext:
            raise PermanentError(f"{kind} response missing key")
        logger.info("%s provision: live http ok", kind, extra={"request_id": str(request_id)})
    else:
        logger.info("%s provision: dry-run (no base/path/credential)", kind,
                    extra={"request_id": str(request_id)})

    await _complete_request(
        session,
        request_id,
        dry_run=plaintext is None,
        write_secret=plaintext is not None,
        plaintext=plaintext,
        provider_id=provider_id,
        secret_type=secret_type,
        cipher=deps.secret_cipher,
    )


async def _complete_request(
    session: AsyncSession,
    request_id: uuid.UUID,
    *,
    dry_run: bool,
    write_secret: bool,
    plaintext: str | None = None,
    provider_id: str | None = None,
    secret_type: str | None = None,
    cipher: object | None = None,
    extra: dict | None = None,
) -> None:
    from datetime import UTC, datetime

    from sqlalchemy import select

    from ..data.db.models.outbox_jobs import OutboxJob
    from ..data.db.models.requests import Request
    from ..data.db.models.secrets import Secret
    from ..domain.enums import RequestStatus, is_terminal

    row = await session.scalar(select(Request).where(Request.id == request_id))
    if row is None:
        raise PermanentError(f"request bulunamadı: {request_id}")
    if is_terminal(row.status):
        return
    now = datetime.now(UTC).replace(tzinfo=None)
    if write_secret and plaintext and cipher is not None and secret_type:
        envelope = cipher.encrypt(  # type: ignore[union-attr]
            plaintext.encode("utf-8"),
            aad=_secret_aad(request_id, secret_type),
        )
        session.add(Secret(
            id=uuid.uuid4(),
            request_id=request_id,
            secret_type=secret_type,
            provider_token_id=provider_id or "unknown",
            ciphertext=envelope.ciphertext,
            nonce=envelope.nonce,
            auth_tag=envelope.auth_tag,
            key_hint=plaintext[-4:] if len(plaintext) >= 4 else plaintext.ljust(4, "*"),
            key_version=envelope.key_version,
        ))
    elif write_secret and plaintext and cipher is None:
        logger.warning("secret_cipher missing; skipping persist of key")
    row.status = RequestStatus.COMPLETED.value
    row.updated_at = now
    row.completed_at = now
    row.version = int(row.version or 0) + 1
    if extra:
        row.error_message = None

    mailed = False
    if plaintext:
        try:
            await handle_send_result_mail(
                session=session,
                payload={"request_id": str(request_id)},
                api_key=plaintext,
            )
            mailed = True
        except Exception:
            logger.exception(
                "result mail immediate send failed; queueing",
                extra={"request_id": str(request_id)},
            )

    from sqlalchemy.exc import IntegrityError

    if mailed:
        await session.commit()
        logger.info(
            "provision complete",
            extra={"request_id": str(request_id), "dry_run": dry_run},
        )
        return

    try:
        async with session.begin_nested():
            session.add(OutboxJob(
                id=uuid.uuid4(),
                job_type=JOB_TYPE_SEND_RESULT_MAIL,
                aggregate_type="request",
                aggregate_id=request_id,
                payload=json.dumps({
                    "schema_version": 1,
                    "request_id": str(request_id),
                    "dry_run": dry_run,
                }),
                dedupe_key=f"result_mail:{request_id}:v1",
                status="pending",
                available_at=now,
                attempts=0,
                max_attempts=5,
                created_at=now,
                updated_at=now,
            ))
            await session.flush()
    except IntegrityError:
        logger.info("result_mail already queued for %s", request_id)
    await session.commit()
    logger.info(
        "provision complete",
        extra={"request_id": str(request_id), "dry_run": dry_run},
    )


# ---- Helpers ------------------------------------------------------------


def _secret_aad(request_id: uuid.UUID, secret_type: str) -> bytes:
    return f"{request_id}|{secret_type}|litellm".encode("utf-8")


async def _decrypt_request_secret(
    session: AsyncSession,
    *,
    request_id: uuid.UUID,
    cipher: object | None,
) -> str:
    """Sonuç maili için plaintext; yoksa veya çözülemezse boş string."""
    if cipher is None or not hasattr(cipher, "decrypt"):
        return ""
    from sqlalchemy import select

    from ..data.db.models.secrets import Secret

    secret = await session.scalar(select(Secret).where(Secret.request_id == request_id))
    if secret is None:
        return ""
    try:
        plaintext = cipher.decrypt(  # type: ignore[union-attr]
            secret.nonce,
            secret.ciphertext,
            secret.auth_tag,
            aad=_secret_aad(request_id, secret.secret_type),
            key_version=secret.key_version,
        )
    except Exception:
        logger.exception(
            "secret decrypt failed",
            extra={"request_id": str(request_id)},
        )
        return ""
    if isinstance(plaintext, bytes):
        return plaintext.decode("utf-8")
    return str(plaintext or "")


def _require_uuid(payload: dict, field: str) -> uuid.UUID:
    raw = payload.get(field)
    if not raw:
        msg = f"payload alanı eksik: {field}"
        raise PermanentError(msg)
    try:
        return uuid.UUID(str(raw))
    except ValueError as exc:
        msg = f"payload alanı UUID değil: {field}={raw!r}"
        raise PermanentError(msg) from exc


async def _load_request(session: AsyncSession, request_id: uuid.UUID) -> dict | None:
    from sqlalchemy import select

    from ..data.db.models.requests import Request

    row = await session.scalar(select(Request).where(Request.id == request_id))
    if row is None:
        return None
    return {
        "id": str(row.id),
        "request_type": row.request_type,
        "status": row.status,
        "version": row.version,
        "genai_orion_panel_ticket_id": row.genai_orion_panel_ticket_id,
        "genai_orion_panel_ticket_url": row.genai_orion_panel_ticket_url,
        "requester_name": row.requester_name,
        "requester_email": row.requester_email,
        "environment": row.environment,
        "department_name": getattr(row, "department_name", None),
        "purpose_text": getattr(row, "purpose_text", None),
        "purpose_code": getattr(row, "purpose_code", None),
        "models": getattr(row, "models", None),
        "max_concurrent_requests": getattr(row, "max_concurrent_requests", None),
        "response_window": getattr(row, "response_window", None),
        "usage_frequency": getattr(row, "usage_frequency", None),
        "litellm_team_id": getattr(row, "litellm_team_id", None),
        "key_alias": getattr(row, "key_alias", None),
        "mcp_server_slug": getattr(row, "mcp_server_slug", None),
        "mcp_server_display_name": getattr(row, "mcp_server_display_name", None),
        "mcp_tool_names": getattr(row, "mcp_tool_names", None),
        "all_tools": getattr(row, "all_tools", None),
        "registry_allows_all_tools": getattr(row, "registry_allows_all_tools", None),
        "reject_reason": getattr(row, "reject_reason", None),
        "error_message": getattr(row, "error_message", None),
        "created_at": row.created_at.isoformat() if getattr(row, "created_at", None) else "",
        "completed_at": row.completed_at.isoformat() if getattr(row, "completed_at", None) else "",
    }


async def _load_latest_revision_snapshot(
    session: AsyncSession, request_id: uuid.UUID,
) -> dict[str, object] | None:
    """Revize öncesi client-facing snapshot; yoksa None (sonuç mailinde diff yok)."""
    from sqlalchemy import select

    from ..data.db.models.request_revisions import RequestRevision

    row = await session.scalar(
        select(RequestRevision)
        .where(RequestRevision.request_id == request_id)
        .order_by(RequestRevision.version.desc())
        .limit(1)
    )
    if row is None:
        return None
    raw = row.snapshot
    if isinstance(raw, dict):
        return raw
    if not isinstance(raw, str) or not raw.strip():
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        logger.warning("revision snapshot JSON değil: request_id=%s", request_id)
        return None
    return parsed if isinstance(parsed, dict) else None


async def _load_approver_emails(session: AsyncSession) -> list[str]:
    from sqlalchemy import select

    from ..data.db.models.config_approvers import ConfigApprover

    rows = await session.scalars(
        select(ConfigApprover.email)
        .where(
            ConfigApprover.scope == "GENAI_APPROVAL",
            ConfigApprover.is_active.is_(True),
        )
        .order_by(ConfigApprover.sort_order.asc())
    )
    return list(rows.all())
