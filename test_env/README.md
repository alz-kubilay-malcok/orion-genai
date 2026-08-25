# test_env — Orion panel + mock LiteLLM test suite

Bu klasör, `apps/api` + `apps/worker` için **manuel bir test ortamı** sunar:
- `mock_litellm/` — `LITELLM_ACCESS_KEY=asd123` ile korunan FastAPI sahtecisi.
- `orion_studio/` — `streamlit` ile çalışan form paneli; üç sayfa backend'in beklediği JSON'u imzalı şekilde webhook'a gönderir.

> **Sadece test ortamı.** Üretime alınmaz. Tüm servisler `127.0.0.1` üzerindedir.

## Port haritası

| Servis                   | Adres                |
|--------------------------|----------------------|
| Backend API (FastAPI)    | `http://127.0.0.1:8001` |
| Backend worker (CLI)     | arkaplanda           |
| Mock LiteLLM (FastAPI)   | `http://127.0.0.1:8200` |
| Streamlit orion_studio   | `http://127.0.0.1:8501` |

## Akış (happy path)

```powershell
# 0. ortam değişkenleri
$env:NO_PROXY              = "localhost,127.0.0.1"
$env:LITELLM_ACCESS_KEY    = "asd123"
$env:GENAI_ORION_PANEL_WEBHOOK_SECRET = "dev-orion-secret"

# 1. mock + backend + worker + panel
pwsh -File test_env/scripts/run_api.ps1       # 8001
pwsh -File test_env/scripts/run_worker.ps1    # arkaplan
pwsh -File test_env/scripts/run_panel.ps1     # 8501

# 2. smoke test: üç talebi imzalı olarak POST'la
# backend venv altındaki interpreter'ı kullandığından emin ol.
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py
```

Alternatif olarak yalnız tek tür göndermek için:

```powershell
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py litellm
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py mcp_key
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py mcp_registry
```

Paneldeki formlar backend'in `received` alanları ile eşleşir; DB'yi `pages/4_🗄_DB_Inspect.py` üzerinden izleyebilirsin.

## Webhook sözleşmesi

- Yol: `POST /webhooks/orion`
- İmza: HMAC-SHA256(raw_body), header `x-genai-orion-panel-signature`.
- Secret: `GENAI_ORION_PANEL_WEBHOOK_SECRET`.
- Backend kabul cevabı: `202` + `{request_id, status}`.

> Backend middleware `PROTECTED_PATHS` hem canonical `/webhooks/orion` (router mount) hem de legacy alias `/webhooks/genai-orion-panel` üzerinde HMAC doğrular; bypass yok.

## Talep şablonları (form alanları)

| `talep_turu`            | Form sayfası           |
|-------------------------|------------------------|
| `litellm_api_anahtari`  | `pages/1_🔑_LiteLLM_Key.py` |
| `mcp_erisim_anahtari`   | `pages/2_🔧_MCP_Key.py`     |
| `mcp_sunucu_kaydi`      | `pages/3_📋_MCP_Registry.py` |

## Mock LiteLLM

- Bearer anahtarı: `$LITELLM_ACCESS_KEY` (varsayılan `asd123`).
- Auth bypass: `$env:MOCK_LITELLM_AUTH_OFF = "1"`.
- Hata injections:
  - `POST /__mock/failures {"endpoint": "key/generate", "status": 500, "repeat": 3}`.
  - Loglar: `GET /__mock/log`, son hal: `GET /__mock/state`.

## DB yolu

- `DATABASE_URL=sqlite+aiosqlite:///../db/orion.db` backend kökten çalıştırıldığında `C:\projects\GenAiOrionPanel\db\orion.db` anlamına gelir.
- Sayfa `pages/4_🗄_DB_Inspect.py` salt okunur URI modunda bağlanır, tablo + son 50 talebi gösterir.

## Mock mailbox (mail)

`MAIL_PROVIDER=jsonfile` modunda worker, gönderilecek her maili
`test_env/mailbox/` klasörüne iki dosya olarak yazar:

- `<ts>_<template>_<request_id>.json` — şablon, subject, from, recipients,
  correlation_id, body_text, body_html, context metadata.
- `<ts>_<template>_<request_id>.html` — kolay önizleme.

Streamlit `pages/5_📬_Mailbox.py` bu klasörü tarar: sol kolon liste, sağ
kolon detay (subject, recipients, context, body_text, HTML önizleme). Key
taşıyan result maillerde secret **JSON'a sızıntı yapmaz** —
`MailMessage.secret` ayrı taşınır; UI yalnız "anahtar taşıyor" uyarısı
basar.

Konfigürasyon (`backend/.env`):

```
MAIL_PROVIDER=jsonfile              # placeholder | jsonfile | graph | smtp
MAIL_FROM=genai-noreply@allianz.com.tr
MAIL_SINK_DIR=test_env/mailbox      # mutlak path ya da CWD'ye göre relative
```

`app_env=production` iken bu adapter'lar (placeholder + jsonfile)
`allow_in_production=True` verilmediği sürece startup fail eder — yani
prod'da yanlışlıkla mailbox klasörüne düşmez.

## Hızlı başlangıç (önerilen — `main.py`)

`test_env/main.py` mock LiteLLM + Streamlit panel'i tek komutla başlatan orkestratördür.

```powershell
# 0. Allianz corp: loopback proxy bypass
$env:NO_PROXY = "localhost,127.0.0.1"

# 1. tümünü başlat (mock + panel)
py -3.14 test_env/main.py all
# mock:    http://127.0.0.1:8200
# panel:   http://127.0.0.1:8501
# Ctrl+C ile ikisini de durdurur.

# 2. ayrı ayrı çalış
py -3.14 test_env/main.py mock          # sadece mock (8200)
py -3.14 test_env/main.py panel         # sadece panel (8501)

# 3. canlılık kontrolü (servislerin çalıştığını doğrular)
py -3.14 test_env/main.py check
#  [check] mock-litellm        HTTP 200   http://127.0.0.1:8200/health/live
#  [check] mock-litellm-admin  DOWN      http://127.0.0.1:8200/key/info     (auth gerekli)
#  [check] mock-litellm-debug  DOWN      http://127.0.0.1:8200/__mock/state (auth gerekli)
#  [check] streamlit-panel     HTTP 200   http://127.0.0.1:8501/_stcore/health

# 4. (opsiyonel) tek tek örnek talep gönder — ARKA PLAN: backend API 8001'de olmalı
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py            # üçünü birden
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py litellm     # sadece litellm
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py mcp_key
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py mcp_registry
```

`main.py` başlarken `backend/.env` dosyasını okur ve değerleri mevcut shell ortamına `setdefault` ile ekler; kabukta zaten tanımlıysa onu korur. Hangi değerin nereden geldiği `[env]` bloğunda açıkça yazılır (`(from .env)` / `(from shell/unset)`).

## Backend (API + Worker) — `run_*.ps1`

`main.py` test_env içindeki **mock + panel**'i ayağa kaldırır. Gerçek backend FastAPI (8001) ve worker için hâlâ standalone PS1'ler var; bunlar backend `.venv`'i kullanıyor:

```powershell
$env:NO_PROXY = "localhost,127.0.0.1"

pwsh -File test_env/scripts/run_api.ps1     # 8001 — backend FastAPI
pwsh -File test_env/scripts/run_worker.ps1  # backend worker
```

Sonra seeded POST'lar:

```powershell
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py            # üçünü birden
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py litellm     # sadece litellm
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py mcp_key
backend/.venv/Scripts/python.exe test_env/scripts/seed_demo.py mcp_registry
```

(`run_mock.ps1` ve `run_panel.ps1` artık yok — `main.py all` aynı şeyi yapıyor.)

## `.env` yerleşimi

`main.py`'nin ihtiyacı olan tek değer `backend/.env` içinde **21. satırda** zaten var:

```
LITELLM_ACCESS_KEY=asd123
```

`GENAI_ORION_PANEL_WEBHOOK_SECRET` şu an `backend/.env` dosyasında **yok**. Backend onu FastAPI tarafında `dev-orion-secret` olarak varsayıyor; panel ile backend aynı şekilde okuduğu sürece webhook imzaları eşleşir. Override etmek istersen:

```powershell
Add-Content backend/.env "`nGENAI_ORION_PANEL_WEBHOOK_SECRET=dev-orion-secret"
```

veya tek oturum için shell'de:

```powershell
$env:GENAI_ORION_PANEL_WEBHOOK_SECRET = "dev-orion-secret"
```
