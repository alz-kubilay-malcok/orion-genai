"""Orion Studio — local webhook + mailbox harness."""

from __future__ import annotations

import os

import httpx
import streamlit as st

from orion_studio._signing import (
    DEFAULT_API_BASE_URL,
    DEFAULT_FRONTEND_BASE_URL,
    DEFAULT_MOCK_URL,
    load_backend_env,
)
from orion_studio.ui import apply_chrome, render_sidebar

apply_chrome("Orion Studio")
load_backend_env()


def _ping(url: str, path: str = "/health/live") -> tuple[bool, str]:
    try:
        response = httpx.get(f"{url.rstrip('/')}{path}", timeout=2.0)
    except httpx.HTTPError as exc:
        return False, exc.__class__.__name__
    ok = response.status_code in {200, 204, 401}
    return ok, f"HTTP {response.status_code}"


def main() -> None:
    api_base, _secret, _sign = render_sidebar()
    mock_base = os.getenv("MOCK_LITELLM_URL", DEFAULT_MOCK_URL)
    frontend = os.getenv("PUBLIC_ACTION_BASE_URL", DEFAULT_FRONTEND_BASE_URL)
    frontend_origin = frontend.rsplit("/approvals", 1)[0] or "http://localhost:3000"

    st.title("Orion Studio")
    st.caption(
        "Yerel test suite: webhook formu, mailbox HTML önizleme, "
        "onay aksiyonları frontend’e açılır."
    )

    api_ok, api_msg = _ping(api_base)
    mock_ok, mock_msg = _ping(mock_base)
    fe_ok, fe_msg = _ping(frontend_origin, "/")
    c1, c2, c3 = st.columns(3)
    c1.metric("API", "up" if api_ok else "down", api_msg)
    c2.metric("Frontend", "up" if fe_ok else "down", fe_msg)
    c3.metric("Mock LiteLLM", "up" if mock_ok else "down", mock_msg)

    st.divider()
    st.subheader("Akış")
    st.markdown(
        """
1. LiteLLM Key, MCP Key veya MCP Registry formunu gönder.
2. Worker onay mailini `test_env/mailbox` altına yazar.
3. Mailbox’ta HTML’i gör; Onayla / Revize / Reddet frontend onay sayfasına gider.
4. Talepler sayfası Postgres `requests` tablosunu listeler.
        """
    )
    st.caption(f"API `{api_base.replace('http://', '')}` · Frontend `{frontend_origin}`")

    nav1, nav2, nav3 = st.columns(3)
    with nav1:
        st.page_link("pages/1_LiteLLM_Key.py", label="LiteLLM Key")
        st.page_link("pages/2_MCP_Key.py", label="MCP Key")
    with nav2:
        st.page_link("pages/3_MCP_Registry.py", label="MCP Registry")
        st.page_link("pages/4_Mailbox.py", label="Mailbox")
    with nav3:
        st.page_link("pages/5_Requests.py", label="Talepler")
        st.link_button("Admin panel", f"{frontend_origin}/admin")


if __name__ in {"__main__", "app"}:
    main()
