"""DI composability kökü.

``genai_orion_panel_core`` port'larına somut adapter bağlantıları burada yapılır.
Route handler'ları yalnızca bu state üzerinden core'u kullanır.

Core'un framework-agnostic sınırı korunur: burası composition köküdür.

Approval action token imzalayan ``HmacTokenSigner`` business-token'dır;
dış kullanıcı mail linkinden gelen capability'yi taşır. Login JWT'si
``Settings.jwt_secret`` → ``PyJWT`` üzerinden üretilir (ayrı modül;
kapasite çakışmasını engeller).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker

from backend.src.adapters.crypto.signer import HmacTokenSigner
from backend.src.adapters.postgres.unit_of_work import SqlAlchemyUnitOfWork
from backend.src.api.auth.rate_limit import LoginRateLimiter
from backend.src.data.db.config import DBConfig
from backend.src.data.db.engine import build_async_engine, build_session_factory
from backend.src.observability.settings import Settings, get_settings

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class AppState:
    """Her request için DI container; test'te override edilebilir."""

    db_config: DBConfig
    settings: Settings
    engine: AsyncEngine
    session_factory: async_sessionmaker[AsyncSession]
    token_signer: HmacTokenSigner
    login_rate_limiter: LoginRateLimiter

    @property
    def config(self) -> DBConfig:
        """Legacy rate: ``state.config`` hâlâ ``DBConfig``'i döner."""
        return self.db_config

    def new_uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)

    async def aclose(self) -> None:
        """Pool + engine temizliği."""
        await self.engine.dispose()


async def build_app_state() -> AppState:
    """Lifespan başlangıcında çağrılır; adapter bağlantıları kurulur."""
    config = DBConfig.from_env()
    settings = get_settings()

    environment = settings.environment
    if environment == "prod":
        settings.validate_production()
    else:
        # Dev/stg'de logla (operatör fark etsin) ama boot etme —
        # legacy davranış.
        try:
            settings.validate_production()
        except RuntimeError as exc:
            logger.warning(
                "Unsafe config tolerated in env=%s: %s", environment, exc,
            )

    engine = build_async_engine(config)
    session_factory = build_session_factory(engine)
    signing_secret = settings.action_signing_secret
    if not signing_secret:
        signing_secret = "dev-action-signing-secret-change-me-32b"
        logger.warning(
            "ACTION_SIGNING_SECRET empty; using insecure dev default",
        )
    token_signer = HmacTokenSigner(signing_secret)

    return AppState(
        db_config=config,
        settings=settings,
        engine=engine,
        session_factory=session_factory,
        token_signer=token_signer,
        login_rate_limiter=LoginRateLimiter(),
    )
