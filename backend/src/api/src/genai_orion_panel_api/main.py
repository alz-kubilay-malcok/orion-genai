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

from backend.src.api.genai_orion_panel_api.routes import admin, approval_actions, genai_orion_panel_webhook, health, internal
from backend.src.api.genai_orion_panel_api.routes import (
    mcp_catalog,
)
from backend.src.api.genai_orion_panel_api.utils.dependencies import build_app_state
from backend.src.api.genai_orion_panel_api.utils.middleware.correlation import CorrelationIdMiddleware
from backend.src.data.scripts import FlywayError, flyway_init

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """DB engine, repository/UoW factory başlatma.

    PostgreSQL ise uygulama açılışında `flyway_init` ile eksik tablolar
    otomatik tamamlanır. SQLite (test/dev) için `flyway_init` sync
    çağrıldığından thread offload yok — küçük DDL seti birkaç ms sürer.
    """
    if os.getenv("PROCESS_ROLE", "api") != "api":
        msg = "genai-orion-panel-api sadece PROCESS_ROLE=api ile çalışır"
        raise RuntimeError(msg)

    db_url = os.getenv("DATABASE_URL", "")
    if db_url:
        try:
            applied = flyway_init(db_url)
            if applied:
                logger.info(
                    "flyway_init uygulanan migration'lar: %s",
                    applied,
                    extra={"role": "api", "applied_count": len(applied)},
                )
            else:
                logger.info("flyway_init: schema güncel", extra={"role": "api"})
        except FlywayError as exc:
            logger.error(
                "flyway_init başarısız: %s (migration=%s)",
                exc, exc.migration_name,
                extra={"role": "api"},
            )
            raise

    state = await build_app_state()
    app.state.container = state
    logger.info("genai-orion-panel-api hazır", extra={"role": "api"})
    try:
        yield
    finally:
        await state.aclose()


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
    application.add_middleware(CorrelationIdMiddleware)

    # Route registration (Bölüm 10). `/auth/*` router'ı kaldırıldı.
    application.include_router(health.router)
    application.include_router(genai_orion_panel_webhook.router, prefix="/webhooks")
    application.include_router(mcp_catalog.router, prefix="/catalog")
    application.include_router(approval_actions.router, prefix="/actions")
    application.include_router(internal.router, prefix="/internal")
    application.include_router(admin.router)

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
