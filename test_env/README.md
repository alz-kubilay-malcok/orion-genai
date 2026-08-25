# test_env — yerel test suite

API (8056) + worker + frontend (8058) ayaktayken Orion webhook, onay
maili ve aksiyon tıklamasını buradan çalıştırırsın. Üretime alınmaz.

## Servisler

| Servis | Adres |
| --- | --- |
| API | `http://127.0.0.1:8056` |
| Frontend | `http://localhost:8058` |
| Mock LiteLLM | `http://127.0.0.1:8200` |
| Studio | `http://127.0.0.1:8501` |

`backend/.env`: `MAIL_PROVIDER=placeholder`, `PUBLIC_ACTION_BASE_URL=http://localhost:8058/approvals`.
Worker mailleri `test_env/mailbox/` altına HTML + JSON yazar.

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

`POST /webhooks/orion`, HMAC-SHA256 raw body, header `x-genai-orion-panel-signature`.
Secret: `GENAI_ORION_PANEL_WEBHOOK_SECRET` (boşsa API imzayı atlar).
Field contract: [`docs/genai-orion-panel-talep-key-contract.md`](../docs/genai-orion-panel-talep-key-contract.md).
