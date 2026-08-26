/**
 * Browser: same-origin `/api` (nginx strip). Local `next dev` overrides
 * with NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000.
 *
 * SSR (Next server): container cannot use localhost for the API.
 * API_INTERNAL_URL=http://backend-api:8000 in compose.
 */

export function browserApiBase(): string {
  const raw = (process.env.NEXT_PUBLIC_API_BASE_URL ?? "/api").trim();
  return raw.replace(/\/$/, "");
}

export function serverApiBase(): string {
  const internal = (process.env.API_INTERNAL_URL ?? "").trim();
  if (internal) return internal.replace(/\/$/, "");
  return browserApiBase();
}
