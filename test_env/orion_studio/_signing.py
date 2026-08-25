"""Helpers shared by the Streamlit webhook form pages.

Loads `backend/.env` using stdlib only, computes HMAC-SHA256 over a
JSON body exactly like :mod:`backend.src.api.middleware.webhook_auth`
does, and POSTs the payload to `/webhooks/orion`.

Backend'in eski ``/auth/login`` + session cookie + ``/admin/mail/messages``
yüzeyi kaldırıldığı için bu modüldeki ``login_admin`` / ``mark_mail_read``
vb. helper'lar da silindi. Mailbox sayfası artık ``db/orion.db`` üzerinden
salt okunur bağlanır (sayfa-5 kendi içinde).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKEND_ENV_FILE = REPO_ROOT / "backend" / ".env"
DEFAULT_API_BASE_URL = "http://127.0.0.1:8001"
DEFAULT_WEBHOOK_PATH = "/webhooks/orion"


def load_backend_env(force_reload: bool = False) -> dict[str, str]:
    """Read simple KEY=VALUE lines from `backend/.env` and seed os.environ.

    Honours `export`, `set`, and bare `KEY=VALUE` forms; ignores `#` comments.
    Returns the parsed map so callers can show users the resolved values.
    """
    cache: dict[str, str] = {}
    if not BACKEND_ENV_FILE.exists():
        return cache
    for raw in BACKEND_ENV_FILE.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        elif line.lower().startswith("set "):
            line = line[4:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        cache[key] = value
        if force_reload or key not in os.environ:
            os.environ[key] = value
    return cache


def make_signature(secret: str, body: bytes) -> str:
    """Lowercase hex HMAC-SHA256 like the FastAPI middleware expects."""
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def now_iso() -> str:
    """ISO-8601 UTC with offset (matches Pydantic EmailStr/HttpUrl expectations)."""
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def serialise(payload: dict[str, Any]) -> bytes:
    """Serialise with `separators=(",", ":")` to match what tests curl against."""
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def post_orion_webhook(
    payload: dict[str, Any],
    *,
    api_base_url: str,
    secret: str,
    sign: bool,
    timeout_seconds: float = 10.0,
) -> httpx.Response:
    """Submit a flat Orion payload; mirror the failing-path options too."""
    body = serialise(payload)
    headers = {"Content-Type": "application/json"}
    if sign and secret:
        headers["x-genai-orion-panel-signature"] = make_signature(secret, body)
    url = api_base_url.rstrip("/") + DEFAULT_WEBHOOK_PATH
    with httpx.Client(timeout=timeout_seconds) as client:
        return client.post(url, content=body, headers=headers)


def render_metadata(builder: Any) -> None:
    """Display submission metadata in a consistent block at the top of each page."""
    env = load_backend_env()
    api_base = os.getenv("ORION_API_BASE", env.get("ORION_API_BASE", DEFAULT_API_BASE_URL))
    secret_signing = bool(os.getenv("GENAI_ORION_PANEL_WEBHOOK_SECRET", env.get("GENAI_ORION_PANEL_WEBHOOK_SECRET")))
    auth_mode = os.getenv("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", env.get("GENAI_ORION_PANEL_WEBHOOK_AUTH_MODE", "hmac"))
    with builder.container(border=True):
        lc, rc, lc2, rc2 = builder.columns(4)
        lc.metric("API base", api_base.replace("http://", "").replace("https://", ""))
        rc.metric("Webhook path", DEFAULT_WEBHOOK_PATH)
        lc2.metric("Auth mode", auth_mode)
        rc2.metric("Secret present", "✅" if secret_signing else "⚠️ yok")
