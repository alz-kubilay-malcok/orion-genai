"""Liveness + readiness endpoints (Bölüm 16 / Bölüm 17).

- /health/live   → process alive
- /health/ready  → DB reachable + role-typed config valide
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from fastapi import APIRouter, Request, status
from fastapi.responses import JSONResponse
from sqlalchemy import text

from backend.src.api.auth.ldap import LdapUnavailableError, _preflight

if TYPE_CHECKING:
    from backend.src.api.utils.dependencies import AppState

logger = logging.getLogger(__name__)
router = APIRouter(tags=["health"])


@router.get("/health/live")
async def liveness() -> dict[str, str]:
    """Process'in ayakta olduğunu bildirir; DB/migration kontrolü yapmaz."""
    return {"status": "alive"}


@router.get("/health/ready")
async def readiness(request: Request) -> JSONResponse:
    """Process rolüne göre gereken bağımlılıkların hazır olduğunu doğrular."""
    state: AppState = request.app.state.container
    checks: dict[str, bool] = {}

    try:
        async with state.session_factory() as session:
            await session.execute(text("SELECT 1"))
        checks["database"] = True
    except Exception:  # noqa: BLE001 — detay sızdırmaz, yalnız boolean check
        checks["database"] = False

    # LDAP pre-flight: directory bağlantısı kurulabilir mi? Sadece
    # ``LDAP_ENABLED=true`` ise çalışır; değilse (legacy local-only veya
    # break-glass) bu kontrol N/A kabul edilir. TCP <5s ile.
    settings = state.settings
    if settings.ldap_enabled:
        try:
            _preflight(
                settings.ldap_host, settings.ldap_port, settings.ldap_connect_timeout,
            )
            checks["ldap"] = True
        except LdapUnavailableError as exc:
            logger.warning("ldap pre-flight failed: %s", exc)
            checks["ldap"] = False

    checks["action_signing_config"] = state.token_signer is not None

    all_ok = all(checks.values())
    return JSONResponse(
        status_code=status.HTTP_200_OK if all_ok else status.HTTP_503_SERVICE_UNAVAILABLE,
        content={"status": "ready" if all_ok else "not_ready", "checks": checks},
    )
