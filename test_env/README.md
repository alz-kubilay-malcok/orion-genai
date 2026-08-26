# test_env — yerel test suite

Compose (`PANEL_PORT`, varsayılan 8056) veya local API (:8000) +
`next dev` (:3000) ayaktayken Orion webhook, onay maili ve aksiyon
tıklamasını buradan çalıştırırsın. Üretime alınmaz.

## Servisler

| Servis | Compose (nginx) | Local (nginx yok) |
| --- | --- | --- |
| UI + API | `http://127.0.0.1:$PANEL_PORT` | UI `:3000`, API `:8000` |
| Webhook | `POST /api/webhooks/orion` | `POST /webhooks/orion` |
| Mock LiteLLM | `http://127.0.0.1:8200` | aynı |
| Studio | `http://127.0.0.1:8501` | aynı |

`backend/.env`: `MAIL_PROVIDER=placeholder`, local için
`PUBLIC_ACTION_BASE_URL=http://localhost:3000/approvals`.
Compose worker `PUBLIC_BASE_URL/approvals` kullanır.
Worker mailleri `test_env/mailbox/` altına HTML + JSON yazar.

Studio API tabanı: local `http://127.0.0.1:8000`; compose
`http://127.0.0.1:$PANEL_PORT/api` (`ORION_STUDIO_API_BASE`).

## Çalıştırma

```bash
# 1. API + worker + frontend (docker compose veya local)
# 2. mock LiteLLM + Studio
python test_env/main.py all
```

Compose worker mailleri host `test_env/mailbox` klasörüne yazar
(`MAIL_SINK_DIR` volume). Local worker da aynı klasöre yazar.

Studio: http://127.0.0.1:8501

- LiteLLM Key / MCP Key / MCP Registry — imzalı webhook
- Mailbox — HTML önizleme, Onayla / Revize / Reddet linkleri frontend’e açılır
- Requests — Postgres `requests` (backend/.env)

```bash
python test_env/main.py seed          # üç talep türü
python test_env/main.py seed litellm
python test_env/main.py check
python test_env/main.py mock          # yalnız 8200
```

Studio bağımlılığı: `pip install -r test_env/requirements.txt`

## Webhook

Compose: `POST /api/webhooks/orion`. Local FastAPI: `POST /webhooks/orion`.
HMAC-SHA256 raw body, header `x-genai-orion-panel-signature`.
Secret: `GENAI_ORION_PANEL_WEBHOOK_SECRET` (boşsa API imzayı atlar).
Field contract: [`docs/genai-orion-panel-talep-key-contract.md`](../docs/genai-orion-panel-talep-key-contract.md).
