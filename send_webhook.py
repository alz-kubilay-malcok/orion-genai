"""Orion webhook deneme scripti: `POST /webhooks/orion` çağırır.

Kullanım:
    python send_webhook.py

Değerleri aşağıdaki bölümden değiştir. Sadece standart kütüphane kullanır.
HMAC imzası, gövdenin ham byte'ları üzerinden hesaplanır
(`X-GenAi-Orion-Panel-Signature`, SHA-256 hex).
"""

from __future__ import annotations

import hashlib
import hmac
import json
import urllib.error
import urllib.request
import uuid
from datetime import UTC, datetime

# ---------------------------------------------------------------- AYARLAR --
WEBHOOK_URL = ""  # örn. "http://localhost:8056/webhooks/orion"
WEBHOOK_SECRET = ""  # GENAI_ORION_PANEL_WEBHOOK_SECRET; boşsa imza gönderilmez

# Boş bırakırsan her çalıştırmada yeni bir ITSM-xxxxxxxx üretilir.
# Aynı talep_no ile tekrar göndermek "duplicate" yanıtı döndürür.
TALEP_NO = ""

TALEP_TURU = "litellm_api_anahtari"  # litellm_api_anahtari | mcp_erisim_anahtari | mcp_sunucu_kaydi
TALEP_EDEN_ADI = ""
TALEP_EDEN_EPOSTA = ""

DEPARTMAN_ADI = "[Veri Bilimi]"
ORTAM = "BIREYSEL"  # DEV | STG | PROD | BIREYSEL
PROJE_ADI = "genai-management"
KULLANIM_AMACI = "IDP"  # CODER | IDP | CHATBOT | AGENTIC | KUBEFLOW | OTHER
MODELLER = ["allianz-vision"]
TALEP_ACIKLAMASI = "test"
KULLANIM_SENARYOSU = "test"
YANIT_SURESI = "realtime"
KULLANIM_SIKLIGI = "0_10"
TAHMINI_GUNLUK_ISTEK = 1
MAKSIMUM_ES_ZAMANLI_ISTEK = 1
ORTALAMA_GIRDI_SAYFASI = 1
ORTALAMA_CIKTI_SAYFASI = 1

TIMEOUT_SECONDS = 15
# ---------------------------------------------------------------------------


def build_payload() -> dict:
    talep_no = TALEP_NO or f"ITSM-{uuid.uuid4().hex[:8]}"
    return {
        "talep_turu": TALEP_TURU,
        "talep_no": talep_no,
        "talep_url": f"https://example.com/jira/browse/{talep_no}",
        "talep_eden_adi": TALEP_EDEN_ADI,
        "talep_eden_eposta": TALEP_EDEN_EPOSTA,
        "olusturulma_tarihi": datetime.now(UTC).isoformat(),
        "departman_adi": DEPARTMAN_ADI,
        "ortam": ORTAM,
        "talep_aciklamasi": TALEP_ACIKLAMASI,
        "proje_adi": PROJE_ADI,
        "kullanim_amaci": KULLANIM_AMACI,
        "kullanim_senaryosu": KULLANIM_SENARYOSU,
        "modeller": MODELLER,
        "yanit_suresi": YANIT_SURESI,
        "kullanim_sikligi": KULLANIM_SIKLIGI,
        "maksimum_es_zamanli_istek": MAKSIMUM_ES_ZAMANLI_ISTEK,
        "ortalama_girdi_sayfasi": ORTALAMA_GIRDI_SAYFASI,
        "ortalama_cikti_sayfasi": ORTALAMA_CIKTI_SAYFASI,
        "tahmini_gunluk_istek": TAHMINI_GUNLUK_ISTEK,
    }


def main() -> int:
    if not WEBHOOK_URL:
        print("WEBHOOK_URL boş; script'in üstündeki ayarları doldur.")
        return 2

    body = json.dumps(build_payload(), ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"}
    if WEBHOOK_SECRET:
        headers["X-GenAi-Orion-Panel-Signature"] = hmac.new(
            WEBHOOK_SECRET.encode("utf-8"), body, hashlib.sha256,
        ).hexdigest()

    print(f"POST {WEBHOOK_URL}")
    print(body.decode("utf-8"))

    req = urllib.request.Request(WEBHOOK_URL, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT_SECONDS) as resp:
            status, text = resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as exc:
        status, text = exc.code, exc.read().decode("utf-8", "replace")
    except urllib.error.URLError as exc:
        print(f"Bağlantı hatası: {exc.reason}")
        return 1

    print(f"\n-> HTTP {status}\n{text}")
    return 0 if status == 202 else 1


if __name__ == "__main__":
    raise SystemExit(main())
