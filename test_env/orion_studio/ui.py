"""Shared Streamlit chrome and webhook submit helper."""

from __future__ import annotations

import os

import httpx
import streamlit as st

from orion_studio._signing import (
    DEFAULT_API_BASE_URL,
    DEFAULT_FRONTEND_BASE_URL,
    DEFAULT_MOCK_URL,
    load_backend_env,
    make_signature,
    serialise,
)

_CSS = """
<style>
    #MainMenu, header, footer, [data-testid="stToolbar"],
    [data-testid="stDecoration"], [data-testid="stStatusWidget"] {
        visibility: hidden;
        height: 0;
    }
    .stApp { background: #f4f6f8; color: #1a1f2e; }
    .block-container {
        padding-top: 1.75rem;
        padding-bottom: 3rem;
        max-width: 1120px;
    }
    h1 {
        font-size: 1.45rem;
        font-weight: 600;
        letter-spacing: -0.02em;
        color: #0a3370;
        margin-bottom: 0.15rem;
    }
    [data-testid="stSidebar"] {
        background: #0a3370;
        border-right: none;
    }
    [data-testid="stSidebar"] .stMarkdown p,
    [data-testid="stSidebar"] label,
    [data-testid="stSidebar"] .stCaption,
    [data-testid="stSidebarNav"] span {
        color: #f4f6f8 !important;
    }
    [data-testid="stSidebar"] input {
        color: #1a1f2e !important;
        background: #fff !important;
    }
    [data-testid="stSidebarNav"] [data-testid="stSidebarNavLink"] {
        border-radius: 6px;
    }
    div[data-testid="stMetric"] {
        background: #fff;
        border: 1px solid #d8dde3;
        border-radius: 8px;
        padding: 12px 16px;
    }
    .stButton > button, .stFormSubmitButton > button, .stLinkButton > a {
        border-radius: 6px;
        font-weight: 600;
    }
</style>
"""


def apply_chrome(page_title: str) -> None:
    st.set_page_config(
        page_title=page_title,
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.markdown(_CSS, unsafe_allow_html=True)


def render_sidebar() -> tuple[str, str, bool]:
    env = load_backend_env()
    with st.sidebar:
        st.markdown("**Hedef servisler**")
        api_base = st.text_input(
            "API",
            value=st.session_state.get(
                "api_base",
                os.getenv(
                    "ORION_STUDIO_API_BASE",
                    env.get("ORION_STUDIO_API_BASE", DEFAULT_API_BASE_URL),
                ),
            ),
            key="api_base",
        )
        st.text_input(
            "Frontend",
            value=os.getenv("PUBLIC_ACTION_BASE_URL", DEFAULT_FRONTEND_BASE_URL),
            disabled=True,
            help="Mail aksiyon linkleri bu tabana yazılır (PUBLIC_ACTION_BASE_URL).",
        )
        st.text_input(
            "Mock LiteLLM",
            value=os.getenv("MOCK_LITELLM_URL", DEFAULT_MOCK_URL),
            disabled=True,
        )
        secret = st.text_input(
            "Webhook HMAC secret",
            value=st.session_state.get(
                "orion_secret",
                env.get("GENAI_ORION_PANEL_WEBHOOK_SECRET", "dev-orion-secret"),
            ),
            type="password",
            key="orion_secret",
        )
        sign = st.checkbox("HMAC imzala", value=True, key="sign_webhook")
        st.caption("API 8056 · Frontend 8058 · Mock 8200")
    return api_base, secret, sign


def post_webhook(payload: dict, *, api_base: str, secret: str, sign: bool) -> httpx.Response:
    body = serialise(payload)
    headers = {"Content-Type": "application/json"}
    if sign and secret:
        headers["x-genai-orion-panel-signature"] = make_signature(secret, body)
    url = api_base.rstrip("/") + "/webhooks/orion"
    with httpx.Client(timeout=12.0) as client:
        return client.post(url, content=body, headers=headers)


def show_response(response: httpx.Response) -> None:
    text = response.text[:800]
    if response.status_code == 202:
        st.success(f"HTTP 202 — {text}")
    else:
        st.error(f"HTTP {response.status_code} — {text}")


def requester_fields(*, default_ticket: str) -> dict[str, str]:
    st.subheader("Talep sahibi")
    c1, c2 = st.columns(2)
    talep_no = c1.text_input("Talep no", value=default_ticket)
    talep_url = c2.text_input(
        "Talep URL",
        value=f"https://orion.example.com/browse/{talep_no}",
    )
    c3, c4 = st.columns(2)
    adi = c3.text_input("Talep eden adı", value="Dev User")
    posta = c4.text_input("Talep eden e-posta", value="dev@example.com")
    return {
        "talep_no": talep_no,
        "talep_url": talep_url,
        "talep_eden_adi": adi,
        "talep_eden_eposta": posta,
    }
