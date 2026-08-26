"""Enterprise LDAP authentication (LDAPS + bind-as-user against Active Directory).

Kılavuz §4.2 — aşağıdaki 5 invariant korunmuştur:
1. _preflight: off-network <5s fail (TLS handshake 60-75s sürmesin).
2. auto_referrals=False: AD `ForestDnsZones.*` container DNS'te
   resolve edilmez; chase → LDAPSocketOpenError.
3. _ldap_escape: RFC-4515 escape; filter injection tek savunma hattı.
4. İkinci bağlantı ile user-bind: service account kullanıcı parolasını
   görmemeli; başarısız user-bind service conn'u kirletmemeli.
5. finally: service.unbind() → DC connection table'ı tükenmesin.

``asyncio.to_thread`` ile event loop'u bloklamadan çalışır.
"""

from __future__ import annotations

import asyncio
import logging
import socket
import ssl
from dataclasses import dataclass, field

from ldap3 import ALL, SUBTREE, Connection, Server, Tls
from ldap3.core.exceptions import LDAPException

from backend.src.observability.settings import get_settings

logger = logging.getLogger(__name__)


class LdapUnavailableError(Exception):
    """Directory'ye erişilemedi (network/TLS) — auth failure'dan ayrı tutulur."""


@dataclass
class LdapIdentity:
    dn: str
    username: str
    email: str | None = None
    display_name: str | None = None
    group_dns: list[str] = field(default_factory=list)


def _ldap_escape(value: str) -> str:
    """RFC-4515 search-filter escape."""
    replacements = {
        "\\": "\\5c",
        "*": "\\2a",
        "(": "\\28",
        ")": "\\29",
        "\x00": "\\00",
        "/": "\\2f",
    }
    return "".join(replacements.get(ch, ch) for ch in value)


def _preflight(host: str, port: int, timeout: int) -> None:
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return
    except OSError as exc:
        raise LdapUnavailableError(
            f"LDAP host {host}:{port} unreachable: {exc}"
        ) from exc


def _attr_values(entry: object, attr: str) -> list[str]:
    try:
        raw = entry[attr].values  # type: ignore[index]
    except (KeyError, LDAPException, AttributeError):
        return []
    return [str(v) for v in raw]


def _normalize_ca_pem(raw: str) -> str:
    """Env'deki PEM: tırnak, `\\n`, CRLF → ldap3 `ca_certs_data`."""
    text = raw.strip().strip('"').strip("'")
    if not text:
        return ""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    if "\\n" in text and "-----BEGIN" in text:
        text = text.replace("\\n", "\n")
    return text.strip()


def _build_server() -> Server:
    settings = get_settings()
    tls = None
    if settings.ldap_use_ssl:
        validate = ssl.CERT_REQUIRED if settings.ldap_tls_verify else ssl.CERT_NONE
        pem = _normalize_ca_pem(settings.ldap_ca_cert_pem or "")
        if pem:
            tls = Tls(validate=validate, ca_certs_data=pem)
        else:
            ca_file = (settings.ldap_ca_cert or "").strip() or None
            tls = Tls(validate=validate, ca_certs_file=ca_file)
    return Server(
        settings.ldap_host,
        port=settings.ldap_port,
        use_ssl=settings.ldap_use_ssl,
        tls=tls,
        connect_timeout=settings.ldap_connect_timeout,
        get_info=ALL,
    )


def _authenticate_sync(username: str, password: str) -> LdapIdentity | None:
    settings = get_settings()
    _preflight(settings.ldap_host, settings.ldap_port, settings.ldap_connect_timeout)

    try:
        server = _build_server()
        service = Connection(
            server,
            user=settings.ldap_bind_dn or None,
            password=settings.ldap_bind_password or None,
            auto_bind=True,
            auto_referrals=False,  # AD ForestDnsZones.* container'da resolve olmaz
        )
    except LDAPException as exc:
        raise LdapUnavailableError(f"LDAP service bind failed: {exc}") from exc

    try:
        safe_user = _ldap_escape(username)
        group_clause = ""
        if settings.ldap_required_group:
            group_clause = (
                f"({settings.ldap_group_member_attr}"
                f"={settings.ldap_required_group})"
            )
        search_filter = (
            f"(&(objectClass={settings.ldap_object_class})"
            f"({settings.ldap_user_attr}={safe_user}){group_clause})"
        )
        service.search(
            settings.ldap_base_dn,
            search_filter,
            search_scope=SUBTREE,
            attributes=[
                settings.ldap_mail_attr,
                settings.ldap_display_name_attr,
                settings.ldap_group_member_attr,
            ],
        )
        if not service.entries:
            logger.info("LDAP: user not found or not in required group: %s", username)
            return None

        entry = service.entries[0]
        user_dn = entry.entry_dn
        emails = _attr_values(entry, settings.ldap_mail_attr)
        names = _attr_values(entry, settings.ldap_display_name_attr)
        groups = _attr_values(entry, settings.ldap_group_member_attr)
    finally:
        service.unbind()

    # Verify password by binding as the user (separate connection).
    try:
        user_conn = Connection(server, user=user_dn, password=password)
        if not user_conn.bind():
            logger.info("LDAP: password bind failed for %s", user_dn)
            return None
        user_conn.unbind()
    except LDAPException as exc:
        raise LdapUnavailableError(f"LDAP user bind error: {exc}") from exc

    return LdapIdentity(
        dn=user_dn,
        username=username,
        email=emails[0] if emails else None,
        display_name=names[0] if names else None,
        group_dns=groups,
    )


async def authenticate_ldap(username: str, password: str) -> LdapIdentity | None:
    """LDAP authentication. ``LdapUnavailableError`` network/TLS sorunlarında;
    ``None`` invalid creds / user-not-found / not-in-group için."""
    return await asyncio.to_thread(_authenticate_sync, username, password)


__all__ = [
    "LdapIdentity",
    "LdapUnavailableError",
    "authenticate_ldap",
]
