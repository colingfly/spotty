// src/lib/api.ts
import { API_BASE } from "../config";
import { getToken, setToken } from "./auth";

export class ApiError extends Error {
  status: number;
  code: string;
  retryAfter?: number;

  constructor(status: number, code: string, message: string, retryAfter?: number) {
    super(message);
    this.status = status;
    this.code = code;
    this.retryAfter = retryAfter;
  }
}

type Listener = () => void;
const unauthorizedListeners = new Set<Listener>();

export function onUnauthorized(fn: Listener): () => void {
  unauthorizedListeners.add(fn);
  return () => unauthorizedListeners.delete(fn);
}

const FRIENDLY: Record<string, string> = {
  acestep_unavailable: "The ACE-Step GPU server is offline. Start it and try again.",
  rate_limited: "You're moving fast. Give it a few seconds.",
  reauth_required: "Your Spotify session expired. Sign in again.",
  not_linked: "This account isn't linked. Sign in with Spotify.",
  llm_unavailable: "The AI composer isn't configured on the server.",
  taste_unavailable: "Couldn't build your taste profile from Spotify right now.",
};

async function request<T>(method: string, path: string, body?: unknown, init?: RequestInit): Promise<T> {
  const headers: Record<string, string> = { Accept: "application/json" };
  const token = getToken();
  if (token) headers.Authorization = `Bearer ${token}`;
  let payload: BodyInit | undefined;
  if (body instanceof FormData) {
    payload = body;
  } else if (body !== undefined) {
    headers["Content-Type"] = "application/json";
    payload = JSON.stringify(body);
  }

  let res: Response;
  try {
    res = await fetch(`${API_BASE}${path}`, { method, headers, body: payload, ...init });
  } catch (e) {
    throw new ApiError(0, "network", "Can't reach the trill backend. Is it running?");
  }

  if (res.status === 204) return undefined as T;

  let data: any = null;
  const text = await res.text();
  if (text) {
    try {
      data = JSON.parse(text);
    } catch {
      data = { error: "bad_response", message: text.slice(0, 200) };
    }
  }

  if (!res.ok) {
    const code: string = data?.error || `http_${res.status}`;
    if (res.status === 401 && code !== "reauth_required") {
      setToken(null);
      unauthorizedListeners.forEach((fn) => fn());
    }
    const retry = Number(res.headers.get("Retry-After")) || undefined;
    const message: string = FRIENDLY[code] || data?.message || data?.detail || `Request failed (${res.status})`;
    throw new ApiError(res.status, code, message, retry);
  }
  return data as T;
}

export const api = {
  get: <T>(path: string, init?: RequestInit) => request<T>("GET", path, undefined, init),
  post: <T>(path: string, body?: unknown, init?: RequestInit) => request<T>("POST", path, body, init),
  patch: <T>(path: string, body?: unknown) => request<T>("PATCH", path, body),
  del: <T>(path: string) => request<T>("DELETE", path),
  url: (path: string) => `${API_BASE}${path}`,
};

export function qs(params: Record<string, string | number | boolean | undefined | null>): string {
  const sp = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v === undefined || v === null || v === "" || v === false) return;
    sp.set(k, String(v));
  });
  const s = sp.toString();
  return s ? `?${s}` : "";
}
