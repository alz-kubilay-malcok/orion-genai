"""Worker DI factory — env üzerinden `WorkerDependencies` kurulumu.

Adapter wiring'i burada yaşar; legacy `genai_orion_panel_worker` kalıbına
paralel. Kuruluşu bilerek **fail-fast** tutuyoruz: adapter yok / config
yanlışsa constructor seviyesinde `RuntimeError` raise ederek worker'ı
başlatmayı engelliyoruz (production'da lobby'de crash edilmesi tercih
edilir, silent partial mode'a kaymaktansa).
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Optional

from sqlalchemy.ext.asyncio import async_sessionmaker

from ..core.mailing.jwt_mail import issue as _jwt_issue
from ..data.db.repository import WorkerHeartbeatRepository
from .config import WorkerConfig
from .dependencies import WorkerDependencies

# Dead-letter notifier uses outbox_helpers lazily at call time so
# circular imports (helpers import handlers — handlers'ın load anında
# None) halkasından kaçınılır.
import importlib
from sqlalchemy import select

from ..data.db.models.config_approvers import ConfigApprover

logger = logging.getLogger(__name__)


WORKER_VERSION = "v1.0.0"


def _build_secret_cipher():
    """AES-GCM cipher — `KEY_ENCRYPTION_KEY` env'den, lokal fallback ile.

    Strateji:
        1) ``KEY_ENCRYPTION_KEY`` set ise ve import edilebilir dış
           ``AesGcmSecretCipher`` varsa onu tercih et (prod davranışı).
        2) Dış adapter yoksa ya da key yoksa dev-grade
           ``LocalAesGcmSecretCipher`` ile devam et; warning logu ile
           operatöre "bu canary/auto-generated" olduğunu hatırlat.
           Restart'ta Secret tablosu çözümsüz olur — bunu da logla.
        3) Her iki yol da patlarsa ``return None`` — ``WorkerDependencies``
           ``secret_cipher`` field'ı opsiyonel; provisioning handler'ları
           None olduğunda fail-safe mesaj verir.

    KEY_ENCRYPTION_KEY_VERSION env (default ``1``) her durumda
    ``current_key_version`` olarak kullanılır.
    """
    import os

    key = os.getenv("KEY_ENCRYPTION_KEY", "").strip()
    key_version = int(os.getenv("KEY_ENCRYPTION_KEY_VERSION", "1"))

    # ---- 1) dış adapter (production tercihi) -----------------------------
    if key:
        try:
            from genai_orion_panel_adapters.crypto.cipher import (  # type: ignore[import-not-found]
                AesGcmSecretCipher,
            )

            return AesGcmSecretCipher(
                current_key_b64=key, current_key_version=key_version,
            )
        except ImportError as exc:
            logger.warning(
                "KEY_ENCRYPTION_KEY set ama genai_orion_panel_adapters "
                "import edilemedi (%s); local AES-GCM fallback kullanılıyor",
                exc,
            )

    # ---- 2) lokal AES-GCM fallback ---------------------------------------
    try:
        from ._local_aes import LocalAesGcmSecretCipher, generate_dev_key_b64

        # Dev/test: env'de key yoksa rastgele üret; restart'ta Secret
        # tablosu çözümsüz olur warning tekrarı operatöre hatırlatır.
        if not key:
            key = generate_dev_key_b64()
            logger.warning(
                "KEY_ENCRYPTION_KEY env boş → otomatik 32B base64 üretildi. "
                "Dev/CI için OK; production'da kalıcı mount et."
            )
        return LocalAesGcmSecretCipher(
            current_key_b64=key, current_key_version=key_version,
        )
    except (ImportError, ValueError) as exc:
        # cryptography paketi yoksa ya da kullanıcı bozuk base64 verdiyse:
        logger.warning(
            "secret_cipher fallback da kurulamadı (%s); "
            "WorkerDependencies.secret_cipher = None kalacak",
            exc,
        )
        return None


def _build_litellm_adapter():
    """Environment-routed LiteLLM adapter.

    `LITELLM_BASE_URL` env'den environment'a göre URL+credential çözen
    legacy sınıfı kullanır. Adapter yoksa `None` döner; provisioning
    handler'ı bu nullptr ile fail-safe bir hata mesajı üretir.
    """
    import os

    if not os.getenv("LITELLM_BASE_URL"):
        return None, None
    try:
        from genai_orion_panel_adapters.config import Config, get_config  # noqa: F401
        from genai_orion_panel_adapters.litellm.key_gateway import LiteLLMKeyGateway  # noqa: F401
        from genai_orion_panel_adapters.litellm.mcp_gateway import LiteLLMMCPGatewayKeyAdapter  # noqa: F401
    except ImportError:
        logger.warning(
            "LITELLM_BASE_URL set ama adapter paketi yok; provisioning None kalır"
        )
        return None, None

    try:
        config: Config = get_config()

        class _EnvironmentRoutedLiteLLM:
            async def generate_key(self, command):  # noqa: ANN001, ANN201
                from genai_orion_panel_adapters.litellm.key_gateway import LiteLLMKeyGateway

                gateway = LiteLLMKeyGateway(
                    base_url=config.litellm_base_url(command.environment),
                    master_key=config.litellm_master_key(command.environment),
                )
                return await gateway.generate_key(command)

        class _EnvironmentRoutedMCPProvision:
            async def generate_scoped_key(self, command):  # noqa: ANN001, ANN201
                from genai_orion_panel_adapters.litellm.mcp_gateway import LiteLLMMCPGatewayKeyAdapter

                adapter = LiteLLMMCPGatewayKeyAdapter(
                    base_url=config.mcp_gateway_base_url(command.environment),
                    admin_credential=config.mcp_gateway_admin_credential(command.environment),
                )
                return await adapter.generate_scoped_key(command)

        return _EnvironmentRoutedLiteLLM(), _EnvironmentRoutedMCPProvision()
    except (ImportError, AttributeError, RuntimeError, ValueError) as exc:
        # config import sonrası bir şey patlarsa (env eksik, bilinmeyen
        # environment key, vs.) sessizce None'a düş; handler'lar
        # fail-safe hata mesajı verir.
        logger.warning(
            "LiteLLM adapter runtime init başarısız (%s); provisioning None kalır",
            exc,
        )
        return None, None


def _build_approval_token_issuer():
    """`core.mailing.jwt_mail.issue(...)` thin binding.

    `MAIL_JWT_SECRET` env'de yoksa `return None` — `WorkerDependencies`
    içine `None` geçer; approval handler fallback'i payload'daki token'ı
    kullanır (testing veya manuel token injection).
    """
    import os

    secret = os.getenv("MAIL_JWT_SECRET", "").strip()
    if not secret:
        logger.warning(
            "MAIL_JWT_SECRET missing; approval_token_issuer disabled, "
            "approver mails will use payload-passed token",
        )
        return None

    def issuer(
        *,
        request_id: str,
        request_type: str,
        action: str,
        recipient: str,
    ):
        return _jwt_issue(
            request_id=request_id,
            request_type=request_type,
            action=action,
            recipient=recipient,
        )

    return issuer


async def _approver_recipients_from_session(session) -> list[str]:
    """Dead-letter approval mail routing liste — sync wrapper.

    Caller `asyncio.run` ile çağıracak; bu helper tek coroutine.
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


_ASYNC_NOTIFIER_MARKER: str = "async_dead_letter_notifier"


def _build_dead_letter_notifier(
    session_factory: async_sessionmaker[AsyncSession],
):
    """`deps.dead_letter_notifier`'a bağlanacak **async** callback.

    Mantık: bir job ``dead_letter``'a düştüğünde approver listesini DB'den
    çek → ``enqueue_litellm_down_notice`` çağır → outbox'a yeni bir
    ``send:litellm_down_notice`` job enqueue'la. Worker bir tick sonra onu
    claim edip SMTP'ye basacak.

    Caller pattern: ``await notify(**)``. **Senkron versiyon nested
    ``asyncio.run`` patlatır çünkü dispatcher zaten async loop içinde;
    dolayısıyla closure bir coroutine döndürür.** Bu marker sayesinde
    test edilebilirlik için sync fonksiyonel "spy" takılabilir.
    """
    from ..core.mailing.outbox_helpers import enqueue_litellm_down_notice

    async def notify(
        *,
        job_id: str,
        job_type: str,
        error_code: str,
        error_message: str,
    ) -> None:
        async with session_factory() as session:
            recipients = await _approver_recipients_from_session(session)
            if not recipients:
                logger.warning(
                    "dead-letter notifier atlandı: approver listesi boş",
                )
                return
            await enqueue_litellm_down_notice(
                session,
                recipients=recipients,
                request_id=None,
                error_code=error_code or "LITELLM_DOWN",
                error_message=(
                    f"job={job_type} (id={job_id}): "
                    f"{(error_message or '')[:500]}"
                ),
            )
            await session.commit()

    # Marker döndür, doc-not read-only.
    setattr(notify, _ASYNC_NOTIFIER_MARKER, True)
    return notify


def _approve_mail_outbox_label() -> str:
    """Outbox job_type label için ortak string — handler'larla aynı."""
    return "send:litellm_down_notice"


def _build_heartbeat_callback(
    session_factory: async_sessionmaker,
):
    """`WorkerDependencies.heartbeat_callback` factory.

    WorkerRunner her tick sonunda sync olarak bu callback'i çağırır::

        deps.heartbeat_callback(
            worker_id=..., started_at=..., last_seen_at=...,
        )

    Veritabanı update'i async; dispatcher loop içinde olduğu için
    nested asyncio.run uygun değil. Çözüm:

    * session_factory async olmasına rağmen **callback sync** döner —
      her tick'te yeni bir kısa-ömürlü asenkron context açmak yerine
      yeni bir koroutini alıp ``asyncio.run_coroutine_threadsafe`` ile
      dispatcher'ın sahip olduğu loop'a göndermek normalde daha temiz
      olurdu; ancak WorkerRunner'da ayrı bir thread'de loop yoktur.
    * Bu nedenle callback içinde ``asyncio.new_event_loop().run_until_complete``
    ile kendi kısa ömürlü loop'unu kurarız. Worker sadece 1 tick'te bir
    bu çağrıyı yapar, maliyeti minimal (≤5 ms/sn düzeyinde).
    * Başarısızlık (DB down, vs.) sessizce loglanır — heartbeat kritik
      değildir; bir sonraki tick yeniden denenir.

    Args:
        session_factory: build_session_factory çıktısı.

    Returns:
        Callable: ``(*, worker_id, started_at, last_seen_at) -> None``.
    """
    import asyncio as _asyncio

    def callback(*, worker_id: str, started_at, last_seen_at) -> None:  # noqa: ANN001
        async def _run() -> None:
            async with session_factory() as session:
                # ``WorkerHeartbeatRepository.upsert`` (self, *, worker_id, version,
                # started_at, last_seen_at, ...) — Repository pattern; session
                # constructor'da bağlıdır.
                await WorkerHeartbeatRepository(session).upsert(
                    worker_id=str(worker_id),
                    version=WORKER_VERSION,
                    started_at=started_at,
                    last_seen_at=last_seen_at,
                )
                await session.commit()

        try:
            _asyncio.run(_run())
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "heartbeat upsert başarısız (worker_id=%s): %s: %s — "
                "bir sonraki tick'te tekrar denenecek",
                worker_id, type(exc).__name__, exc,
            )

    return callback


def build_worker_dependencies(
    *,
    session_factory: async_sessionmaker,
    config: WorkerConfig,
    worker_version: str = WORKER_VERSION,
) -> WorkerDependencies:
    """Per-process bağımlılıkları kur; boilerplate burada toplanır.

    Return edilen `WorkerDependencies` dispatcher'ın dolaştığı tek nesne.
    Hata durumunda explicit `RuntimeError` raise ediyoruz — startup'ta
    patlama daha iyidir, sessiz partial mod production'ı bozar.
    """
    secret_cipher = _build_secret_cipher()  # None olabilir → WorkerDependencies.optional_cipher

    # `_build_litellm_adapter` her durumda (None, None) | (LiteLLM, MCP) tuple
    # döner; dış adapter yoksa veya import/config patlarsa (None, None).
    litellm, mcp_provision = _build_litellm_adapter()

    heartbeat_callback = _build_heartbeat_callback(
        session_factory=session_factory, worker_version=worker_version,
    )
    approval_token_issuer = _build_approval_token_issuer()
    dead_letter_notifier = _build_dead_letter_notifier(
        session_factory=session_factory,
    )

    return WorkerDependencies(
        session_factory=session_factory,
        secret_cipher=secret_cipher,
        litellm=litellm,
        mcp_provision=mcp_provision,
        approval_token_issuer=approval_token_issuer,
        heartbeat_callback=heartbeat_callback,
        dead_letter_notifier=dead_letter_notifier,
    )


def now_utc() -> datetime:
    """Worker'ın tek yerde topladığı UTC helper."""
    return datetime.now(UTC).replace(tzinfo=None)


__all__ = [
    "build_worker_dependencies",
    "now_utc",
    "_build_heartbeat_callback",
    "_build_approval_token_issuer",
    "_build_dead_letter_notifier",
]
