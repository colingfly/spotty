// src/config.ts
export const API_BASE: string = (import.meta.env.VITE_API_BASE as string | undefined)?.replace(/\/$/, "") || "http://127.0.0.1:8888";

export const TOKEN_KEY = "trill.token";
export const LEGACY_SID_KEY = "spotify_user_id";

export const POLL_INTERVAL_MS = 2500;
