# GenAi Orion Panel — frontend

Next.js app: onay ekranı (`/approvals/{token}`) ve admin panel.

## Geliştirme (nginx yok)

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
npm run dev
```

Varsayılan: `http://localhost:3000`. Backend: `python backend/main.py api` (:8000).

Onay: `http://localhost:3000/approvals/<token>`
Admin: `http://localhost:3000/admin` (bootstrap superuser).

## Compose (tek port)

`deployment/.env` içinde `PANEL_PORT` (varsayılan 8056). Dışarı yalnız nginx:

- UI: `http://localhost:$PANEL_PORT/`
- API: `http://localhost:$PANEL_PORT/api/...`
- Onay: `http://localhost:$PANEL_PORT/approvals/<token>`
