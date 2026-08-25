import { z } from "zod";

import {
  clearTokens,
  readAccessToken,
  readRefreshToken,
  storeTokens,
} from "./auth";

const API_BASE_URL =
  process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8056";

const tokenResponseSchema = z.object({
  access_token: z.string(),
  refresh_token: z.string(),
  expires_in: z.number(),
});

const userSchema = z.object({
  id: z.string(),
  username: z.string(),
  email: z.string().nullable(),
  display_name: z.string().nullable(),
  is_active: z.boolean(),
  is_superuser: z.boolean(),
});
export type AuthUser = z.infer<typeof userSchema>;

/**
 * Refresh dedupe — sayfada birden fazla paralel fetch 401 alırsa,
 * hepsi ``refreshAccessToken()`` çağırmaya çalışmasın diye tek ortak
 * promise'i tutuyoruz. Hata durumunda taze deneme yapılabilsin diye
 * değişken temizlenir.
 */
let refreshInFlight: Promise<string | null> | null = null;

async function tryRefreshAccessToken(): Promise<string | null> {
  if (typeof window === "undefined") return null;
  const refresh = readRefreshToken();
  if (!refresh) return null;

  try {
    const res = await fetch(`${API_BASE_URL}/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refresh_token: refresh }),
      cache: "no-store",
    });
    if (!res.ok) {
      clearTokens();
      return null;
    }
    const json = tokenResponseSchema.parse(await res.json());
    storeTokens(json);
    return json.access_token;
  } catch {
    clearTokens();
    return null;
  }
}

async function adminFetch(
  path: string,
  init?: RequestInit & { retry?: boolean },
): Promise<Response> {
  const headers = new Headers(init?.headers);
  if (init?.body && !headers.has("Content-Type")) {
    headers.set("Content-Type", "application/json");
  }
  const access = readAccessToken();
  if (access) headers.set("Authorization", `Bearer ${access}`);

  const res = await fetch(`${API_BASE_URL}${path}`, {
    ...init,
    headers,
    credentials: "include",
    cache: "no-store",
  });

  // 401 → refresh attempt (sadece 1 kez).
  if (res.status === 401 && init?.retry !== false) {
    if (refreshInFlight === null) {
      refreshInFlight = tryRefreshAccessToken().finally(() => {
        refreshInFlight = null;
      });
    }
    const newAccess = await refreshInFlight;
    if (newAccess) {
      const retryHeaders = new Headers(headers);
      retryHeaders.set("Authorization", `Bearer ${newAccess}`);
      const retry = await fetch(`${API_BASE_URL}${path}`, {
        ...init,
        headers: retryHeaders,
        credentials: "include",
        cache: "no-store",
      });
      return retry;
    }
    // refresh başarısız → sayfayı logout'a çekilebilir, UI'a bırakıyoruz.
  }
  return res;
}

// ---- auth -------------------------------------------------------------

export type LoginFailure =
  | { kind: "invalid"; message: string }
  | { kind: "rate_limit"; retryAfter: number; message: string }
  | { kind: "network"; message: string };

export type LoginResult =
  | { kind: "ok"; user: AuthUser }
  | { kind: "invalid"; message: string }
  | { kind: "rate_limit"; retryAfter: number; message: string }
  | { kind: "network"; message: string };

export async function loginRequest(
  username: string,
  password: string,
): Promise<LoginResult> {
  let res: Response;
  try {
    res = await fetch(`${API_BASE_URL}/auth/login`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ username, password }),
      cache: "no-store",
      credentials: "include",
    });
  } catch {
    return { kind: "network", message: "Bağlantı kurulamadı" };
  }
  if (res.status === 429) {
    const retryAfter = Number(res.headers.get("Retry-After") ?? 60);
    return { kind: "rate_limit", retryAfter, message: "Çok fazla deneme" };
  }
  if (res.status === 401 || res.status === 400) {
    return { kind: "invalid", message: "Kullanıcı adı veya şifre hatalı" };
  }
  if (!res.ok) {
    const txt = await res.text().catch(() => "");
    return { kind: "invalid", message: txt || `Beklenmeyen hata (${res.status})` };
  }
  const tokens = tokenResponseSchema.parse(await res.json());
  storeTokens(tokens);

  // Oturumu açan kişiyi /me ile çekelim — login JSON'unda user yok.
  const user = await fetchCurrentUser();
  if (!user) {
    clearTokens();
    return { kind: "invalid", message: "Kullanıcı doğrulanamadı" };
  }
  return { kind: "ok", user };
}

export async function logoutRequest(): Promise<void> {
  clearTokens();
  // Backend stateful logout yok; client-side token drop yeter.
}

export async function fetchCurrentUser(): Promise<AuthUser | null> {
  const res = await adminFetch("/auth/me", { retry: false });
  if (res.status === 401) return null;
  if (!res.ok) return null;
  return userSchema.parse(await res.json());
}

// ---- admin requests (unrelated to LDAP) ------------------------------

export const requestSummarySchema = z.object({
  request_id: z.string(),
  request_type: z.string(),
  status: z.string(),
  genai_orion_panel_ticket_id: z.string(),
  requester_name: z.string(),
  requester_email: z.string(),
  environment: z.string().nullable(),
  created_at: z.string(),
});
export type RequestSummary = z.infer<typeof requestSummarySchema>;

export async function listRequests(status = "all"): Promise<RequestSummary[]> {
  const qs = status && status !== "all" ? `?status=${encodeURIComponent(status)}` : "";
  const res = await adminFetch(`/admin/requests${qs}`);
  if (!res.ok) throw new Error("Talepler yüklenemedi");
  return requestSummarySchema.array().parse(await res.json());
}

export const adminRequestDetailSchema = z.object({
  request_id: z.string(),
  request_type: z.enum(["litellm_key", "mcp_key", "mcp_server_registry"]),
  status: z.string(),
  request_version: z.number(),
  genai_orion_panel_ticket_id: z.string(),
  genai_orion_panel_ticket_url: z.string(),
  requester_name: z.string(),
  requester_email: z.string(),
  environment: z.string(),
  created_at: z.string(),
  detail: z.record(z.string(), z.unknown()),
  available_actions: z.array(z.enum(["approve", "revise", "reject"])),
});
export type AdminRequestDetail = z.infer<typeof adminRequestDetailSchema>;

export async function getRequestDetail(requestId: string): Promise<AdminRequestDetail> {
  const res = await adminFetch(`/admin/requests/${encodeURIComponent(requestId)}`);
  if (!res.ok) throw new Error("Talep bulunamadı");
  return adminRequestDetailSchema.parse(await res.json());
}

type AdminActionResult =
  | { ok: true; status: string }
  | { ok: false; errorCode: string };

async function postAdminAction(path: string, body: object): Promise<AdminActionResult> {
  const res = await adminFetch(path, { method: "POST", body: JSON.stringify(body) });
  const json = await res.json().catch(() => ({}));
  if (!res.ok) return { ok: false, errorCode: json.error_code ?? json.detail ?? "UNKNOWN_ERROR" };
  return { ok: true, status: json.status };
}

export const adminApprove = (
  requestId: string,
  body: { request_version: number; allows_all_tools?: boolean | null },
) => postAdminAction(`/admin/requests/${requestId}/approve`, body);

export const adminRevise = (
  requestId: string,
  body: {
    request_version: number;
    team_id: string;
    max_parallel_requests: number;
    admin_note?: string;
    models?: string[] | null;
    response_window?: string | null;
    usage_frequency?: string | null;
  },
) => postAdminAction(`/admin/requests/${requestId}/revise`, body);

export const adminReject = (
  requestId: string,
  body: { request_version: number; reject_reason: string },
) => postAdminAction(`/admin/requests/${requestId}/reject`, body);

// ---- Approvers (onay maili alıcıları) --------------------------------

export const approverItemSchema = z.object({
  id: z.string(),
  email: z.string(),
  scope: z.string(),
  sort_order: z.number(),
  is_active: z.boolean(),
  created_at: z.string().nullable(),
});
export type ApproverItem = z.infer<typeof approverItemSchema>;

export async function listApprovers(): Promise<ApproverItem[]> {
  const res = await adminFetch("/admin/approvers");
  if (!res.ok) throw new Error("Onaylayan listesi alınamadı");
  return approverItemSchema.array().parse(await res.json());
}

export async function createApprover(email: string): Promise<ApproverItem> {
  const res = await adminFetch("/admin/approvers", {
    method: "POST",
    body: JSON.stringify({ email }),
  });
  if (res.status === 409) throw new Error("Bu e-posta zaten listede");
  if (res.status === 422) throw new Error("Geçerli bir e-posta girin");
  if (!res.ok) throw new Error("Onaylayan eklenemedi");
  return approverItemSchema.parse(await res.json());
}

export async function patchApprover(
  id: string,
  body: { is_active?: boolean; sort_order?: number },
): Promise<ApproverItem> {
  const res = await adminFetch(`/admin/approvers/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(body),
  });
  if (res.status === 404) throw new Error("Kayıt bulunamadı");
  if (!res.ok) throw new Error("Güncelleme başarısız");
  return approverItemSchema.parse(await res.json());
}

export async function deleteApprover(id: string): Promise<void> {
  const res = await adminFetch(`/admin/approvers/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (res.status === 404) throw new Error("Kayıt bulunamadı");
  if (!res.ok) throw new Error("Silinemedi");
}

// ---- LDAP mappings (kılavuz §5) --------------------------------------

export const ldapMappingItemSchema = z.object({
  id: z.string(),
  org_id: z.string(),
  group_dn: z.string(),
  role: z.string(),
  role_id: z.string(),
  namespace_id: z.string().nullable(),
  created_at: z.string(),
});
export type LdapMappingItem = z.infer<typeof ldapMappingItemSchema>;

export const ldapMappingCreateSchema = z.object({
  org_id: z.string().uuid("Geçerli bir organizasyon id girin"),
  group_dn: z.string().min(3, "Group DN zorunlu"),
  role: z.string().min(1, "Rol zorunlu"),
  namespace_id: z.string().uuid().nullable().optional(),
});
export type LdapMappingCreatePayload = z.infer<typeof ldapMappingCreateSchema>;

export async function listLdapMappings(orgId: string): Promise<LdapMappingItem[]> {
  const res = await adminFetch(
    `/admin/ldap-mappings?org_id=${encodeURIComponent(orgId)}`,
  );
  if (res.status === 403) throw new Error("Bu org üzerinde admin yetkisi gerekli");
  if (!res.ok) throw new Error("LDAP mapping listesi alınamadı");
  return ldapMappingItemSchema.array().parse(await res.json());
}

export async function createLdapMapping(
  payload: LdapMappingCreatePayload,
): Promise<LdapMappingItem> {
  const res = await adminFetch(`/admin/ldap-mappings`, {
    method: "POST",
    body: JSON.stringify(payload),
  });
  if (res.status === 409) throw new Error("Bu mapping zaten mevcut");
  if (res.status === 404) {
    const txt = await res.text().catch(() => "");
    throw new Error(txt || "Org/role/namespace bulunamadı");
  }
  if (!res.ok) throw new Error("Mapping oluşturulamadı");
  return ldapMappingItemSchema.parse(await res.json());
}

export async function deleteLdapMapping(id: string): Promise<void> {
  const res = await adminFetch(`/admin/ldap-mappings/${encodeURIComponent(id)}`, {
    method: "DELETE",
  });
  if (res.status === 404) throw new Error("Mapping bulunamadı");
  if (!res.ok) throw new Error("Mapping silinemedi");
}
