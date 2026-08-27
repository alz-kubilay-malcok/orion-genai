# Orion ↔ GenAi Orion Panel — webhook contract

Base (prod): `https://genai-management.allianz-tr.local`  
Login yok. Path'ler `/api` prefix (nginx strip → FastAPI).

Bilinmeyen JSON alanı → **422**. İmza, gönderilen ham body byte'ları üzerinden hesaplanır (pretty-print yok).

---

## Auth

`POST` gövdesi: UTF-8 JSON.  
HMAC-SHA256(secret, raw_body) → lowercase hex.  
Header: `X-GenAi-Orion-Panel-Signature`

`GET` katalog imza istemez.

---

## Katalog

`GET /api/catalog/mcp-servers?ortam=TEST`  
`GET /api/catalog/mcp-servers?ortam=PROD`

Form selectbox: `mcp_sunucusu` = `server_name`, `araclar` = o satırın `tools`.

```json
{
  "ortam": "PROD",
  "servers": [
    { "server_name": "document-search", "tools": ["rag", "search"] }
  ]
}
```

---

## Talep

`POST /api/webhooks/orion`  
`Content-Type: application/json`

### Ortak alanlar (her `talep_turu`)

| Alan | Zorunlu | Kural |
| --- | --- | --- |
| `talep_turu` | evet | `litellm_api_anahtari` \| `mcp_erisim_anahtari` \| `mcp_sunucu_kaydi` |
| `talep_no` | evet | ticket; aynı no + aynı tip tekrar → 202 `duplicate: true` |
| `talep_url` | evet | HTTPS URL |
| `talep_eden_adi` | evet | |
| `talep_eden_eposta` | evet | e-posta |
| `olusturulma_tarihi` | evet | ISO-8601 (offset'li) |

---

### 1. LiteLLM anahtarı — `litellm_api_anahtari`

| Alan | Zorunlu | Değer |
| --- | --- | --- |
| `departman_adi` | evet | metin |
| `ortam` | evet | `DEV` \| `STG` \| `PROD` |
| `talep_aciklamasi` | evet | |
| `kullanim_amaci` | evet | `RAG` \| `CHAT` \| `AGENT` \| `DIGERI` |
| `kullanim_senaryosu` | evet | |
| `modeller` | evet | `allianz-text` \| `allianz-vision` \| `allianz-text-small` \| `allianz-coder` \| `text2test` (dizi, ≥1) |
| `yanit_suresi` | evet | `realtime` \| `within_1h` \| `by_17` \| `by_next_08` |
| `kullanim_sikligi` | evet | `0_10` \| `10_100` \| `100_1000` \| `1000_10k` |
| `tahmini_gunluk_istek` | hayır | pozitif tam sayı |
| `maksimum_es_zamanli_istek` | evet | ≥ 1 |
| `ortalama_girdi_sayfasi` | evet | `1` \| `3` \| `5` \| `10` |
| `ortalama_cikti_sayfasi` | evet | `0.5` \| `1` \| `3` |

```json
{
  "talep_turu": "litellm_api_anahtari",
  "talep_no": "HD-12345",
  "talep_url": "https://atlassian.allianz/HD-12345",
  "talep_eden_adi": "Kubilay",
  "talep_eden_eposta": "user@allianz.com.tr",
  "olusturulma_tarihi": "2026-08-17T11:00:00+03:00",
  "departman_adi": "GENAI",
  "ortam": "PROD",
  "talep_aciklamasi": "LiteLLM API anahtarı talebi.",
  "kullanim_amaci": "RAG",
  "kullanim_senaryosu": "Kurumsal dokümanlardan soru cevaplama.",
  "modeller": ["allianz-text"],
  "yanit_suresi": "realtime",
  "kullanim_sikligi": "100_1000",
  "tahmini_gunluk_istek": 400,
  "maksimum_es_zamanli_istek": 5,
  "ortalama_girdi_sayfasi": 3,
  "ortalama_cikti_sayfasi": 1
}
```

---

### 2. MCP anahtarı — `mcp_erisim_anahtari`

`ortam`: `TEST` \| `PROD`  
Sunucu/araç adları katalogdan. **Tek talepte birden fazla sunucu** desteklenir.

| Alan | Zorunlu | Değer |
| --- | --- | --- |
| `departman_adi` | evet | |
| `ortam` | evet | `TEST` \| `PROD` |
| `talep_aciklamasi` | evet | |
| `kullanim_amaci` | evet | serbest metin (senaryo) |
| `mcp_sunucusu` | `erisimler` yoksa evet | string **veya** string dizisi |
| `araclar` | koşullu | tek sunucu: string dizisi. çoklu: `{ "server_name": ["tool", ...] }` |
| `tum_araclara_erisim` | hayır | `false` varsayılan. bool (tüm seçili sunucular) veya `{ "server_name": true }` |
| `erisimler` | hayır | sunucu başına kapsam; **varsa** `mcp_sunucusu` / `araclar` gönderme |

Kurallar:

- `tum_araclara_erisim=false` ise o sunucu için ≥1 araç.
- `tum_araclara_erisim=true` ise o sunucunun `araclar` listesi boş.
- Çoklu sunucuda düz `araclar: ["rag"]` **422** — araçlar sunucuya map edilmeli.
- Aynı `mcp_sunucusu` iki kez **422**.

Tek sunucu:

```json
{
  "talep_turu": "mcp_erisim_anahtari",
  "talep_no": "HD-12346",
  "talep_url": "https://atlassian.allianz/HD-12346",
  "talep_eden_adi": "Kubilay",
  "talep_eden_eposta": "user@allianz.com.tr",
  "olusturulma_tarihi": "2026-08-17T11:05:00+03:00",
  "departman_adi": "GENAI",
  "ortam": "PROD",
  "talep_aciklamasi": "Ajan uygulaması için MCP erişimi.",
  "kullanim_amaci": "Kurumsal dokümanlarda arama.",
  "mcp_sunucusu": "document-search",
  "araclar": ["rag", "search"],
  "tum_araclara_erisim": false
}
```

Çoklu sunucu (önerilen form çıktısı):

```json
{
  "talep_turu": "mcp_erisim_anahtari",
  "talep_no": "HD-12346",
  "talep_url": "https://atlassian.allianz/HD-12346",
  "talep_eden_adi": "Kubilay",
  "talep_eden_eposta": "user@allianz.com.tr",
  "olusturulma_tarihi": "2026-08-17T11:05:00+03:00",
  "departman_adi": "GENAI",
  "ortam": "PROD",
  "talep_aciklamasi": "Ajan uygulaması için MCP erişimi.",
  "kullanim_amaci": "Doküman arama ve Jira.",
  "mcp_sunucusu": ["document-search", "jira-mcp"],
  "araclar": {
    "document-search": ["rag", "search"],
    "jira-mcp": ["create_issue"]
  },
  "tum_araclara_erisim": false
}
```

Karışık kapsam (bir sunucuda tüm araçlar):

```json
{
  "talep_turu": "mcp_erisim_anahtari",
  "talep_no": "HD-12348",
  "talep_url": "https://atlassian.allianz/HD-12348",
  "talep_eden_adi": "Kubilay",
  "talep_eden_eposta": "user@allianz.com.tr",
  "olusturulma_tarihi": "2026-08-17T11:15:00+03:00",
  "departman_adi": "GENAI",
  "ortam": "PROD",
  "talep_aciklamasi": "Karışık MCP kapsamı.",
  "kullanim_amaci": "Arama + Jira tüm araçlar.",
  "erisimler": [
    {
      "mcp_sunucusu": "document-search",
      "araclar": ["rag"],
      "tum_araclara_erisim": false
    },
    {
      "mcp_sunucusu": "jira-mcp",
      "araclar": [],
      "tum_araclara_erisim": true
    }
  ]
}
```

---

### 3. MCP sunucu kaydı — `mcp_sunucu_kaydi`

| Alan | Zorunlu | Değer |
| --- | --- | --- |
| `departman_adi` | evet | |
| `mcp_sunucu_adi` | evet | görünen ad |
| `proje_adi` | evet | küçük harf, rakam, tire |
| `teknik_sorumlu_eposta` | evet | e-posta |
| `kullanim_amaci` | evet | |
| `repo_platformu` | evet | `GITHUB` \| `BITBUCKET` |
| `repo_url` | evet | HTTPS |
| `devops_jira_no` | hayır | ATL task |
| `ortam` | evet | `TEST` \| `PROD` |
| `mcp_endpoint_url` | evet | HTTPS, `/mcp` ile bitsin |
| `minimum_evaluation_skoru` | PROD evet | PROD ≥ 90 |
| `ek_notlar` | hayır | |

TEST: `https://test-mcp.allianz-tr.local/<proje_adi>/mcp`  
PROD: `https://mcp.allianz-tr.local/<proje_adi>/mcp`  
Yalnız Streamable HTTP.

```json
{
  "talep_turu": "mcp_sunucu_kaydi",
  "talep_no": "HD-12347",
  "talep_url": "https://atlassian.allianz/HD-12347",
  "talep_eden_adi": "Kubilay",
  "talep_eden_eposta": "user@allianz.com.tr",
  "olusturulma_tarihi": "2026-08-17T11:10:00+03:00",
  "departman_adi": "GENAI",
  "mcp_sunucu_adi": "Doküman Arama MCP",
  "proje_adi": "document-search",
  "teknik_sorumlu_eposta": "mcp-owner@allianz.com.tr",
  "kullanim_amaci": "Ajanların kurumsal dokümanlarda arama yapmasını sağlar.",
  "repo_platformu": "BITBUCKET",
  "repo_url": "https://sdlc.allianz.com.tr/stash/projects/ALLMCP/repos/document-search",
  "devops_jira_no": "ATL-12345",
  "ortam": "PROD",
  "mcp_endpoint_url": "https://mcp.allianz-tr.local/document-search/mcp",
  "minimum_evaluation_skoru": 94,
  "ek_notlar": "Release branch üzerinden Prod deployment tamamlandı."
}
```

---

## Yanıtlar

Yeni talep — **202**

```json
{
  "request_id": "7beb17df-ada7-4daa-9243-3500f7810a7c",
  "status": "waiting_approval",
  "approver_mails_enqueued": 2
}
```

Aynı `talep_no` + `talep_turu` — **202**

```json
{
  "request_id": "7beb17df-ada7-4daa-9243-3500f7810a7c",
  "status": "waiting_approval",
  "duplicate": true
}
```

| HTTP | Body |
| --- | --- |
| 401 | `{ "error_code": "INVALID_WEBHOOK_SIGNATURE" }` |
| 422 | `{ "error_code": "BAD_JSON" }` / `UNKNOWN_REQUEST_TYPE` / `VALIDATION_ERROR` (`field_errors` olabilir) |
