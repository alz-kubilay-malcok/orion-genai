# GenAiOrionPanel — Frontend (Viewer)

Next.js 15 app that renders a read-only approval view fetched from the
`GenAiOrionPanel` backend (`GET /actions/{token}/view`). No mutation actions
(approve/reject/revise) live here yet — those remain on the backend's own
HTML confirmation pages for now (Bölüm 10.3).

## Development

```powershell
npm install
cp .env.example .env.local   # adjust NEXT_PUBLIC_API_BASE_URL if needed
npm run dev
```

Visit `http://localhost:3000/approvals/<token>`.

## Structure

- `app/approvals/[token]/page.tsx` — server component that fetches the view model and renders `ApprovalView`.
- `lib/api.ts` — thin fetch wrapper around the backend API.
- `lib/actionSchema.ts` — Zod schema validating the `ApprovalViewModel` JSON contract.
- `components/ApprovalView.tsx` — presentational component for the fetched data.
- `components/ResultBanner.tsx` — error/empty-state banner.
