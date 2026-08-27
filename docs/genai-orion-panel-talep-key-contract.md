# GenAiOrionPanel Talep Formları — Field Contract

## 1. LiteLLM API Anahtarı

| Field key | Form etiketi | Tür | Zorunlu | Seçenek / validasyon |
| --- | --- | --- | --- | --- |
| `departman_adi` | Departman adı | Metin | Evet | Serbest metin |
| `ortam` | Ortam | Tekli seçim | Evet | `DEV`, `STG`, `PROD` |
| `talep_aciklamasi` | Talep açıklaması | Uzun metin | Evet | Serbest metin |
| `kullanim_amaci` | Kullanım amacı | Tekli seçim | Evet | `RAG`, `CHAT`, `AGENT`, `DIGERI` |
| `kullanim_senaryosu` | Kullanım senaryosu | Uzun metin | Evet | Serbest metin |
| `modeller` | Talep edilen model | Çoklu seçim | Evet | `allianz-text`, `allianz-vision`, `allianz-text-small`, `allianz-coder`, `text2test` |
| `yanit_suresi` | Beklenen yanıt süresi | Tekli seçim | Evet | `realtime`, `within_1h`, `by_17`, `by_next_08` |
| `kullanim_sikligi` | Tahmini kullanım sıklığı | Tekli seçim | Evet | `0_10`, `10_100`, `100_1000`, `1000_10k` |
| `tahmini_gunluk_istek` | Tahmini günlük istek sayısı | Sayı | Hayır | Pozitif tam sayı |
| `maksimum_es_zamanli_istek` | En fazla eş zamanlı istek sayısı | Sayı | Evet | En az `1` |
| `ortalama_girdi_sayfasi` | Ortalama girdi uzunluğu | Tekli seçim | Evet | `1`, `3`, `5`, `10` |
| `ortalama_cikti_sayfasi` | Ortalama çıktı uzunluğu | Tekli seçim | Evet | `0.5`, `1`, `3` |

### Model etiketleri

| Değer | Etiket |
| --- | --- |
| `allianz-text` | Allianz Lingua |
| `allianz-vision` | Allianz Optix |
| `allianz-text-small` | Allianz Text Small |
| `allianz-coder` | Allianz Codia |
| `text2test` | Text2Test |

### Yanıt süresi etiketleri

| Değer | Etiket |
| --- | --- |
| `realtime` | Gerçek zamanlı |
| `within_1h` | 1 saat içinde |
| `by_17` | Aynı gün saat 17.00'ye kadar |
| `by_next_08` | Ertesi gün saat 08.00'e kadar |

### Kullanım sıklığı etiketleri

| Değer | Etiket |
| --- | --- |
| `0_10` | Günde 0–10 istek |
| `10_100` | Günde 10–100 istek |
| `100_1000` | Günde 100–1.000 istek |
| `1000_10k` | Günde 1.000–10.000 istek |

### Gönderilecek JSON

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

## 2. MCP Erişim Anahtarı

| Field key | Form etiketi | Tür | Zorunlu | Seçenek / validasyon |
| --- | --- | --- | --- | --- |
| `departman_adi` | Departman adı | Metin | Evet | Serbest metin |
| `ortam` | Erişim talep edilen ortam | Tekli seçim | Evet | `TEST`, `STG`, `PROD` |
| `talep_aciklamasi` | Talep açıklaması | Uzun metin | Evet | Serbest metin |
| `kullanim_amaci` | Kullanım senaryosu | Uzun metin | Evet | Serbest metin |
| `mcp_sunucusu` | MCP sunucusu | Tekli veya çoklu seçim | Evet | Aktif katalog `server_name`. String veya string dizisi. |
| `araclar` | Erişim talep edilen araçlar | Çoklu seçim | Koşullu | Tek sunucu: dizi. Çoklu sunucu: `{ "server_name": ["tool", ...] }`. |
| `tum_araclara_erisim` | Tüm araçlara erişim | Onay kutusu | Hayır | Varsayılan `false`. Çoklu sunucuda bool (hepsi) veya `{ "server_name": true }`. |
| `erisimler` | Sunucu başına kapsam | Dizi | Hayır | Varsa `mcp_sunucusu`/`araclar` gönderme. Öğeler: `mcp_sunucusu`, `araclar`, `tum_araclara_erisim`. |

- `tum_araclara_erisim=false` ise o sunucu için en az bir `araclar` seçimi zorunludur.
- `tum_araclara_erisim` yalnızca ilgili MCP sunucusu izin veriyorsa gösterilir.
- Birden fazla sunucu tek talepte desteklenir; araçlar sunucuya göre eşlenmelidir.

### MCP katalog endpoint yanıtı

`mcp_sunucusu` ve `araclar` seçenekleri Orion ekibine sağlanacak endpoint'ten alınacaktır.

```json
{
  "servers": [
    {
      "server_name": "xx",
      "tools": ["rag", "search"]
    }
  ]
}
```

### Gönderilecek JSON

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
  "mcp_sunucusu": "document-search-prod",
  "araclar": ["rag", "search"],
  "tum_araclara_erisim": false
}
```

Çoklu sunucu:

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
  "mcp_sunucusu": ["document-search-prod", "jira-mcp"],
  "araclar": {
    "document-search-prod": ["rag", "search"],
    "jira-mcp": ["create_issue"]
  },
  "tum_araclara_erisim": false
}
```

## 3. MCP Sunucu Kayıt Talebi

| Field key | Form etiketi | Tür | Zorunlu | Seçenek / validasyon |
| --- | --- | --- | --- | --- |
| `departman_adi` | Departman adı | Metin | Evet | Serbest metin |
| `mcp_sunucu_adi` | MCP sunucu adı | Metin | Evet | Serbest metin |
| `proje_adi` | Proje adı | Metin | Evet | Küçük harf, rakam ve tire |
| `teknik_sorumlu_eposta` | Teknik sorumlu e-posta adresi | Metin | Evet | Geçerli e-posta adresi |
| `kullanim_amaci` | Kullanım senaryosu | Uzun metin | Evet | Serbest metin |
| `repo_platformu` | Repository platformu | Tekli seçim | Evet | `GITHUB`, `BITBUCKET` |
| `repo_url` | Repository bağlantısı | Metin | Evet | Geçerli HTTPS URL |
| `devops_jira_no` | DevOps Jira task numarası | Metin | Hayır | `ATL` task numarası |
| `ortam` | Kayıt edilecek ortam | Tekli seçim | Evet | `TEST`, `PROD` |
| `mcp_endpoint_url` | MCP endpoint URL'si | Metin | Evet | HTTPS ve `/mcp` ile bitmeli |
| `minimum_evaluation_skoru` | En düşük tool evaluation skoru | Sayı | Koşullu | `PROD` için en az `90` |
| `ek_notlar` | Ek açıklamalar | Uzun metin | Hayır | Serbest metin |

- `TEST`: `https://test-mcp.allianz-tr.local/<proje_adi>/mcp`
- `PROD`: `https://mcp.allianz-tr.local/<proje_adi>/mcp`
- Yalnızca Streamable HTTP desteklenir.

### Gönderilecek JSON

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
