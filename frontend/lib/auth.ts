/**
 * JWT tabanlı kimlik doğrulama — access + refresh token durumu.
 *
 * Tasarım notları:
 * - ``access_token`` her istekte Bearer header'ında gönderilir.
 *   ``localStorage``'da disk-persistent tutulur; sayfa yenilense de
 *   state korunur (CSRF açığı: SSE/sitesi başka origin'e açılamaz olduğu
 *   için risk kabul edildi; production'da HttpOnly cookie'ye geçiş
 *   sonraki sprint'te).
 * - ``refresh_token`` sadece access expire olduğunda kullanılır; kendi
 *   başına ``Authorization: Bearer`` olarak fetch'e asla takılmaz.
 * - ``me`` Zod-validated bir cache değildir; her sayfa açılışında
 *   fresh `/auth/me` çağrısı gerekir (active status realtime olsun).
 *
 * SSR notu: ``localStorage`` undefined olabilir → tüm erişimler
 * ``typeof window !== 'undefined'`` ile korunur.
 */

const ACCESS_KEY = "goa:auth:access";
const REFRESH_KEY = "goa:auth:refresh";

export type TokenResponse = {
  access_token: string;
  refresh_token: string;
  expires_in: number;  // seconds
};

export function readAccessToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(ACCESS_KEY);
}

export function readRefreshToken(): string | null {
  if (typeof window === "undefined") return null;
  return window.localStorage.getItem(REFRESH_KEY);
}

export function storeTokens(tokens: TokenResponse): void {
  if (typeof window === "undefined") return;
  window.localStorage.setItem(ACCESS_KEY, tokens.access_token);
  window.localStorage.setItem(REFRESH_KEY, tokens.refresh_token);
}

export function clearTokens(): void {
  if (typeof window === "undefined") return;
  window.localStorage.removeItem(ACCESS_KEY);
  window.localStorage.removeItem(REFRESH_KEY);
}

export function isAuthenticated(): boolean {
  return readAccessToken() !== null;
}

/**
 * ``access_token`` ``iat + jwt_access_ttl`` karşılaştırması için
 * decode etmeden expires_at tahmini yapamayız; backend'in
 * ``/auth/refresh`` orta halli 401'de tetiklendiği için optimistic
 * kontrol: süre bittiğini bilemeyiz, çoğu durumda ``/auth/me`` veya
 * başka API 401 dönerse refresh-then-retry düşeceğiz.
 *
 * decodeAccessToken — UI side'da süre göstermek için opsiyonel.
 */
export type AccessClaims = { sub: string; type: string; iat: number; exp: number; jti: string };

export function decodeAccessToken(compact: string | null): AccessClaims | null {
  if (!compact) return null;
  const parts = compact.split(".");
  if (parts.length !== 3) return null;
  try {
    const payload = JSON.parse(
      atob(parts[1].replace(/-/g, "+").replace(/_/g, "/")),
    );
    if (
      typeof payload.sub === "string" &&
      typeof payload.exp === "number" &&
      typeof payload.iat === "number"
    ) {
      return {
        sub: payload.sub,
        type: payload.type ?? "",
        iat: payload.iat,
        exp: payload.exp,
        jti: payload.jti ?? "",
      };
    }
    return null;
  } catch {
    return null;
  }
}

/** ``Date.now()`` milisaniye karşılaştırması yapacak şekilde exp saniyesini ms'ye çevirir. */
export function isAccessExpired(claims: AccessClaims, skewSeconds = 10): boolean {
  return claims.exp * 1000 <= Date.now() + skewSeconds * 1000;
}
