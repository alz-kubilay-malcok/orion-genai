"""FastAPI process entry point.

Çalışma zamanı: ``PROCESS_ROLE=api python backend/main.py api``.
Aynı image worker rolüyle de çalışır (ADR-004).
"""

from __future__ import annotations

import logging
import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.src.api.routes import (
    admin,
    approval_actions,
    auth,
    health,
    internal,
    mcp_catalog,
    orion_webhook,
)
from backend.src.api.utils.dependencies import build_app_state
from backend.src.api.utils.middleware.correlation import CorrelationIdMiddleware
from backend.src.observability.logging_config import configure_json_logging

logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """DB engine, AppState ve bootstrap admin — başarısız olursa boot fail."""
    if os.getenv("PROCESS_ROLE", "api") != "api":
        raise RuntimeError("genai-orion-panel-api sadece PROCESS_ROLE=api ile çalışır")

    configure_json_logging(level=logging.INFO)

    state = await build_app_state()
    app.state.container = state

    from backend.src.api.auth.dependencies import ensure_approvers, ensure_bootstrap_admin

    await ensure_bootstrap_admin(state)
    logger.info("bootstrap admin ok")
    await ensure_approvers(state)
    logger.info("approver seed ok")
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

    allowed_origins = [
        o.strip()
        for o in os.getenv(
            "GENAI_ORION_PANEL_CORS_ORIGINS",
            "http://localhost:3000,http://127.0.0.1:3000,"
            "http://localhost:3001,http://127.0.0.1:3001,"
            "http://localhost:8058,http://127.0.0.1:8058",
        ).split(",")
        if o.strip()
    ]
    application.add_middleware(
        CORSMiddleware,
        allow_origins=allowed_origins,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        allow_credentials=True,
    )
    application.add_middleware(CorrelationIdMiddleware)

    application.include_router(health.router)
    application.include_router(orion_webhook.router, prefix="/webhooks")
    application.include_router(auth.router)
    application.include_router(admin.router)
    application.include_router(approval_actions.router, prefix="/actions")
    application.include_router(mcp_catalog.router, prefix="/catalog")
    application.include_router(internal.router, prefix="/internal")

    return application


def run() -> None:
    """Console-script entry point."""
    import uvicorn

    uvicorn.run(
        "backend.src.api.main:create_app",
        factory=True,
        host="0.0.0.0",
        port=int(os.getenv("PORT", "8000")),
    )


app = create_app()
