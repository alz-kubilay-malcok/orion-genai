# GenAi Orion Panel — frontend

Next.js app: onay ekranı (`/approvals/{token}`) ve admin panel.

## Geliştirme

```bash
cd frontend
npm install
cp .env.example .env.local   # NEXT_PUBLIC_API_BASE_URL=http://localhost:8056
npm run dev
```

Varsayılan: `http://localhost:8058`.

Onay: `http://localhost:8058/approvals/<token>`
Admin: `http://localhost:8058/admin` (bootstrap superuser).
