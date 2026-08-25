"""`POST /webhooks/orion` — flat payload validation + persist + approver outbox.

Bu modül orijinal `genai_orion_panel_webhook.py` rota'sının yerini alır.
Eski rota ``genai_orion_panel_core.application.commands.
receive_genai_orion_panel_request`` paketine bağlıydı; paket düzeltilene
kadar onun yerine bu **core-import'suz** alternatif kullanılıyor:

* Pydantic validation **yerel** — ``genai_orion_panel_schemas`` editable-broken
  listesinde, dolayısıyla bu modül dışa bağımlılık taşımaz.
* DB ``requests`` tablosuna doğrudan ORM INSERT.
* Aynı session içinde ``send:approval_mail`` outbox job'larını enqueue'la
  (birer tane ``config_approvers(scope=GENAI_APPROVAL, is_active=true)``
  üyesi için).
* ``correlation_id`` request header'ından geçer; response'da yansır.

Core paketi düzeltildiğinde tek satır mapper ile orijinal politika
(``ReceiveGenAiOrionPanelRequestHandler``) geri bağlanabilir; bu arada
bu sürüm tek başına uçtan uca çalışır (Smoke:
``scripts/checks/orion_webhook_smoke.py``).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import logging
import os
from datetime import UTC, datetime
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Header, Request, status
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, EmailStr, Field, HttpUrl, ValidationError
from sqlalchemy import select

from ...core.mailing.outbox_helpers import (
    enqueue_approval_request_mail,
)
from ...data.db.models.config_approvers import ConfigApprover
from ...data.db.models.requests import Request as RequestModel
from ...data.db.repository import RequestRepository
from ...observability.events import log_event

logger = logging.getLogger(__name__)

router = APIRouter(tags=["orion-webhook"])


TALEP_TURU_MAPPING: dict[str, str] = {
    "litellm_api_anahtari": "litellm_key",
    "mcp_erisim_anahtari": "mcp_key",
    "mcp_sunucu_kaydi": "mcp_server_registry",
}


class SharedFields(BaseModel):
    """Tüm tipler için ortak alanlar — `extra='forbid'` ile sıkı doğrula."""

    model_config = ConfigDict(extra="forbid")

    talep_turu: str = Field(min_length=1, max_length=64)
    talep_no: str = Field(min_length=1, max_length=64)
    talep_url: HttpUrl
    talep_eden_adi: str = Field(min_length=1, max_length=200)
    talep_eden_eposta: EmailStr
    olusturulma_tarihi: datetime


class LitellmKeyPayload(SharedFields):
    departman_adi: str | None = None
    ortam: str | None = None
    talep_aciklamasi: str | None = None
    kullanim_amaci: str | None = None
    kullanim_senaryosu: str | None = None
    modeller: list[str] = Field(default_factory=list)
    yanit_suresi: str | None = None
    kullanim_sikligi: str | None = None
    tahmini_gunluk_istek: int | None = None
    maksimum_es_zamanli_istek: int | None = None
    ortalama_girdi_sayfasi: float | None = None
    ortalama_cikti_sayfasi: float | None = None


class McpKeyPayload(SharedFields):
    departman_adi: str | None = None
    ortam: str | None = None
    talep_aciklamasi: str | None = None
    kullanim_amaci: str | None = None
    mcp_sunucusu: str | None = None
    araclar: list[str] = Field(default_factory=list)
    tum_araclara_erisim: bool | None = None


class McpRegistryPayload(SharedFields):
    departman_adi: str | None = None
    ortam: str | None = None
    talep_aciklamasi: str | None = None
    kullanim_amaci: str | None = None
    mcp_sunucu_adi: str | None = None
    mcp_sunucusu_goruntulu_ad: str | None = None
    proje_adi: str | None = None
    teknik_sorumlu_eposta: EmailStr | None = None
    repo_platformu: str | None = None
    repo_url: HttpUrl | None = None
    devops_jira_no: str | None = None
    devops_jira_anahtari: str | None = None
    mcp_endpoint_url: HttpUrl | None = None
    minimum_evaluation_skoru: int | None = None
    minimum_degerlendirme_skoru: int | None = None
    ek_notlar: str | None = None


_SCHEMA_BY_TALEP_TURU: dict[str, type[SharedFields]] = {
    "litellm_api_anahtari": LitellmKeyPayload,
    "mcp_erisim_anahtari": McpKeyPayload,
    "mcp_sunucu_kaydi": McpRegistryPayload,
}


def _resolve_request_type(talep_turu: str) -> str:
    if talep_turu not in TALEP_TURU_MAPPING:
        msg = f"unsupported talep_turu: {talep_turu!r}"
        raise ValueError(msg)
    return TALEP_TURU_MAPPING[talep_turu]


async def _approver_recipients(session) -> list[str]:
    """``config_approvers.scope='GENAI_APPROVAL'`` aktif satırlar.

    Cold-start durumunda (henüz seed edilmemiş) boş liste döner; route
    outbox'a düşülemezse mail enqueue'suz 202 döner ve loglar —
    core düzeltildiğinde admin seed script'i bağlandığında akış normale
    döner.
    """
    rows = await session.scalars(
        select(ConfigApprover.email)
        .where(
            ConfigApprover.scope == "GENAI_APPROVAL",
            ConfigApprover.is_active.is_(True),
        )
        .order_by(ConfigApprover.sort_order.asc())
    )
    return list(rows.all())


_TURKISH_TO_SNAKE: dict[str, str] = {
    "departman_adi": "department_name",
    "ortam": "environment",
    "talep_aciklamasi": "request_description",
    "kullanim_amaci": "purpose_text",
    "kullanim_senaryosu": "use_case",
    "modeller": "models",
    "yanit_suresi": "response_window",
    "kullanim_sikligi": "usage_frequency",
    "tahmini_gunluk_istek": "estimated_daily_requests",
    "maksimum_es_zamanli_istek": "max_concurrent_requests",
    "ortalama_girdi_sayfasi": "input_pages",
    "ortalama_cikti_sayfasi": "output_pages",
    "mcp_sunucusu": "mcp_server_slug",
    "araclar": "mcp_tool_names",
    "tum_araclara_erisim": "all_tools",
    "mcp_sunucu_adi": "mcp_server_display_name",
    "mcp_sunucusu_goruntulu_ad": "mcp_server_display_name",
    "proje_adi": "project_name",
    "teknik_sorumlu_eposta": "technical_owner_email",
    "repo_platformu": "repo_platform",
    "repo_url": "repo_url",
    "devops_jira_no": "devops_jira_key",
    "devops_jira_anahtari": "devops_jira_key",
    "mcp_endpoint_url": "mcp_endpoint_url",
    "minimum_evaluation_skoru": "minimum_evaluation_score",
    "minimum_degerlendirme_skoru": "minimum_evaluation_score",
    "ek_notlar": "additional_notes",
}


def _payload_to_request_fields(
    payload: SharedFields, request_type: str, raw: dict[str, Any],
) -> dict[str, Any]:
    """Pydantic payload → ORM ``requests`` satır field'ları."""
    fields: dict[str, Any] = {
        "request_type": request_type,
        "status": "waiting_approval",
        "version": 0,
        "genai_orion_panel_ticket_id": payload.talep_no,
        "genai_orion_panel_ticket_url": str(payload.talep_url),
        "requester_name": payload.talep_eden_adi,
        "requester_email": payload.talep_eden_eposta,
        "genai_orion_panel_created_at": payload.olusturulma_tarihi,
        "raw_genai_orion_panel_payload": json.dumps(
            raw, ensure_ascii=False, default=str,
        ),
    }
    for k, v in payload.model_dump(mode="json").items():
        if k in {
            "talep_turu", "talep_no", "talep_url", "talep_eden_adi",
            "talep_eden_eposta", "olusturulma_tarihi",
        }:
            continue
        snakecase = _TURKISH_TO_SNAKE.get(k, k)
        if snakecase in {
            "request_type", "status", "version",
            "genai_orion_panel_ticket_id",
            "genai_orion_panel_ticket_url",
            "requester_name", "requester_email",
            "genai_orion_panel_created_at",
            "raw_genai_orion_panel_payload",
        }:
            continue
        fields[snakecase] = v
    if request_type == "litellm_key":
        purpose = payload.model_dump().get("kullanim_amaci")
        if purpose:
            fields["purpose_code"] = purpose
        input_pages = float(fields.get("input_pages") or 0)
        output_pages = float(fields.get("output_pages") or 0)
        tokens = max(int((input_pages + output_pages) * 1000), 1000)
        fields["estimated_tokens_per_request"] = tokens
        if (fields.get("department_name") or "").strip():
            fields["litellm_team_id"] = str(fields["department_name"]).strip()
    if request_type in {"litellm_key", "mcp_key"}:
        from backend.src.core.naming import key_alias_for_request

        fields["key_alias"] = key_alias_for_request(fields, request_type)
    return fields


def _action_base() -> str:
    return os.getenv("PUBLIC_ACTION_BASE_URL", "http://localhost:8058/approvals").rstrip("/")


def _webhook_signature_failure(request: Request, body: bytes) -> JSONResponse | None:
    """HMAC-SHA256 over raw body. Empty secret or AUTH_MODE=off → skip (local smoke)."""
    mode = os.getenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "hmac").strip().lower()
    secret = os.getenv("GENAI_ORION_PANEL_WEBHOOK_SECRET", "").strip()
    if mode in {"off", "none", "disabled"} or not secret:
        return None
    provided = (
        request.headers.get("x-genai-orion-panel-signature")
        or request.headers.get("X-GenAi-Orion-Panel-Signature")
        or ""
    ).strip()
    expected = hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()
    if provided and hmac.compare_digest(provided.lower(), expected.lower()):
        return None
    log_event(
        logger, "orion.webhook.invalid",
        level=logging.WARNING,
        error_code="INVALID_WEBHOOK_SIGNATURE",
    )
    return JSONResponse(
        status_code=status.HTTP_401_UNAUTHORIZED,
        content={"error_code": "INVALID_WEBHOOK_SIGNATURE"},
    )


@router.post("/orion", status_code=status.HTTP_202_ACCEPTED)
async def receive_orion_webhook(
    request: Request,
    x_correlation_id: Annotated[str | None, Header(alias="X-Correlation-Id")] = None,
) -> JSONResponse:
    """`POST /webhooks/orion` — validate → INSERT request → outbox mail.

    Hata sınıfları:
    - 401: HMAC imza yok/uyuşmaz (secret set + AUTH_MODE=hmac).
    - 422: bilinmeyen talep_turu, JSON parse, payload schema reddi.
    - 202 (duplicate=True): aynı (ticket_no, request_type) daha önce alındı.
    - 202: yeni istek alındı, N approver mail outbox'a düştü (enqueued=N),
      approver listesi boşsa outbox boş kalır (warning log).
    """
    state = request.app.state.container
    factory = state.session_factory

    body = await request.body()
    rejected = _webhook_signature_failure(request, body)
    if rejected is not None:
        return rejected

    try:
        raw = json.loads(body) if body else None
    except Exception:  # noqa: BLE001 — parse hatası 422 olarak geri dön.
        log_event(
            logger, "orion.webhook.parse_failed",
            level=logging.WARNING,
            raw_size=str(request.headers.get("content-length") or "?"),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "BAD_JSON", "field_errors": []},
        )

    raw_size_hint = request.headers.get("content-length") or "?"
    log_event(
        logger,
        "orion.webhook.received",
        method="POST",
        path="/webhooks/orion",
        raw_size=str(raw_size_hint),
        ticket_no=str(raw.get("talep_no", "?")) if isinstance(raw, dict) else "?",
    )

    talep_turu = raw.get("talep_turu") if isinstance(raw, dict) else None
    if talep_turu not in _SCHEMA_BY_TALEP_TURU:
        log_event(
            logger, "orion.webhook.invalid",
            level=logging.WARNING,
            error_code="UNKNOWN_REQUEST_TYPE",
            talep_turu=str(talep_turu),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "UNKNOWN_REQUEST_TYPE", "field_errors": []},
        )

    schema_cls = _SCHEMA_BY_TALEP_TURU[talep_turu]
    try:
        payload = schema_cls.model_validate(raw)
    except ValidationError as exc:
        log_event(
            logger, "orion.webhook.invalid",
            level=logging.WARNING,
            error_code="VALIDATION_ERROR",
            talep_turu=talep_turu,
            field_count=len(exc.errors()),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "VALIDATION_ERROR",
                     "field_errors": exc.errors()},
        )

    try:
        request_type = _resolve_request_type(talep_turu)
    except ValueError as exc:
        log_event(
            logger, "orion.webhook.invalid",
            level=logging.WARNING,
            error_code="UNKNOWN_REQUEST_TYPE",
            exc_msg=str(exc),
        )
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={"error_code": "UNKNOWN_REQUEST_TYPE",
                     "field_errors": [str(exc)]},
        )

    async with factory() as session:
        repo = RequestRepository(session)
        existing = await repo.get_by_ticket_id(
            ticket_id=payload.talep_no,
            request_type=request_type,
        )
        if existing is not None:
            log_event(
                logger, "orion.webhook.duplicate",
                request_id=str(existing.id),
                ticket_no=payload.talep_no,
                request_type=request_type,
                status=existing.status,
            )
            return JSONResponse(
                status_code=status.HTTP_202_ACCEPTED,
                content={
                    "request_id": str(existing.id),
                    "status": existing.status,
                    "duplicate": True,
                },
                headers={"X-Correlation-Id": x_correlation_id or ""},
            )

        request_fields = _payload_to_request_fields(
            payload, request_type=request_type, raw=raw,
        )
        now = datetime.now(UTC).replace(tzinfo=None)
        request_fields.setdefault("id", uuid4())
        request_fields.setdefault("created_at", now)
        request_fields.setdefault("updated_at", now)
        new_db_request = RequestModel(**request_fields)
        await repo.save(new_db_request)
        await session.flush()  # PK garantile

        from urllib.parse import quote

        from backend.src.api.utils.action_tokens import compact_of, issue_tokens_for_request

        token_rows = issue_tokens_for_request(
            state.token_signer,
            request_id=new_db_request.id,
            request_type=request_type,
            ttl_hours=state.settings.action_token_ttl_hours,
        )
        action_urls: dict[str, str] = {}
        base = _action_base()
        for token_row in token_rows:
            session.add(token_row)
            compact = compact_of(token_row)
            if compact:
                action_urls[token_row.action] = f"{base}/{quote(compact, safe='.-_')}"

        recipients = await _approver_recipients(session)
        enqueued = 0
        for recipient in recipients:
            await enqueue_approval_request_mail(
                session,
                request_id=new_db_request.id,
                request_type=request_type,
                recipient=recipient,
                viewer_base=base,
                token=compact_of(token_rows[0]) if token_rows else "",
                required_action="approve",
                created_by=payload.talep_eden_eposta,
                action_urls=action_urls,
            )
            enqueued += 1

        await session.commit()

    log_event(
        logger, "orion.webhook.accepted",
        request_id=str(new_db_request.id),
        ticket_no=payload.talep_no,
        request_type=request_type,
        approver_mails_enqueued=enqueued,
        requester_email=payload.talep_eden_eposta,
    )
    response: dict[str, Any] = {
        "request_id": str(new_db_request.id),
        "status": "waiting_approval",
        "approver_mails_enqueued": enqueued,
    }
    if not recipients:
        logger.warning(
            "approver listesi boş; outbox'a mail düşmedi",
            extra={"event": "orion.webhook.no_approvers",
                   "request_id": str(new_db_request.id),
                   "request_type": request_type},
        )
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=response,
        headers={"X-Correlation-Id": x_correlation_id or ""},
    )


__all__ = ["router", "receive_orion_webhook"]
