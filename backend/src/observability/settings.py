"""Cross-cutting application settings (env-bound).

Tüm süreçlerde (api, worker) paylaşılan; pydantic-settings üzerinden
.env'den okunan typed konfig katmanı. ``get_settings()`` ``@lru_cache``'li
→ test'lerde ``get_settings.cache_clear()`` gerekir.

Sözleşme referansı: docs/ldap_active_directory_setup.md, docs/baseline.md.
"""

from __future__ import annotations

import os
from functools import lru_cache
from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    # General / process
    environment: Literal["dev", "stg", "prod"] = "dev"
    debug: bool = False

    # JWT (login akışı; mail capability ayrı tutulur — `MAIL_JWT_SECRET`)
    jwt_secret: str = ""
    jwt_access_ttl_minutes: int = 30
    jwt_refresh_ttl_days: int = 14

    # LDAP block — verbatim kılavuz §4.1, sadece env key'leri snakecase'e
    # çevrildi (pydantic-settings case_sensitive=False).
    ldap_enabled: bool = False
    ldap_host: str = "ldap.example.local"
    ldap_port: int = 636
    ldap_use_ssl: bool = True            # LDAPS (implicit TLS)
    ldap_tls_verify: bool = True         # False → CERT_NONE (insecure, test only)
    ldap_ca_cert: str | None = None      # path to corporate CA PEM (container path)
    ldap_ca_cert_pem: str = ""           # PEM içeriği; varsa dosyadan önce gelir
    ldap_connect_timeout: int = 5        # pre-flight TCP check, fail-fast off-network
    ldap_base_dn: str = "DC=example,DC=local"
    ldap_bind_dn: str = ""               # service account DN
    ldap_bind_password: str = ""         # service account password (secret)
    ldap_user_attr: str = "sAMAccountName"
    ldap_mail_attr: str = "mail"
    ldap_display_name_attr: str = "displayName"
    ldap_object_class: str = "person"
    ldap_group_member_attr: str = "memberOf"
    ldap_required_group: str | None = None
    ldap_admin_group: str | None = None  # DN; member → is_superuser
    default_namespace_slug: str = "demo"
    ldap_allow_local_fallback: bool = True
    allow_prod_local_break_glass: bool = False
    allow_prod_insecure_ldap_tls: bool = False

    # Bootstrap admin (local bcrypt account). LDAP gelmeden önceki
    # break-glass girişi ve `admin` mapping'lerini oluşturan kullanıcı.
    bootstrap_admin_enabled: bool = True
    bootstrap_admin_username: str = "admin@local"
    bootstrap_admin_email: str = "admin@local"
    bootstrap_admin_password: str = "admin"  # noqa: S105 — dev default only

    # Login rate-limit (per (IP, username)). Prod'da backend'i olarak
    # dışarı taşınabilir; default'lar kılavuz §4.5 ruhuna uygun.
    login_rate_limit_max_attempts: int = Field(default=5, ge=1)
    login_rate_limit_window_seconds: int = Field(default=60, ge=1)
    login_rate_limit_lockout_seconds: int = Field(default=300, ge=1)

    # Approval action capability imzalayan HMAC anahtarı (business-token;
    # JWT ``jwt_secret``'tan ayrı tutulur — farklı içerik + yaşam süresi).
    # ``/actions/{token}/*`` akışı bu anahtarla imzalanır/çözülür.
    action_signing_secret: str = ""
    action_token_ttl_hours: int = Field(default=72, ge=1)
    public_action_base_url: str = "http://localhost:8058/approvals"

    # Comma-separated emails seeded into config_approvers (GENAI_APPROVAL).
    approver_emails: str = ""

    # Validate hook'unda action_signing_secret kontrolü: prod'da zorunlu,
    # dev/stg'de warning.

    # ---- helpers -------------------------------------------------------

    @property
    def is_production(self) -> bool:
        return self.environment == "prod"

    def validate_production(self) -> None:
        """Lifespan başlangıcında çağrılır; bilinçsiz unsafe kombinasyonu reddeder.

        Hata mesajları operatöre actionable olmalı — "3am sayımı" için değil,
        deploy anında fail-fast.
        """
        if not self.is_production:
            return
        problems: list[str] = []
        # Genel
        if not self.jwt_secret or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET >=32 chars required in prod")
        # Approval action HMAC anahtarı — login akışından ayrı tutulduğu
        # için ayrı doğrulanır.
        if not self.action_signing_secret or len(self.action_signing_secret) < 32:
            problems.append("ACTION_SIGNING_SECRET >=32 chars required in prod")
        if self.bootstrap_admin_enabled and (
            not self.bootstrap_admin_password
            or len(self.bootstrap_admin_password) < 12
        ):
            problems.append("BOOTSTRAP_ADMIN_PASSWORD >=12 chars required "
                            "(ya da BOOTSTRAP_ADMIN_ENABLED=false)")
        if self.bootstrap_admin_enabled and self.bootstrap_admin_password == "admin":
            problems.append("BOOTSTRAP_ADMIN_PASSWORD dev default 'admin' reddedildi")
        # LDAP block
        if self.ldap_enabled:
            if not self.ldap_use_ssl:
                problems.append("LDAP requires SSL (LDAPS)")
            if not self.ldap_tls_verify and not self.allow_prod_insecure_ldap_tls:
                problems.append("LDAP certificate verification is required "
                                "(set ALLOW_PROD_INSECURE_LDAP_TLS=true to override, insecure)")
            if not self.ldap_bind_dn or not self.ldap_bind_password:
                problems.append("LDAP_BIND_DN and LDAP_BIND_PASSWORD are required")
            if self.ldap_allow_local_fallback and not self.allow_prod_local_break_glass:
                problems.append("LDAP local fallback requires "
                                "ALLOW_PROD_LOCAL_BREAK_GLASS=true")
        if problems:
            raise RuntimeError(
                "Unsafe production configuration: " + "; ".join(problems)
            )


@lru_cache
def get_settings() -> Settings:
    return Settings()


def reset_settings_cache() -> None:
    """Test fixture'larında env değiştiğinde çağırılır."""
    get_settings.cache_clear()


__all__ = ["Settings", "get_settings", "reset_settings_cache"]
