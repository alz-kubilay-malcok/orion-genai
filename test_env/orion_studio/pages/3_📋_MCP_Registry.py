"""Form page → POSTs a `talep_turu=mcp_sunucu_kaydi` payload."""

from __future__ import annotations

import re

import httpx
import streamlit as st

from orion_studio import (
    load_backend_env,
    make_signature,
    serialise,
)
from orion_studio._signing import DEFAULT_API_BASE_URL, now_iso  # noqa: E402

st.set_page_config(
    page_title="MCP Sunucu Kayıt Talebi",
    page_icon="📋",
    layout="wide",
)

ENV = load_backend_env()
TALEP_TURU = "mcp_sunucu_kaydi"
ENVIRONMENTS = ("TEST", "PROD")
REPO_PLATFORMS = ("GITHUB", "BITBUCKET")
SLUG_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")
JIRA_RE = re.compile(r"^[A-Z][A-Z0-9]+-[1-9][0-9]*$")


def _sidebar() -> str:
    with st.sidebar:
        st.subheader("Hedef ayarları")
        api_base = st.text_input(
            "API temel URL'si",
            value=st.session_state.get("api_base", DEFAULT_API_BASE_URL),
            key="page3_api",
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
            key="page3_secret",
        )
        st.checkbox("HMAC imzalı gönder", value=True, key="page3_sign")
    return api_base


def _autofill_endpoint(ortam: str, slug: str) -> str:
    if not (ortam and SLUG_RE.match(slug or "")):
        return ""
    host = "test-mcp.allianz-tr.local" if ortam == "TEST" else "mcp.allianz-tr.local"
    return f"https://{host}/{slug}/mcp"


def main() -> None:
    st.title("📋 MCP Sunucu Kayıt Talebi")
    st.caption(
        "Yeni bir MCP sunucusunu registry'ye eklemek için `MCPRegistryPayload` ile POST eder. "
        "Endpoint URL backend tarafından otomatik olarak kanonik hale getirilir."
    )
    api_base = _sidebar()

    with st.form("mcp_registry_form", clear_on_submit=False):
        st.subheader("Talep sahibi")
        cols = st.columns(2)
        talep_no = cols[0].text_input("Talep no (Jira)", value="HD-30001")
        talep_url = cols[1].text_input(
            "Talep URL",
            value=f"https://orion.example.com/browse/{talep_no}",
        )
        cols2 = st.columns(2)
        adi = cols2[0].text_input("Talep eden adı", value="Dev User")
        posta = cols2[1].text_input("Talep eden e-posta", value="dev@example.com")
        st.divider()
        st.subheader("Sunucu meta verisi")
        cols3 = st.columns(2)
        departman = cols3[0].text_input("Departman adı", value="Platform Ekibi")
        # Eski ``mcp_sunucu_adi`` reddedilirdi; doğru alan adı
        # Türkçe→snake mapping'ten sonra ``mcp_server_display_name``'a map olan
        # ``mcp_sunucusu_goruntulu_ad``.
        mcp_sunucusu_goruntulu_ad = cols3[1].text_input(
            "MCP sunucu adı", value="Hasar Asistanı"
        )
        cols4 = st.columns(2)
        proje = cols4[0].text_input(
            "Proje adı (slug)",
            value="hasar-asistani",
            help="Sadece küçük harf, rakam ve tire. backend tarafında kanonik slug ile doğrulanır.",
        )
        teknik = cols4[1].text_input("Teknik sorumlu e-posta", value="oncall@example.com")
        cols5 = st.columns(2)
        repo_platformu = cols5[0].selectbox("Repo platformu", REPO_PLATFORMS, index=0)
        repo_url = cols5[1].text_input(
            "Repo URL",
            value="https://github.com/allianz/hasar-asistani",
        )
        # Eski ``devops_jira_no`` → ``devops_jira_anahtari``.
        jira_anahtari = cols5[1].text_input(
            "DevOps Jira no (opsiyonel)",
            value="DEVOPS-42",
            help="Boş bırakılırsa alan gönderilmez.",
        )
        ortam = cols5[0].selectbox("Ortam", ENVIRONMENTS, index=0)
        autofilled = _autofill_endpoint(ortam, proje)
        mcp_endpoint_url = st.text_input(
            "MCP endpoint URL (kanonik)",
            value=autofilled,
            help="Backend bunu kontrol ediyor: TEST → https://test-mcp.allianz-tr.local/{slug}/mcp, aksi halde https://mcp.allianz-tr.local/{slug}/mcp",
        )
        kullanim_amaci = st.text_area("Kullanım amacı", value="Hasar ihbarlarını özetlemek için MCP")
        min_eval_required = (ortam == "PROD")
        min_eval = st.number_input(
            "Minimum değerlendirme skoru (0–100)",
            min_value=0, max_value=100, value=90 if min_eval_required else 0, step=1,
            help="PROD için ≥ 90 zorunlu; backend `MCP_PROD_MIN_TOOL_EVALUATION_SCORE` (varsayılan 90).",
        )
        ek_notlar = st.text_area("Ek notlar (opsiyonel)", value="")

        cols6 = st.columns(2)
        submitted = cols6[0].form_submit_button("Talebi gönder")

    if submitted:
        errs: list[str] = []
        if not SLUG_RE.match(proje or ""):
            errs.append("Proje adı `^[a-z0-9]+(?:-[a-z0-9]+)*$` desenine uymuyor")
        # ``devops_jira_anahtari`` regex'i (eski ``devops_jira_no`` da aynıydı).
        if jira_anahtari and not JIRA_RE.match(jira_anahtari):
            errs.append("DevOps Jira no `^[A-Z][A-Z0-9]+-[1-9][0-9]*$` desenine uymuyor")
        canonical = _autofill_endpoint(ortam, proje)
        if canonical and mcp_endpoint_url.rstrip("/") != canonical.rstrip("/"):
            errs.append(f"Endpoint URL kanonik olmalı: {canonical}")
        if ortam == "PROD" and (min_eval or 0) < 90:
            errs.append("PROD için minimum_degerlendirme_skoru ≥ 90 olmalı")
        if errs:
            for msg in errs:
                st.error(msg)
            return

        # NOT: ``extra='forbid'`` reddeden alanlar:
        # - ``ortam``: SharedFields'ta yok.
        # - ``mcp_sunucu_adi``: doğrusu ``mcp_sunucusu_goruntulu_ad``.
        # - ``minimum_evaluation_skoru``: doğrusu ``minimum_degerlendirme_skoru``.
        # - ``devops_jira_no``: doğrusu ``devops_jira_anahtari``.
        payload: dict[str, object] = {
            "talep_turu": TALEP_TURU,
            "talep_no": talep_no,
            "talep_url": talep_url,
            "talep_eden_adi": adi,
            "talep_eden_eposta": posta,
            "olusturulma_tarihi": now_iso(),
            "departman_adi": departman,
            "mcp_sunucusu_goruntulu_ad": mcp_sunucusu_goruntulu_ad,
            "proje_adi": proje,
            "teknik_sorumlu_eposta": teknik,
            "kullanim_amaci": kullanim_amaci,
            "repo_platformu": repo_platformu,
            "repo_url": repo_url,
            "mcp_endpoint_url": mcp_endpoint_url,
            "minimum_degerlendirme_skoru": int(min_eval) if min_eval else None,
            "ek_notlar": ek_notlar or None,
        }
        if jira_anahtari:
            payload["devops_jira_anahtari"] = jira_anahtari
        if not payload.get("minimum_degerlendirme_skoru"):
            payload.pop("minimum_degerlendirme_skoru", None)

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


if __name__ in {"__main__", "app"}:
    main()
