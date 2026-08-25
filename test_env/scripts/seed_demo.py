"""Seed demo: POSTs three signed requests (one of each type) to the API.

Uses the same HMAC path as the Streamlit panel. Run after backend + mock are up.
"""

from __future__ import annotations

import random
import sys
import time
from typing import Callable

_PKG_PARENT = os.path.abspath(os.path.join(os.path.dirname(__file__), os.pardir))
if _PKG_PARENT not in sys.path:
    sys.path.insert(0, _PKG_PARENT)

from orion_studio._signing import (
    DEFAULT_API_BASE_URL,
    now_iso,
    serialise,
)
from orion_studio import (
    load_backend_env,
    make_signature,
)

BACKEND = DEFAULT_API_BASE_URL
WEBHOOK_PATH = "/webhooks/orion"


def _build_litellm(ticket: str) -> dict[str, object]:
    return {
        "talep_turu": "litellm_api_anahtari",
        "talep_no": ticket,
        "talep_url": f"https://orion.local/browse/{ticket}",
        "talep_eden_adi": "Demo User",
        "talep_eden_eposta": "demo@example.local",
        "olusturulma_tarihi": now_iso(),
        "departman_adi": "Demo Departman",
        "ortam": "DEV",
        "talep_aciklamasi": "Seed demo talep",
        "kullanim_amaci": "CHAT",
        "kullanim_senaryosu": "smoke",
        "modeller": ["allianz-text", "allianz-text-small"],
        "yanit_suresi": "realtime",
        "kullanim_sikligi": "10_100",
        "tahmini_gunluk_istek": 50,
        "maksimum_es_zamanli_istek": 2,
        "ortalama_girdi_sayfasi": 3.0,
        "ortalama_cikti_sayfasi": 1.0,
    }


def _build_mcp_key(ticket: str) -> dict[str, object]:
    return {
        "talep_turu": "mcp_erisim_anahtari",
        "talep_no": ticket,
        "talep_url": f"https://orion.local/browse/{ticket}",
        "talep_eden_adi": "Demo User",
        "talep_eden_eposta": "demo@example.local",
        "olusturulma_tarihi": now_iso(),
        "departman_adi": "Demo Departman",
        "ortam": "PROD",
        "talep_aciklamasi": "Seed demo MCP key",
        "kullanim_amaci": "smoke",
        "mcp_sunucusu": "policy-qa",
        "araclar": ["read_file", "search_docs"],
        "tum_araclara_erisim": False,
    }


def _build_mcp_registry(ticket: str) -> dict[str, object]:
    slug = "demo-server"
    return {
        "talep_turu": "mcp_sunucu_kaydi",
        "talep_no": ticket,
        "talep_url": f"https://orion.local/browse/{ticket}",
        "talep_eden_adi": "Demo User",
        "talep_eden_eposta": "demo@example.local",
        "olusturulma_tarihi": now_iso(),
        "departman_adi": "Demo Departman",
        "mcp_sunucu_adi": "Demo Server",
        "proje_adi": slug,
        "teknik_sorumlu_eposta": "oncall@example.local",
        "kullanim_amaci": "smoke",
        "repo_platformu": "GITHUB",
        "repo_url": f"https://github.com/allianz/{slug}",
        "devops_jira_no": "DEVOPS-42",
        "ortam": "TEST",
        "mcp_endpoint_url": f"https://test-mcp.allianz-tr.local/{slug}/mcp",
        "minimum_evaluation_skoru": 95,
    }


BUILDERS: dict[str, Callable[[str], dict[str, object]]] = {
    "litellm": _build_litellm,
    "mcp_key": _build_mcp_key,
    "mcp_registry": _build_mcp_registry,
}


def _post(secret: str, api_base: str, payload: dict[str, object]) -> int:
    import httpx

    body = serialise(payload)
    headers = {
        "Content-Type": "application/json",
        "x-genai-orion-panel-signature": make_signature(secret, body),
    }
    with httpx.Client(timeout=10.0) as client:
        response = client.post(
            f"{api_base.rstrip('/')}{WEBHOOK_PATH}",
            content=body,
            headers=headers,
        )
    return response.status_code


def main(argv: list[str] | None = None) -> int:
    env = load_backend_env()
    secret = env.get("GENAI_ORION_PANEL_WEBHOOK_SECRET", "dev-orion-secret")
    api_base = env.get("ORION_STUDIO_API_BASE", BACKEND)
    argv = argv if argv is not None else sys.argv[1:]
    only = set(argv)
    rng = random.Random(int(time.time()))

    for kind, builder in BUILDERS.items():
        if only and kind not in only:
            continue
        ticket = f"HD-{rng.randint(10000, 99999)}"
        payload = builder(ticket)
        status = _post(secret, api_base, payload)
        print(f"{kind:12s} ticket={ticket} -> HTTP {status}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
