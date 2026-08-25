"""Form page → POSTs a `talep_turu=mcp_erisim_anahtari` payload."""

from __future__ import annotations

import httpx
import streamlit as st

from orion_studio import (
    load_backend_env,
    make_signature,
    serialise,
)
from orion_studio._signing import DEFAULT_API_BASE_URL, now_iso  # noqa: E402

st.set_page_config(
    page_title="MCP Erişim Anahtarı Talebi",
    page_icon="🔧",
    layout="wide",
)

ENV = load_backend_env()
TALEP_TURU = "mcp_erisim_anahtari"
ENVIRONMENTS = ("TEST", "PROD")
TOOL_OPTIONS = ("read_file", "write_file", "search_docs", "summarise", "query_db")


def _sidebar() -> str:
    with st.sidebar:
        st.subheader("Hedef ayarları")
        api_base = st.text_input(
            "API temel URL'si",
            value=st.session_state.get("api_base", DEFAULT_API_BASE_URL),
            key="page2_api",
        )
        st.session_state["api_base"] = api_base
        secret = st.session_state.get(
            "orion_secret",
            ENV.get("GENAI_ORION_PANEL_WEBHOOK_SECRET", "dev-orion-secret"),
        )
        st.session_state["orion_secret"] = st.text_input(
            "Webhook gizli anahtarı",
            value=secret,
            type="password",
            key="page2_secret",
        )
        st.checkbox("HMAC imzalı gönder", value=True, key="page2_sign")
    return api_base


def _common_top() -> dict[str, str]:
    st.subheader("Talep sahibi")
    cols = st.columns(2)
    talep_no = cols[0].text_input("Talep no (Jira)", value="HD-20001")
    talep_url = cols[1].text_input(
        "Talep URL",
        value=f"https://orion.example.com/browse/{talep_no}",
    )
    cols2 = st.columns(2)
    adi = cols2[0].text_input("Talep eden adı", value="Dev User")
    posta = cols2[1].text_input("Talep eden e-posta", value="dev@example.com")
    return {
        "talep_no": talep_no,
        "talep_url": talep_url,
        "talep_eden_adi": adi,
        "talep_eden_eposta": posta,
    }


def main() -> None:
    st.title("🔧 MCP Erişim Anahtarı Talebi")
    st.caption(
        "Sunucu sahiplerinin MCP araçlarına kapsamlı erişim için anahtar isteği. Backend `MCPKeyPayload` bekliyor."
    )
    api_base = _sidebar()

    with st.form("mcp_key_form", clear_on_submit=False):
        head = _common_top()
        st.divider()
        st.subheader("Anahtar detayları")
        cols = st.columns(2)
        departman = cols[0].text_input("Departman adı", value="MCP Operasyon")
        aciklama = st.text_area("Talep açıklaması", value="Araç çağrıları için 1 haftalık test anahtarı.")
        kullanim_amaci = st.text_area("Kullanım amacı", value="MCP entegrasyon testleri")
        sunucu = cols[0].text_input("MCP sunucusu (slug)", value="policy-qa")
        all_tools = cols[1].checkbox(
            "Tüm araçlara erişim",
            value=False,
            help="İşaretlenirse araç listesi boş bırakılmalı.",
        )
        araclar = st.multiselect(
            "Araçlar",
            options=TOOL_OPTIONS,
            default=("read_file", "search_docs"),
            disabled=all_tools,
        )
        if all_tools:
            araclar = []

        cols2 = st.columns(2)
        submitted = cols2[0].form_submit_button("Talebi gönder")

    if submitted:
        if not all_tools and len(araclar) < 1:
            st.error("Araç listesi boş olamaz (tüm araçlara erişim seçili değilken).")
        elif all_tools and araclar:
            st.error("Tüm araçlara erişim seçildiğinde araç listesi boş olmalıdır.")
        else:
            payload = {
                "talep_turu": TALEP_TURU,
                "talep_no": head["talep_no"],
                "talep_url": head["talep_url"],
                "talep_eden_adi": head["talep_eden_adi"],
                "talep_eden_eposta": head["talep_eden_eposta"],
                "olusturulma_tarihi": now_iso(),
                "departman_adi": departman,
                "talep_aciklamasi": aciklama,
                "kullanim_amaci": kullanim_amaci,
                "mcp_sunucusu": sunucu,
                "araclar": list(araclar),
                "tum_araclara_erisim": all_tools,
            }
            body = serialise(payload)
            signed = make_signature(st.session_state["orion_secret"], body)
            headers = {
                "Content-Type": "application/json",
                "x-genai-orion-panel-signature": signed,
            }
            with httpx.Client(timeout=10.0) as client:
                response = client.post(
                    f"{api_base.rstrip('/')}/webhooks/orion",
                    content=body,
                    headers=headers,
                )
            if response.status_code == 202:
                st.success(f"HTTP 202 — {response.text[:600]}")
            else:
                st.error(f"HTTP {response.status_code} — {response.text[:600]}")

    with st.expander("İpucu"):
        st.write(
            "Backend `MCPKeyPayload` şu kuralı uygular: `tum_araclara_erisim=true` ⇒ `araclar=[]`, "
            "`false` ⇒ `len(araclar) ≥ 1`. Alanlar otomatik olarak tekrarlardan arındırılır."
        )


if __name__ in {"__main__", "app"}:
    main()
