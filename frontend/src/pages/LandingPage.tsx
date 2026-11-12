import React, { useEffect, useState } from "react";
import { API_BASE } from "../config";
import { useAuth } from "../hooks/useAuth";
import { api } from "../lib/api";

const ERRORS: Record<string, string> = {
  access_denied: "spotify sign-in was cancelled.",
  invalid_state: "that sign-in link expired. try again.",
  token_exchange_failed: "spotify rejected the sign-in. the app's redirect uri must match the backend.",
  profile_failed: "signed in, but spotify did not return a profile. try again.",
  session_expired: "session expired. sign in again.",
  backend_outdated: "the backend is still running the old version. try again in a few minutes.",
};

export default function LandingPage() {
  const { login, authError } = useAuth();
  const [api_status, setApiStatus] = useState<string>("checking");

  useEffect(() => {
    api.get<{ ok: boolean }>("/api/health/live").then((r) => setApiStatus(r.ok ? "online" : "error")).catch(() => setApiStatus("offline"));
  }, []);

  return (
    <div className="landing">
      <header className="topbar">
        <span className="brand">trill</span>
        <div className="meta">
          <span>api: {api_status}</span>
        </div>
      </header>

      <main>
        <p className="label">ai music from what you actually play</p>
        <h1 className="display" style={{ textTransform: "none", letterSpacing: 0, margin: "8px 0 16px" }}>trill</h1>
        <p style={{ maxWidth: 560 }}>
          trill reads your spotify top artists, builds an eight-axis taste profile, and renders an original track with ace-step 1.5. requires a spotify account.
        </p>
        <div style={{ marginTop: 20 }}>
          <button className="primary" onClick={() => login("/dashboard")}>connect spotify</button>
        </div>
        {authError && <p className="notice" style={{ maxWidth: 560 }}>{ERRORS[authError] || `sign-in failed (${authError}).`}</p>}
      </main>

      <footer>
        <span>© {new Date().getFullYear()} trill</span>
        <span>not affiliated with spotify</span>
        <span>api: {API_BASE.replace(/^https?:\/\//, "")}</span>
        <span>v2.0.0</span>
      </footer>
    </div>
  );
}
