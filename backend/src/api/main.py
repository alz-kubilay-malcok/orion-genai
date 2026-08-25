"""FastAPI process entry point.

Çalışma zamanı: `PROCESS_ROLE=api uv run genai-orion-panel-api`.
Aynı image worker rolüyle de çalışır (ADR-004).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """DB engine, repository/UoW factory başlatma.

    Refactor tamamlanana kadar alt bileşenler opsiyoneldir; `health/live`
    DB-bağımsız, `health/ready` ise ``build_app_state`` çağrısını deneyip
    başarısız olursa database=false döner.
    """
    if os.getenv("PROCESS_ROLE", "api") != "api":
        msg = "genai-orion-panel-api sadece PROCESS_ROLE=api ile çalışır"
        raise RuntimeError(msg)

    configure_json_logging = _safe_import_attr(
        "backend.src.observability.logging_config", "configure_json_logging",
    )
    if configure_json_logging is not None:
        configure_json_logging(level=logging.INFO)

    build_app_state = _safe_import_attr(
        "backend.src.api.utils.dependencies", "build_app_state",
    )
    app.state.container = None
    if build_app_state is not None:
        try:
            state = await build_app_state()
            app.state.container = state
        except Exception as exc:  # noqa: BLE001
            logger.warning("build_app_state başarısız (yoksay): %s: %s",
                           type(exc).__name__, exc)

    # Bootstrap admin seed (idempotent) — circular import'tan kaçınmak
    # için lifespan'da çağrılır.
    if app.state.container is not None:
        try:
            from backend.src.api.auth.dependencies import ensure_bootstrap_admin

            await ensure_bootstrap_admin(app.state.container)
            logger.info("bootstrap admin ok")
        except Exception as exc:  # noqa: BLE001
            logger.warning("bootstrap admin seed başarısız (yoksay): %s", exc)

    logger.info("genai-orion-panel-api hazır", extra={"role": "api"})
    try:
        yield
    finally:
        if app.state.container is not None:
            try:
                await app.state.container.aclose()
            except Exception as exc:  # noqa: BLE001
                logger.warning("state.aclose başarısız (yoksay): %s", exc)


def _safe_import_attr(module_path: str, attr: str) -> object | None:
    """Legacy import hatasında None döner; ``create_app`` yine de kurulur."""
    import importlib

    try:
        module = importlib.import_module(module_path)
    except Exception as exc:  # noqa: BLE001
        logger.warning("import skip: %s.%s -> %s: %s",
                       module_path, attr, type(exc).__name__, exc)
        return None
    return getattr(module, attr, None)


def _try_import_router(module_path: str) -> tuple[str, object | None]:
    """Legacy import hatası durumunda None döner; rotalar refactor edilene
    kadar çalışmazsa bile ``/health/*`` ve ``/webhooks/*`` ayakta kalır.

    Return: (module_path, router_or_None)
    """
    return module_path, _safe_import_attr(module_path, "router")


def _register_router_safe(app: FastAPI, module_path: str, *, prefix: str | None = None) -> None:
    """Rotaları try/except ile yükle; legacy bağımlılığı olanlar skip olur.

    Skip olan rotalar ``lifespan`` ve DB-conn driver'larına dokunmaz;
    ``/health/*`` + ``/webhooks/*`` bugün refactor tamamlanana kadar bile
    uvicorn'un ayakta kalması için yeterli.
    """
    _, router = _try_import_router(module_path)
    if router is None:
        return
    if prefix is not None:
        app.include_router(router, prefix=prefix)
    else:
        app.include_router(router)


def create_app() -> FastAPI:
    """FastAPI uygulamasını oluşturur; test fixture'larında override edilir."""
    application = FastAPI(
        title="GenAiOrionPanel — API",
        version="0.1.0",
        lifespan=lifespan,
    )

    # Frontend (Next.js viewer + admin panel) CORS — izinli origin'ler; şimdilik
    # auth'sız çalışıldığı için credentialed istek gereksiz, ancak LDAP
    # sonrası cookie/session için yine açık kalabilir.
    allowed_origins = [
        o.strip()
        for o in os.getenv(
            "GENAI_ORION_PANEL_CORS_ORIGINS", "http://localhost:3000,http://localhost:3001"
        ).split(",")
        if o.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "DELETE", "PATCH"],
        allow_headers=["*"],
        allow_credentials=True,
    )

    # Middleware (LIFO çalışır; correlation en dışta kalsın diye en son eklenir).
    # Auth middleware'leri (CatalogAuthMiddleware, GenAiOrionPanelWebhookAuthMiddleware)
    # kaldırıldı; LDAP entegrasyonu sonrası yeniden tasarlanacak.
    CorrelationIdMiddleware = _safe_import_attr(
        "backend.src.api.utils.middleware.correlation", "CorrelationIdMiddleware",
    )
    if CorrelationIdMiddleware is not None:
        application.add_middleware(CorrelationIdMiddleware)

    # Route registration. Sağlam import'lar ``_safe_import_attr`` üzerinden
    # yüklenir; başarısız rota skip olur, uvicorn yine ayakta kalır.
    #
    # NOT: Bu turda ``backend.src.api.utils.dependencies`` -> eski
    # ``genai_orion_panel_adapters.config`` zincirine bağlı olan
    # tüm rotalar (auth, admin_ldap dahil) skip olur — test/yerel ortamda
    # o paket kuruluyken ``_register_router_safe`` ``/auth/*`` ve
    # ``/admin/ldap-mappings/*``'i bağlar; kurulu değilken sadece health ve
    # orion_webhook yüklü kalır. Refactor turunda (kılavuz: tüm ``AppState``
    # / settings bağımlılıkları ``backend.src.*`` altına taşınınca) tüm
    # rotalar tek satırda bağlanacak. Mevcut durum:
    #   bağımlı olmayan (her ortamda yüklenir):
    #     - health, orion_webhook
    #   eski pakete bağlı (ortamda varsa yüklenir):
    #     - auth, admin_ldap, admin, approval_actions, internal, mcp_catalog
    _register_router_safe(application, "backend.src.api.routes.health")
    _register_router_safe(application, "backend.src.api.routes.orion_webhook", prefix="/webhooks")
    _register_router_safe(application, "backend.src.api.routes.auth")
    _register_router_safe(application, "backend.src.api.routes.admin_ldap")

    return application


def run() -> None:
    """Console-script entry point."""
    import uvicorn

    uvicorn.run(
        "genai_orion_panel_api.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )


app = create_app()
