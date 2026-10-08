"""Copilot roster — LiteLLM key üretildikten sonra kişi kaydı.

``POST {COPILOT_ROSTER_BASE_URL}/roster``
Başlık: ``X-Admin-Token``. Ham anahtar serviste SHA-256'ya çevrilir.
URL veya token boşsa no-op. Ağ / HTTP hatası anahtar üretimini düşürmez.
"""

from __future__ import annotations

import logging
import os

logger = logging.getLogger(__name__)

_TIMEOUT_SECONDS = 15.0


def _base_url() -> str:
    return (os.getenv("COPILOT_ROSTER_BASE_URL") or "").strip().rstrip("/")


def _admin_token() -> str:
    return (os.getenv("COPILOT_ROSTER_ADMIN_TOKEN") or "").strip()


async def register_roster_member(
    *,
    api_key: str,
    full_name: str,
    team_id: str,
    email: str = "",
) -> bool:
    """Kişiyi roster'a ekler veya aynı anahtarda günceller.

    Başarıda ``True``. Atlanırsa veya hata olursa ``False``; exception yükselmez.
    """
    key = (api_key or "").strip()
    name = (full_name or "").strip()
    team = (team_id or "").strip()
    base = _base_url()
    token = _admin_token()
    if not base or not token:
        logger.info("copilot roster skipped: base url or admin token empty")
        return False
    if not key or not name or not team:
        logger.warning(
            "copilot roster skipped: api_key/full_name/team_id eksik name=%s team=%s",
            bool(name),
            bool(team),
        )
        return False

    import httpx

    body: dict[str, str] = {
        "api_key": key,
        "full_name": name,
        "team_id": team,
    }
    mail = (email or "").strip()
    if mail:
        body["email"] = mail
    url = f"{base}/roster"
    try:
        async with httpx.AsyncClient(timeout=_TIMEOUT_SECONDS, trust_env=False) as client:
            response = await client.post(
                url,
                headers={
                    "X-Admin-Token": token,
                    "Content-Type": "application/json",
                },
                json=body,
            )
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("copilot roster unreachable: %s", exc)
        return False
    if response.status_code >= 400:
        logger.warning(
            "copilot roster http %s: %s",
            response.status_code,
            (response.text or "")[:300],
        )
        return False
    logger.info("copilot roster ok team=%s", team)
    return True


__all__ = ["register_roster_member"]
