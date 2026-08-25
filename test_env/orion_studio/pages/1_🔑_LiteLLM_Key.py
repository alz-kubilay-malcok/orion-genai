"""Form page → POSTs a `talep_turu=litellm_api_anahtari` payload."""

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
    page_title="LiteLLM Anahtar Talebi",
    page_icon="🔑",
    layout="wide",
)

ENV = load_backend_env()

LITELLM_MODELS = (
    "allianz-text",
    "allianz-vision",
    "allianz-text-small",
    "allianz-coder",
    "text2test",
)
RESPONSE_WINDOWS = ("realtime", "within_1h", "by_17", "by_next_08")
USAGE_FREQS = ("0_10", "10_100", "100_1000", "1000_10k")
PURPOSES = ("RAG", "CHAT", "AGENT", "DIGERI")
ENVIRONMENTS = ("DEV", "STG", "PROD")
PAGE_INPUT_ALLOWED = (1.0, 3.0, 5.0, 10.0)
PAGE_OUTPUT_ALLOWED = (0.5, 1.0, 3.0)

TALEP_TURU = "litellm_api_anahtari"


def _render_header() -> tuple[str, str, str]:
    with st.sidebar:
        st.subheader("Hedef ayarları")
        api_base = st.text_input(
            "API temel URL'si",
            value=st.session_state.get("api_base", DEFAULT_API_BASE_URL),
            key="api_base",
        )
        secret = st.session_state.get(
            "orion_secret",
            ENV.get("GENAI_ORION_PANEL_WEBHOOK_SECRET", "dev-orion-secret"),
        )
        st.session_state["orion_secret"] = st.text_input(
            "Webhook gizli anahtarı",
            value=secret,
            type="password",
            key="page1_secret",
        )
        sign = st.checkbox("HMAC imzalı gönder", value=True, key="page1_sign")
    return api_base, st.session_state["orion_secret"], "true" if sign else "false"


def _render_top(talep_no: str) -> dict[str, str]:
    st.subheader("Talep sahibi")
    cols = st.columns(2)
    talep_no_val = cols[0].text_input("Talep no (Jira)", value=talep_no)
    talep_url = cols[1].text_input(
        "Talep URL",
        value=f"https://orion.example.com/browse/{talep_no_val}",
    )
    cols2 = st.columns(2)
    adi = cols2[0].text_input("Talep eden adı", value="Dev User")
    posta = cols2[1].text_input("Talep eden e-posta", value="dev@example.com")
    return {
        "talep_no": talep_no_val,
        "talep_url": talep_url,
        "talep_eden_adi": adi,
        "talep_eden_eposta": posta,
    }


def main() -> None:
    st.title("🔑 LiteLLM Anahtar Talebi")
    st.caption(
        "Backend `talep_turu=litellm_api_anahtari` için `LiteLLMKeyPayload` bekliyor. Bu sayfa imzalanmış bir JSON gönderiyor."
    )
    api_base, _secret, _sign_flag = _render_header()

    with st.form("litellm_key_form", clear_on_submit=False):
        head = _render_top("HD-10001")
        st.divider()
        st.subheader("Anahtar detayları")
        cols = st.columns(2)
        departman = cols[0].text_input("Departman adı", value="Rıza Operasyon")
        ortam = cols[1].selectbox("Ortam", ENVIRONMENTS, index=0)
        aciklama = st.text_area("Talep açıklaması", value="RAG demo için kısa süreli anahtar.")
        used_purpose = st.selectbox("Kullanım amacı (kod)", PURPOSES, index=1)
        senaryo = st.text_area(
            "Kullanım senaryosu",
            value="Dahili bilgi bankası dökümanlarından yanıt üretimi.",
        )
        modeller = st.multiselect("Modeller", LITELLM_MODELS, default=LITELLM_MODELS[:1])
        yanit = st.selectbox("Yanıt süresi", RESPONSE_WINDOWS, index=0)
        siklik = st.selectbox("Kullanım sıklığı", USAGE_FREQS, index=1)
        cols2 = st.columns(3)
        gunluk = cols2[0].number_input(
            "Tahmini günlük istek (>0)", min_value=0, value=0, step=10,
            help="0 bırakılırsa alan gönderilmez.",
        )
        es_zamanli = cols2[1].number_input(
            "Maksimum eş zamanlı istek (≥1)",
            min_value=1, value=2, step=1,
        )
        giris = cols2[2].selectbox("Ortalama girdi sayfası", PAGE_INPUT_ALLOWED, index=0)
        cikis = st.selectbox("Ortalama çıktı sayfası", PAGE_OUTPUT_ALLOWED, index=0)

        cols3 = st.columns(2)
        submitted = cols3[0].form_submit_button("Talebi gönder")
        filled = gunluk > 0
        sent = False

    if submitted:
        # Backend ``LitellmKeyPayload`` ``extra='forbid'`` olduğu için:
        # - 'ortam' shared alanlarda yok; Pydantic bunu reddeder.
        # - 'talep_aciklamasi' ASCII 'i' ile yazılmalı (Türkçe ı olmaz).
        payload: dict[str, object] = {
            "talep_turu": TALEP_TURU,
            "talep_no": head["talep_no"],
            "talep_url": head["talep_url"],
            "talep_eden_adi": head["talep_eden_adi"],
            "talep_eden_eposta": head["talep_eden_eposta"],
            "olusturulma_tarihi": now_iso(),
            "departman_adi": departman,
            "talep_aciklamasi": aciklama,
            "kullanim_amaci": used_purpose,
            "kullanim_senaryosu": senaryo,
            "modeller": modeller,
            "yanit_suresi": yanit,
            "kullanim_sikligi": siklik,
            "tahmini_gunluk_istek": int(gunluk) if filled else None,
            "maksimum_es_zamanli_istek": int(es_zamanli),
            "ortalama_girdi_sayfasi": float(giris),
            "ortalama_cikti_sayfasi": float(cikis),
        }
        if not filled:
            payload.pop("tahmini_gunluk_istek", None)
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
        sent = True
        st.session_state["last_response_status"] = response.status_code
        st.session_state["last_response_body"] = response.text[:600]

    if st.session_state.get("last_response_status") is not None:
        status = st.session_state["last_response_status"]
        body = st.session_state["last_response_body"]
        if status == 202:
            st.success(f"HTTP 202 — {body}")
        else:
            st.error(f"HTTP {status} — {body}")

    with st.expander("Gönderilen JSON (imzasız)"):
        st.code(
            serialise(
                {
                    "talep_turu": TALEP_TURU,
                    "talep_no": head["talep_no"] if submitted else "HD-10001",
                    "departman_adi": departman,
                    "ortam": ortam,
                    "modeller": modeller,
                    "maksimum_es_zamanli_istek": int(es_zamanli),
                    "ortalama_girdi_sayfasi": float(giris),
                    "ortalama_cikti_sayfasi": float(cikis),
                }
            ).decode("utf-8"),
            language="json",
        )


if __name__ in {"__main__", "app"}:  # when run standalone
    main()
