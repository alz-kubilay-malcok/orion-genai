# Orion API

Base: `http://<host>:<PANEL_PORT>` (nginx; varsayılan `8056`). Dışarı yalnız bu port.

İki endpoint. Login gerekmez. Path'ler `/api` prefix (nginx strip → FastAPI).

Webhook imzası: ham JSON body üzerinden HMAC-SHA256, header `X-GenAi-Orion-Panel-Signature` (hex). Extra JSON alanı 422.

---

## Katalog

`GET /api/catalog/mcp-servers?ortam=TEST`  
`GET /api/catalog/mcp-servers?ortam=PROD`

`mcp_sunucusu` = `server_name`, `araclar` = `tools`.

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

Her talepte:

| Alan | |
| --- | --- |
| `talep_turu` | `litellm_api_anahtari` / `mcp_erisim_anahtari` / `mcp_sunucu_kaydi` |
| `talep_no` | ticket; aynı no + tip tekrar → duplicate |
| `talep_url` | HTTPS |
| `talep_eden_adi` | |
| `talep_eden_eposta` | |
| `olusturulma_tarihi` | ISO-8601 |

### LiteLLM anahtarı — `litellm_api_anahtari`

`ortam`: `DEV` | `STG` | `PROD`  
`kullanim_amaci`: `RAG` | `CHAT` | `AGENT` | `DIGERI`  
`modeller`: `allianz-text`, `allianz-vision`, `allianz-text-small`, `allianz-coder`, `text2test`  
`yanit_suresi`: `realtime` | `within_1h` | `by_17` | `by_next_08`  
`kullanim_sikligi`: `0_10` | `10_100` | `100_1000` | `1000_10k`

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

### MCP anahtarı — `mcp_erisim_anahtari`

`ortam`: `TEST` | `PROD`  
`mcp_sunucusu` / `araclar` katalogdan. `tum_araclara_erisim=false` ise en az bir araç.

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

### MCP sunucu kaydı — `mcp_sunucu_kaydi`

`ortam`: `TEST` | `PROD`  
`repo_platformu`: `GITHUB` | `BITBUCKET`  
`mcp_endpoint_url` HTTPS ve `/mcp` ile bitsin.  
TEST: `https://test-mcp.allianz-tr.local/<proje_adi>/mcp`  
PROD: `https://mcp.allianz-tr.local/<proje_adi>/mcp`

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

Aynı `talep_no` + tip — **202**

```json
{
  "request_id": "7beb17df-ada7-4daa-9243-3500f7810a7c",
  "status": "waiting_approval",
  "duplicate": true
}
```

| Kod | Body |
| --- | --- |
| 401 | `{ "error_code": "INVALID_WEBHOOK_SIGNATURE" }` |
| 422 | `{ "error_code": "BAD_JSON" }` / `UNKNOWN_REQUEST_TYPE` / `VALIDATION_ERROR` |
