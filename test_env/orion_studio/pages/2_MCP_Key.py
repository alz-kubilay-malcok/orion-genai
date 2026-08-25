"""MCP access-key webhook form."""

from __future__ import annotations

from orion_studio._signing import now_iso
from orion_studio.ui import (
    apply_chrome,
    post_webhook,
    render_sidebar,
    requester_fields,
    show_response,
)

apply_chrome("MCP Key")

ENVIRONMENTS = ("TEST", "STG", "PROD")
TOOL_OPTIONS = ("rag", "search", "read_file", "write_file", "summarise")


def main() -> None:
    import streamlit as st

    api_base, secret, sign = render_sidebar()
    st.title("MCP erişim anahtarı")
    st.caption("POST /webhooks/orion — talep_turu=mcp_erisim_anahtari")

    with st.form("mcp_key_form"):
        head = requester_fields(default_ticket="HD-20001")
        st.subheader("Kapsam")
        c1, c2 = st.columns(2)
        departman = c1.text_input("Departman adı", value="GENAI")
        ortam = c2.selectbox("Ortam", ENVIRONMENTS, index=2)
        aciklama = st.text_area("Talep açıklaması", value="Ajan uygulaması için MCP erişimi.")
        kullanim = st.text_area("Kullanım amacı", value="Kurumsal dokümanlarda arama.")
        sunucu = st.text_input("MCP sunucusu", value="document-search-prod")
        all_tools = st.checkbox("Tüm araçlara erişim", value=False)
        araclar = st.multiselect(
            "Araçlar",
            options=TOOL_OPTIONS,
            default=["rag", "search"],
            disabled=all_tools,
        )
        submitted = st.form_submit_button("Talebi gönder")

    if not submitted:
        return
    if not all_tools and len(araclar) < 1:
        st.error("tum_araclara_erisim=false iken en az bir araç seç.")
        return
    payload = {
        "talep_turu": "mcp_erisim_anahtari",
        "talep_no": head["talep_no"],
        "talep_url": head["talep_url"],
        "talep_eden_adi": head["talep_eden_adi"],
        "talep_eden_eposta": head["talep_eden_eposta"],
        "olusturulma_tarihi": now_iso(),
        "departman_adi": departman,
        "ortam": ortam,
        "talep_aciklamasi": aciklama,
        "kullanim_amaci": kullanim,
        "mcp_sunucusu": sunucu,
        "araclar": [] if all_tools else list(araclar),
        "tum_araclara_erisim": all_tools,
    }
    show_response(post_webhook(payload, api_base=api_base, secret=secret, sign=sign))


if __name__ in {"__main__", "app"}:
    main()
