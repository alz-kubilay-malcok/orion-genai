"""Kılavuz §6 LDAP verification helper.

Üç adımda smoke-test:
  1. TCP pre-flight (``ldap.host:ldap.port``) — connect timeout ile.
  2. Anonymous bind + search ``(objectclass=person)`` — ILK 5 DN/sAM'yi yazdırır.
  3. Opsiyonel user-bind (``--bind-user``): service-account yerine test
     kullanıcısı ile bind + kendi attribute'larını çek.

Çıkış kodu:
  0 → tüm adımlar başarılı.
  1 → herhangi bir adım başarısız (LDAP unreachable / bind failed).

Kullanım::

    cd backend && python -m scripts.ldap_check
    cd backend && python -m scripts.ldap_check --bind-user kubilay
    cd backend && python -m scripts.ldap_check --host fake --port 389
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import sys

from ldap3 import Server, Connection, ALL, SUBTREE
from ldap3.core.exceptions import LDAPException
from backend.src.api.auth.ldap import _preflight, authenticate_ldap

from backend.src.observability.settings import get_settings, reset_settings_cache

logger = logging.getLogger(__name__)


async def _step1_tcp(host: str, port: int, timeout: int) -> bool:
    print(f"[1/3] TCP pre-flight {host}:{port} (timeout={timeout}s)...")
    try:
        await _preflight(host, port, timeout)
    except Exception as exc:  # noqa: BLE001 — Usage mesajında kapsama alınır
        print(f"  FAIL: {exc}")
        return False
    print("  OK")
    return True


async def _step2_anon_search(host: str, port: int, use_ssl: bool, base_dn: str) -> bool:
    """Anonymous bind + search.

    Çoğu prod AD anonymous search'ü kapatmıştır; bu adım schema doğrulama
    için bir TLS/socket kimliği denetimidir. Kişi listesini beklemeyin.
    """
    print(f"[2/3] Anonymous search {host}:{port} base='{base_dn}'...")
    server = Server(host, port=port, use_ssl=use_ssl, get_info=ALL, connect_timeout=5)
    try:
        conn = Connection(server, auto_bind=True, receive_timeout=5)
    except LDAPException as exc:
        print(f"  skip: anonymous bind rejected ({exc!r}). Sunucu anonymous'a kapalı — OK.")
        return True
    try:
        conn.search(
            search_base=base_dn,
            search_filter="(objectclass=person)",
            search_scope=SUBTREE,
            attributes=["sAMAccountName", "displayName", "mail"],
            size_limit=5,
        )
        entries = conn.entries
        print(f"  OK: {len(entries)} entry (ilk 5)")
        for entry in entries[:5]:
            print(f"    - {entry}")
    finally:
        try:
            conn.unbind()
        except Exception:  # noqa: BLE001
            pass
    return True


async def _step3_user_bind(settings, username: str, password: str) -> bool:
    """Service-account + kullanıcı adı/parola üzerinden bind."""
    print(f"[3/3] User bind '{username}' (LDAP enabled={settings.ldap_enabled})...")
    identity = await authenticate_ldap(username, password)
    if identity is None:
        print("  FAIL: bind veya attribute okuma başarısız")
        return False
    print("  OK")
    print(f"    dn           = {identity.dn}")
    print(f"    username     = {identity.username}")
    print(f"    email        = {identity.email}")
    print(f"    display_name = {identity.display_name}")
    print(f"    groups       = {identity.member_of[:5]}{' …' if len(identity.member_of) > 5 else ''}")
    return True


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--host", help="override LDAP host (default: settings)")
    parser.add_argument("--port", type=int, help="override LDAP port (default: settings)")
    parser.add_argument(
        "--bind-user",
        help="opsiyonel kullanıcı adı — adım 3'te kullanıcı-bind denemesi yapar",
    )
    return parser.parse_args()


async def _run() -> int:
    args = _parse_args()
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s %(name)s :: %(message)s")

    settings = get_settings()
    host = args.host or settings.ldap_host
    port = args.port or settings.ldap_port

    ok1 = await _step1_tcp(host, port, settings.ldap_connect_timeout)
    if not ok1:
        return 1
    try:
        ok2 = await _step2_anon_search(host, port, settings.ldap_use_ssl, settings.ldap_base_dn)
    except Exception as exc:  # noqa: BLE001
        print(f"  step2 exception: {exc}")
        ok2 = False

    ok3 = True
    if args.bind_user:
        import getpass

        password = getpass.getpass(f"Şifre ({args.bind_user}): ")
        try:
            ok3 = await _step3_user_bind(settings, args.bind_user, password)
        except Exception as exc:  # noqa: BLE001
            print(f"  step3 exception: {exc}")
            ok3 = False

    if not (ok1 and ok2 and ok3):
        return 1
    print("\nldap_check OK")
    return 0


def main() -> None:
    sys.exit(asyncio.run(_run()))


if __name__ == "__main__":
    main()
