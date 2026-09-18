"""LiteLLM / MCP credential provision jobs."""

from __future__ import annotations

import json
import logging
import uuid

from sqlalchemy.ext.asyncio import AsyncSession

from ...domain.enums import OutboxJobType
from ..dependencies import WorkerDependencies
from ..errors import PermanentError, RetryHeld
from .common import _require_uuid, _secret_aad
from .mail import handle_send_result_mail

logger = logging.getLogger(__name__)
litellm_log = logging.getLogger("genai.litellm")

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
    """Team adı/alias → gerçek LiteLLM ``team_id``; yoksa ``/team/new`` ile oluşturur.

    Eskiden eşleşme bulunamazsa ham ad ``team_id`` olarak LiteLLM'e
    geçiriliyordu (var olmayan id → provider hata veriyordu). Artık
    :func:`resolve_or_create_team_id` gerçek bir team oluşturup id'sini
    kullanır; ``client`` parametresi geriye dönük uyumluluk için tutulur
    (kullanılmıyor, kendi client'ını açar).
    """
    from ...core.litellm.generate_key import LiteLLMKeyError, resolve_or_create_team_id

    name = team_name.strip()
    if not name:
        return ""
    try:
        return await resolve_or_create_team_id(
            base=base, credential=credential, name=name, auto_create=True,
        )
    except LiteLLMKeyError as exc:
        if exc.retryable:
            raise RetryHeld(f"litellm team resolve/create: {exc}") from exc
        raise PermanentError(f"litellm team resolve/create: {exc}") from exc


def _provider_base(kind: str, environment: str | None) -> tuple[str, str, str]:
    """Return (base_url, credential, path). MCP keys de aynı LiteLLM proxy."""
    import os

    from ...core.litellm.target import resolve_litellm_http

    target_kind = "litellm" if kind == "litellm" else "mcp"
    base, key = resolve_litellm_http(environment, kind=target_kind)
    if kind == "litellm":
        path = os.getenv("LITELLM_KEY_GENERATE_PATH", "/key/generate").strip() or "/key/generate"
        return base, key, path
    from ...core.litellm.generate_key import mcp_key_generate_path

    path = mcp_key_generate_path(os.getenv("MCP_GATEWAY_KEY_CREATE_PATH"))
    return base, key, path


async def _provision_credential(
    session: AsyncSession,
    *,
    deps: WorkerDependencies,
    request_id: uuid.UUID,
    secret_type: str,
    kind: str,
) -> None:
    from sqlalchemy import select

    from ...data.db.models.requests import Request

    row = await session.scalar(select(Request).where(Request.id == request_id))
    if row is None:
        raise PermanentError(f"request bulunamadı: {request_id}")
    from ...domain.enums import is_terminal

    if is_terminal(row.status):
        logger.info("provision no-op: already terminal", extra={"request_id": str(request_id)})
        return

    from ...core.naming import key_alias_for_request

    alias = (row.key_alias or "").strip() or key_alias_for_request(row)
    if row.key_alias != alias:
        row.key_alias = alias
        await session.flush()

    base, credential, path = _provider_base(kind, row.environment)
    plaintext: str | None = None
    provider_id = f"dry-run-{request_id.hex[:12]}"
    if base and path and credential:
        import httpx

        from ...core.litellm.generate_key import (
            build_key_generate_body,
            build_mcp_key_generate_body,
        )

        url = f"{base}{path if path.startswith('/') else '/' + path}"
        metadata = {
            "request_id": str(request_id),
            "ticket": row.genai_orion_panel_ticket_id,
        }
        litellm_log.info(
            "LiteLLM POST %s",
            url,
            extra={"kind": kind, "request_id": str(request_id)},
        )
        try:
            async with httpx.AsyncClient(timeout=30.0) as client:
                team_name = (getattr(row, "litellm_team_id", None) or "").strip()
                resolved_team = ""
                if team_name:
                    resolved_team = await _resolve_litellm_team_id(
                        client,
                        base=base,
                        credential=credential,
                        team_name=team_name,
                    )
                if kind == "litellm":
                    body = build_key_generate_body(
                        key_alias=alias,
                        models=list(row.models or []),
                        team_id=resolved_team or None,
                        max_parallel_requests=row.max_concurrent_requests,
                        metadata=metadata,
                    )
                else:
                    from ...core.mcp_scopes import scopes_from_row

                    server = (getattr(row, "mcp_server_slug", None) or "").strip()
                    if not server:
                        raise PermanentError("mcp provision: mcp_server_slug boş")
                    try:
                        mcp_scopes = scopes_from_row(
                            server,
                            list(row.mcp_tool_names or []),
                            bool(row.all_tools),
                        )
                    except ValueError as exc:
                        raise PermanentError(f"mcp provision: {exc}") from exc
                    body = build_mcp_key_generate_body(
                        key_alias=alias,
                        server_slug=server,
                        tool_names=list(row.mcp_tool_names or []),
                        all_tools=bool(row.all_tools),
                        scopes=mcp_scopes,
                        metadata=metadata,
                        team_id=resolved_team or None,
                    )
                response = await client.post(
                    url,
                    headers={"Authorization": f"Bearer {credential}"},
                    json=body,
                )
        except PermanentError:
            raise
        except (httpx.ConnectError, httpx.TimeoutException, OSError) as exc:
            litellm_log.error(
                "LiteLLM unreachable %s: %s",
                url, exc,
                extra={"kind": kind, "request_id": str(request_id)},
            )
            raise RetryHeld(f"{kind} unavailable: {exc}") from exc
        snippet = (response.text or "")[:500]
        litellm_log.info(
            "LiteLLM %s → HTTP %s",
            url, response.status_code,
            extra={"kind": kind, "request_id": str(request_id), "status": response.status_code},
        )
        if response.status_code in {429, 502, 503, 504}:
            raise RetryHeld(f"{kind} http {response.status_code}: {snippet}")
        if response.status_code >= 400:
            litellm_log.error(
                "LiteLLM %s body: %s",
                url, snippet,
                extra={"kind": kind, "request_id": str(request_id)},
            )
            raise PermanentError(f"{kind} http {response.status_code}: {snippet}")
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

    await complete_request(
        session,
        request_id,
        dry_run=plaintext is None,
        write_secret=plaintext is not None,
        plaintext=plaintext,
        provider_id=provider_id,
        secret_type=secret_type,
        cipher=deps.secret_cipher,
    )


async def complete_request(
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

    from ...data.db.models.outbox_jobs import OutboxJob
    from ...data.db.models.requests import Request
    from ...data.db.models.secrets import Secret
    from ...domain.enums import RequestStatus, is_terminal

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
                job_type=OutboxJobType.SEND_RESULT_MAIL.value,
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

