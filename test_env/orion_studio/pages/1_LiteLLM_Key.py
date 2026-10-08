"""LiteLLM key webhook form."""

from __future__ import annotations

from orion_studio._signing import now_iso
from orion_studio.ui import (
    apply_chrome,
    post_webhook,
    render_sidebar,
    requester_fields,
    show_response,
)

apply_chrome("LiteLLM Key")

LITELLM_MODELS = (
    "allianz-text",
    "allianz-vision",
    "allianz-text-small",
    "allianz-coder",
    "text2test",
)
RESPONSE_WINDOWS = ("realtime", "within_1h", "by_17", "by_next_08")
USAGE_FREQS = ("0_10", "10_100", "100_1000", "1000_10k")
PURPOSES = ("RAG", "CHAT", "AGENT", "DIGERI", "KUBEFLOW")
ENVIRONMENTS = ("DEV", "STG", "PROD")
PAGE_INPUT = (1.0, 3.0, 5.0, 10.0)
PAGE_OUTPUT = (0.5, 1.0, 3.0)


def main() -> None:
    import streamlit as st

    api_base, secret, sign = render_sidebar()
    st.title("LiteLLM API anahtarı")
    st.caption("POST /webhooks/orion — talep_turu=litellm_api_anahtari")

    with st.form("litellm_key_form"):
        head = requester_fields(default_ticket="HD-10001")
        st.subheader("Anahtar")
        c1, c2 = st.columns(2)
        departman = c1.text_input("Departman / team adı", value="GENAI")
        ortam = c2.selectbox("Ortam", ENVIRONMENTS, index=0)
        aciklama = st.text_area("Talep açıklaması", value="LiteLLM API anahtarı talebi.")
        purpose = st.selectbox("Kullanım amacı", PURPOSES, index=0)
        senaryo = st.text_area("Kullanım senaryosu", value="Kurumsal dokümanlardan soru cevaplama.")
        modeller = st.multiselect("Modeller", LITELLM_MODELS, default=[LITELLM_MODELS[0]])
        yanit = st.selectbox("Yanıt süresi", RESPONSE_WINDOWS, index=0)
        siklik = st.selectbox("Kullanım sıklığı", USAGE_FREQS, index=2)
        c3, c4, c5 = st.columns(3)
        gunluk = c3.number_input("Tahmini günlük istek", min_value=0, value=400, step=10)
        es_zamanli = c4.number_input("Anlık paralel istek", min_value=1, value=5, step=1)
        giris = c5.selectbox("Ortalama girdi sayfası", PAGE_INPUT, index=1)
        cikis = st.selectbox("Ortalama çıktı sayfası", PAGE_OUTPUT, index=1)
        submitted = st.form_submit_button("Talebi gönder")

    if not submitted:
        return
    payload: dict[str, object] = {
        "talep_turu": "litellm_api_anahtari",
        "talep_no": head["talep_no"],
        "talep_url": head["talep_url"],
        "talep_eden_adi": head["talep_eden_adi"],
        "talep_eden_eposta": head["talep_eden_eposta"],
        "olusturulma_tarihi": now_iso(),
        "departman_adi": departman,
        "ortam": ortam,
        "talep_aciklamasi": aciklama,
        "kullanim_amaci": purpose,
        "kullanim_senaryosu": senaryo,
        "modeller": modeller,
        "yanit_suresi": yanit,
        "kullanim_sikligi": siklik,
        "maksimum_es_zamanli_istek": int(es_zamanli),
        "ortalama_girdi_sayfasi": float(giris),
        "ortalama_cikti_sayfasi": float(cikis),
    }
    if gunluk > 0:
        payload["tahmini_gunluk_istek"] = int(gunluk)
    show_response(post_webhook(payload, api_base=api_base, secret=secret, sign=sign))


if __name__ in {"__main__", "app"}:
    main()
