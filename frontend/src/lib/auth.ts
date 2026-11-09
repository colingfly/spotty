// src/lib/auth.ts
import { API_BASE, LEGACY_SID_KEY, TOKEN_KEY } from "../config";

export function getToken(): string | null {
  try {
    return localStorage.getItem(TOKEN_KEY);
  } catch {
    return null;
  }
}

export function setToken(token: string | null): void {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(LEGACY_SID_KEY);
  } catch {
    // storage unavailable; the session simply won't persist
  }
}

export function loginUrl(next = "/dashboard", switchAccount = false): string {
  const params = new URLSearchParams({ next });
  if (switchAccount) params.set("switch", "1");
  return `${API_BASE}/login?${params.toString()}`;
}

/**
 * The backend redirects to `/#token=...&next=/dashboard` after OAuth.
 * Consume the fragment once and clean the URL.
 */
export function consumeAuthFragment(): { token?: string; next?: string; error?: string } | null {
  const hash = window.location.hash.replace(/^#/, "");
  if (!hash) return null;
  const params = new URLSearchParams(hash);
  const token = params.get("token") ?? undefined;
  const next = params.get("next") ?? undefined;
  const error = params.get("auth_error") ?? undefined;
  if (!token && !error) return null;
  history.replaceState(null, "", window.location.pathname + window.location.search);
  return { token, next, error };
}
