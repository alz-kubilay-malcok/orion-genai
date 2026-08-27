#!/usr/bin/env python3
"""Orion → Panel webhook / katalog probe. Stdlib only.

    cp orion_probe/.env.example orion_probe/.env   # BASE_URL + HMAC_SECRET
    # payloads/*.json düzenle
    python orion_probe/probe.py                    # katalog + litellm + mcp key
    python orion_probe/probe.py catalog
    python orion_probe/probe.py litellm
    python orion_probe/probe.py mcp
    python orion_probe/probe.py --unique           # talep_no sonuna timestamp
"""

from __future__ import annotations

import argparse
import hashlib
import hmac
import json
import ssl
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urljoin

HERE = Path(__file__).resolve().parent
PAYLOAD_DIR = HERE / "payloads"
DEFAULT_ENV = HERE / ".env"
LITELLM_JSON = PAYLOAD_DIR / "litellm_api_anahtari.json"
MCP_JSON = PAYLOAD_DIR / "mcp_erisim_anahtari.json"
SIG_HEADER = "X-GenAi-Orion-Panel-Signature"


def _parse_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    if not path.is_file():
        raise SystemExit(f"env yok: {path}\n  cp {HERE / '.env.example'} {path}")
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.lower().startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        out[key.strip()] = value.strip().strip('"').strip("'")
    return out


def _cfg(env: dict[str, str]) -> tuple[str, str, str, str]:
    base = (
        env.get("BASE_URL")
        or env.get("ORION_PANEL_BASE_URL")
        or env.get("PUBLIC_BASE_URL")
        or ""
    ).rstrip("/")
    secret = (
        env.get("HMAC_SECRET")
        or env.get("GENAI_ORION_PANEL_WEBHOOK_SECRET")
        or ""
    ).strip()
    prefix = env.get("API_PREFIX", "/api").strip()
    if prefix in {"-", "none", "off"}:
        prefix = ""
    elif prefix and not prefix.startswith("/"):
        prefix = "/" + prefix
    ortam = (env.get("CATALOG_ORTAM") or "PROD").strip().upper()
    if not base:
        raise SystemExit("BASE_URL boş (.env)")
    if not secret:
        raise SystemExit("HMAC_SECRET boş (.env)")
    if ortam not in {"TEST", "PROD"}:
        raise SystemExit(f"CATALOG_ORTAM TEST|PROD olmalı, gelen: {ortam}")
    return base, secret, prefix, ortam


def _url(base: str, prefix: str, path: str) -> str:
    return urljoin(base + "/", (prefix + path).lstrip("/"))


def _dumps(payload: dict[str, Any]) -> bytes:
    return json.dumps(payload, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _sign(secret: str, body: bytes) -> str:
    return hmac.new(secret.encode("utf-8"), body, hashlib.sha256).hexdigest()


def _request(
    method: str,
    url: str,
    *,
    body: bytes | None = None,
    headers: dict[str, str] | None = None,
    timeout: float = 30.0,
) -> tuple[int, str]:
    req = urllib.request.Request(url, data=body, method=method, headers=headers or {})
    ctx = ssl.create_default_context()
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ctx) as resp:
            return resp.status, resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _print(title: str, status: int, raw: str) -> None:
    print(f"\n=== {title}  HTTP {status} ===")
    text = raw.strip() or "(empty)"
    try:
        print(json.dumps(json.loads(text), ensure_ascii=False, indent=2))
    except json.JSONDecodeError:
        print(text)


def _load_payload(path: Path, unique: bool) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if unique and isinstance(payload.get("talep_no"), str):
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S")
        payload["talep_no"] = f"{payload['talep_no']}-{stamp}"
        url = payload.get("talep_url")
        if isinstance(url, str):
            payload["talep_url"] = url.rsplit("/", 1)[0] + "/" + payload["talep_no"]
    return payload


def catalog(base: str, prefix: str, ortam: str) -> int:
    url = _url(base, prefix, f"/catalog/mcp-servers?ortam={ortam}")
    print(f"GET {url}")
    status, raw = _request("GET", url)
    _print("catalog", status, raw)
    return 0 if status == 200 else 1


def webhook(base: str, prefix: str, secret: str, path: Path, unique: bool) -> int:
    payload = _load_payload(path, unique)
    body = _dumps(payload)
    url = _url(base, prefix, "/webhooks/orion")
    headers = {
        "Content-Type": "application/json",
        SIG_HEADER: _sign(secret, body),
    }
    print(f"POST {url}")
    print(f"  talep_turu={payload.get('talep_turu')}  talep_no={payload.get('talep_no')}")
    status, raw = _request("POST", url, body=body, headers=headers)
    _print(path.name, status, raw)
    return 0 if status == 202 else 1


def main() -> int:
    parser = argparse.ArgumentParser(description="Orion panel katalog + HMAC webhook probe")
    parser.add_argument(
        "what",
        nargs="?",
        default="all",
        choices=["all", "catalog", "litellm", "mcp"],
        help="all = katalog + litellm + mcp key",
    )
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--ortam", choices=["TEST", "PROD"], help="katalog ortam (env CATALOG_ORTAM override)")
    parser.add_argument(
        "--unique",
        action="store_true",
        help="talep_no sonuna UTC timestamp ekle (duplicate 202'yi önler)",
    )
    args = parser.parse_args()

    base, secret, prefix, ortam = _cfg(_parse_env(args.env))
    if args.ortam:
        ortam = args.ortam

    print(f"BASE_URL={base}  API_PREFIX={prefix or '(yok)'}  CATALOG_ORTAM={ortam}")
    rc = 0
    if args.what in {"all", "catalog"}:
        rc |= catalog(base, prefix, ortam)
    if args.what in {"all", "litellm"}:
        rc |= webhook(base, prefix, secret, LITELLM_JSON, args.unique)
    if args.what in {"all", "mcp"}:
        rc |= webhook(base, prefix, secret, MCP_JSON, args.unique)
    return rc


if __name__ == "__main__":
    sys.exit(main())
