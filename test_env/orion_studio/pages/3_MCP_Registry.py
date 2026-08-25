"""MCP server registry webhook form."""

from __future__ import annotations

import re

from orion_studio._signing import now_iso
from orion_studio.ui import (
    apply_chrome,
    post_webhook,
    render_sidebar,
    requester_fields,
    show_response,
)

apply_chrome("MCP Registry")

ENVIRONMENTS = ("TEST", "PROD")
REPO_PLATFORMS = ("GITHUB", "BITBUCKET")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def _endpoint(ortam: str, slug: str) -> str:
    if not SLUG_RE.match(slug or ""):
        return ""
    host = "test-mcp.allianz-tr.local" if ortam == "TEST" else "mcp.allianz-tr.local"
    return f"https://{host}/{slug}/mcp"


def main() -> None:
    import streamlit as st

    api_base, secret, sign = render_sidebar()
    st.title("MCP sunucu kaydı")
    st.caption("POST /webhooks/orion — talep_turu=mcp_sunucu_kaydi")

    with st.form("mcp_registry_form"):
        head = requester_fields(default_ticket="HD-30001")
        st.subheader("Sunucu")
        c1, c2 = st.columns(2)
        departman = c1.text_input("Departman adı", value="GENAI")
        sunucu_adi = c2.text_input("MCP sunucu adı", value="Doküman Arama MCP")
        c3, c4 = st.columns(2)
        proje = c3.text_input("Proje adı", value="document-search")
        teknik = c4.text_input("Teknik sorumlu e-posta", value="mcp-owner@allianz.com.tr")
        c5, c6 = st.columns(2)
        repo_platformu = c5.selectbox("Repo platformu", REPO_PLATFORMS, index=1)
        ortam = c6.selectbox("Ortam", ENVIRONMENTS, index=1)
        repo_url = st.text_input(
            "Repo URL",
            value="https://sdlc.allianz.com.tr/stash/projects/ALLMCP/repos/document-search",
        )
        jira = st.text_input("DevOps Jira no", value="ATL-12345")
        endpoint = st.text_input("MCP endpoint URL", value=_endpoint(ortam, proje))
        kullanim = st.text_area(
            "Kullanım amacı",
            value="Ajanların kurumsal dokümanlarda arama yapmasını sağlar.",
        )
        min_eval = st.number_input("Minimum evaluation skoru", min_value=0, max_value=100, value=94)
        notlar = st.text_area("Ek notlar", value="")
        submitted = st.form_submit_button("Talebi gönder")

    if not submitted:
        return
    if not SLUG_RE.match(proje or ""):
        st.error("proje_adi küçük harf, rakam ve tire olmalı.")
        return
    payload: dict[str, object] = {
        "talep_turu": "mcp_sunucu_kaydi",
        "talep_no": head["talep_no"],
        "talep_url": head["talep_url"],
        "talep_eden_adi": head["talep_eden_adi"],
        "talep_eden_eposta": head["talep_eden_eposta"],
        "olusturulma_tarihi": now_iso(),
        "departman_adi": departman,
        "ortam": ortam,
        "mcp_sunucu_adi": sunucu_adi,
        "proje_adi": proje,
        "teknik_sorumlu_eposta": teknik,
        "kullanim_amaci": kullanim,
        "repo_platformu": repo_platformu,
        "repo_url": repo_url,
        "mcp_endpoint_url": endpoint or _endpoint(ortam, proje),
        "minimum_evaluation_skoru": int(min_eval),
    }
    if jira.strip():
        payload["devops_jira_no"] = jira.strip()
    if notlar.strip():
        payload["ek_notlar"] = notlar.strip()
    show_response(post_webhook(payload, api_base=api_base, secret=secret, sign=sign))


if __name__ in {"__main__", "app"}:
    main()
