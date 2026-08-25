"""Orion Studio — Streamlit harness entry point.

Run from the repo root:
    streamlit run test_env/orion_studio/app.py --server.port 8501

Pages in `pages/` are auto-discovered by Streamlit.
"""

from __future__ import annotations

import os
import pathlib
import sys

import httpx
import streamlit as st

# Ensure the sibling module file (_signing.py) is importable regardless of which
# tool launched Streamlit. Pages reuse the same bootstrap.
_HERE = pathlib.Path(__file__).resolve().parent
if str(_HERE) not in sys.path:
    sys.path.insert(0, str(_HERE))

from orion_studio import (
    load_backend_env,
    make_signature,
    serialise,
)
from orion_studio._signing import DEFAULT_API_BASE_URL, now_iso  # noqa: E402

st.set_page_config(
    page_title="Orion Studio",
    page_icon="🛠",
    layout="wide",
    initial_sidebar_state="expanded",
)

ENV = load_backend_env()


def _ping_mock(url: str) -> tuple[bool, str]:
    try:
        response = httpx.get(f"{url.rstrip('/')}/health/live", timeout=2.0)
    except httpx.HTTPError as exc:  # noqa: BLE001 — surface any failure to the operator
        return False, f"connection error: {exc!s}"
    if response.status_code == 200:
        return True, "ok"
    return False, f"http {response.status_code}"


def _ping_api(url: str) -> tuple[bool, str]:
    try:
        response = httpx.get(f"{url.rstrip('/')}/health/live", timeout=2.0)
    except httpx.HTTPError as exc:  # noqa: BLE001
        return False, f"connection error: {exc!s}"
    if response.status_code in (200, 204):
        return True, f"http {response.status_code}"
    return False, f"http {response.status_code}"


def main() -> None:
    st.title("🛠 Orion Studio — talep simülatörü")
    st.caption("`/webhooks/orion` uç noktasına talep göndererek uygulamayı doğrulamak için interaktif UI.")

    with st.sidebar:
        st.subheader("Hedef ayarları")
        api_base = st.text_input(
            "API temel URL'si",
            value=os.getenv("ORION_API_BASE", DEFAULT_API_BASE_URL),
            help="Genellikle http://127.0.0.1:8001",
        )
        mock_base = st.text_input(
            "Mock LiteLLM URL'si",
            value=os.getenv("MOCK_LITELLM_URL", "http://127.0.0.1:8200"),
            help="mock_litellm uvicorn host:port",
        )
        secret = st.session_state.get(
            "orion_secret",
            ENV.get("GENAI_ORION_PANEL_WEBHOOK_SECRET", "dev-orion-secret"),
        )
        st.session_state["orion_secret"] = st.text_input(
            "Webhook gizli anahtarı (HMAC)",
            value=secret,
            type="password",
            help="backend/.env dosyasındaki GENAI_ORION_PANEL_WEBHOOK_SECRET",
        )
        should_sign = st.checkbox(
            "İstekleri HMAC ile imzala",
            value=True,
            help="İşareti kaldırmak yalnızca geliştirme amaçlıdır; PROTECTED_PATHS bug'ı çözülünce 401 alırsınız.",
        )

    cols = st.columns(2)
    api_ok, api_msg = _ping_api(api_base)
    mock_ok, mock_msg = _ping_mock(mock_base)
    cols[0].metric("Backend API", "✅" if api_ok else "❌", api_msg)
    cols[1].metric("Mock LiteLLM", "✅" if mock_ok else "❌", mock_msg)

    st.divider()
    st.subheader("Hazır talep şablonları")
    st.write(
        "Sol menüden herhangi bir form sayfasını açın; HMAC ile imzalanmış olarak backend'e POST edilir. "
        "Sonuçlar (202 → `request_id`) burada ve `Inspect / webhooks / orion` sayfasında görünür."
    )

    st.subheader("Hızlı ping")
    with st.form("quick_ping", clear_on_submit=True):
        ticket_no = st.text_input("Talep no", value="HD-99999")
        submitted = st.form_submit_button("Sağlık ping'i at")
    if submitted:
        payload = {
            "talep_turu": "litellm_api_anahtari",
            "talep_no": ticket_no,
            "talep_url": "https://orion.local/browse/HD-99999",
            "talep_eden_adi": "Orion Studio Smoke",
            "talep_eden_eposta": "studio@example.com",
            "olusturulma_tarihi": now_iso(),
        }
        body = serialise(payload)
        headers = {"Content-Type": "application/json"}
        if should_sign:
            headers["x-genai-orion-panel-signature"] = make_signature(
                st.session_state["orion_secret"], body
            )
        with httpx.Client(timeout=8.0) as client:
            response = client.post(
                f"{api_base.rstrip('/')}/webhooks/orion",
                content=body,
                headers=headers,
            )
        st.write(f"HTTP {response.status_code}: {response.text[:300]}")


if __name__ in {"__main__", "app"}:  # both `streamlit run` and `python app.py`
    main()
