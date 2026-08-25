"""Structured event emitter — logların "ne oldu" sorusunu netleştirir.

``logging.info`` her yer tek başına konuşur; bu modül her event'i
``event=<tag>`` alanı ile ``extras`` üzerinden sabit bir namespace'e
sokar. JSON formatter zaten ``extras`` dict'ini flat çıkarıyor; dolayısıyla
bir kayıt satırı şöyle görünür::

  {"ts":..., "level":"INFO", "logger":"...", "message":"...",
   "extras": {"event":"request.received", "request_id":"...",
              "request_type":"litellm_key", "enqueued":3},
   "correlation_id":"..."}

Yaklaşım:
- Uygulama çağrıları hep :func:`log_event` üzerinden gitsin.
- Envanter ``EVENT_TAGS`` ile sözleşmeye bağlanır — yeni tag'ler burada
  listelenir; testler ve dashboard bu listeyi referans alır.
- Helper'lar düşük-overhead; hot path'te ``logger.isEnabledFor(level)`` ek
  kontrolü yok (formatter extras'ı zaten discard eder, mesajına bakmaz).
"""

from __future__ import annotations

import logging
from typing import Any, Final


# Event tag registry — operasyonel view için stable contract.
EVENT_TAGS: Final[tuple[str, ...]] = (
    # ---- HTTP request lifecycle ------------------------------------------------
    "http.request.received",  # path + method + correlation_id (middleware öncesi)
    "http.request.completed",  # method + path + status + elapsed_ms
    "http.request.failed",  # client disconnect / unhandled exception
    # ---- Orion webhook ---------------------------------------------------------
    "orion.webhook.received",  # ilk parse öncesi; ticket_no + raw_size
    "orion.webhook.parse_failed",  # JSON okunamadı
    "orion.webhook.invalid",  # 422 — bilinmeyen talep_turu / validating error
    "orion.webhook.duplicate",  # 202 duplicate=True
    "orion.webhook.accepted",  # 202 yeni insert + outbox enqueue adedi
    # ---- Outbox ---------------------------------------------------------------
    "outbox.enqueue",  # yeni job INSERT edildi (job_type + dedupe_key)
    "outbox.claim.empty",  # tick boş
    "outbox.claim.batch",  # tick start (worker_id + batch size)
    "outbox.tick.completed",  # tick sonu (final_status dizilimi + ms)
    "outbox.retry.scheduled",  # mark_retry → available_at delta
    "outbox.dead_letter",  # permanent / max_attempts exceeded / bad_payload
    # ---- Mailer ---------------------------------------------------------------
    "mail.rendering",  # template_name + recipients count
    "mail.sent",  # SMTP 250 + elapsed_ms
    "mail.failed",  # SMTP / template / config hatası
    "mail.skipped",  # jsonfile placeholder gibi no-op
    # ---- LDAP / auth ----------------------------------------------------------
    "ldap.auth.start",  # authenticate_ldap çağrı öncesi
    "ldap.auth.success",  # bind ok + identity snapshot
    "ldap.auth.failed",  # bind hata + reason
    "ldap.auth.unavailable",  # LdapUnavailableError raised
    "ldap.required_group_denied",  # directory user ama required_group yok
    "user.provisioned",  # provision_ldap_user user upsert + binding sayıları
    "user.bootstrap",  # ensure_bootstrap_admin seed
    "auth.login.ok",  # /auth/login 200 — JWT üretildi
    "auth.login.invalid",  # 401
    "auth.login.rate_limit",  # 429
    "auth.refresh",  # /auth/refresh sonucu
    # ---- Admin actions --------------------------------------------------------
    "admin.action.approve",
    "admin.action.revise",
    "admin.action.reject",
    "admin.action.conflict",  # stale request_version
    "admin.ldap_mapping.created",
    "admin.ldap_mapping.deleted",
    # ---- Worker ---------------------------------------------------------------
    "worker.started",
    "worker.stopping",
    "worker.stopped",
    "worker.heartbeat.batch",  # toplu metrik
    "worker.tick.error",  # `tick patladı`
    # ---- Provision + integration ---------------------------------------------
    "provision.litellm.started",
    "provision.litellm.failed",
    "provision.mcp.started",
    "provision.mcp.failed",
    "litellm.down",  # remote 5xx / timeout → outbox enqueue
)


def log_event(
    logger: logging.Logger,
    tag: str,
    *,
    level: int = logging.INFO,
    message: str | None = None,
    **fields: Any,
) -> None:
    """``event=<tag>`` ve flat extras ile tek çağrılık log bas.

    Parametreler:
    - ``logger``: çağıran modülün kendi logger'ı (örn ``logger = logging.getLogger(__name__)``).
    - ``tag``: :data:`EVENT_TAGS` içinden bir sabit.
    - ``level``: default ``INFO``; ``WARNING`` / ``ERROR`` opsiyonel.
    - ``message``: opsiyonel kısa açıklama. Verilmezse ``tag`` kullanılır.
    - ``fields``: extras dict'ine flat eklenecek anahtar/değer çiftleri.
      Pydantic / dataclass objesi ``str(..)`` ile güvenli hale getirilir
      formatter tarafında; numeric değerler aynen geçer.

    Performance: bu fonksiyon ``logger.log(level, msg, extra=...)`` çağrısını
    sarmaladığı için formatter aynı şekilde çalışır; event tag'inin eklenmesi
    sadece tek dict literal ekleme maliyeti.
    """
    extras = {"event": tag, **fields}
    logger.log(level, message or tag, extra=extras)


def attach_uvicorn_loggers(level: int = logging.INFO) -> None:
    """Uvicorn'un kendi ``uvicorn`` / ``uvicorn.access`` / ``uvicorn.error``
    logger'larını JSON root handler'ına bağla.

    Uvicorn default olarak kendi ``StreamHandler``'ını ``uvicorn.access``
    logger'ına kurar ve onun format'ı değişkendir. Burada yapılan:
    1. uvicorn.* logger'larının level'ını ayarla.
    2. propagate = True yap → root JSON formatter'ına düşer.
    3. uvicorn'un kendi handler'larını temizle (mükerrer tekrar).

    ``configure_json_logging`` çağrısıyla birlikte kullanılır.
    """
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error"):
        lg = logging.getLogger(name)
        for h in list(lg.handlers):
            lg.removeHandler(h)
        lg.propagate = True
        lg.setLevel(level)


__all__ = [
    "EVENT_TAGS",
    "attach_uvicorn_loggers",
    "log_event",
]
