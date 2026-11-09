import React from "react";
import { useAuth } from "../hooks/useAuth";

const ERRORS: Record<string, string> = {
  access_denied: "spotify sign-in was cancelled.",
  invalid_state: "that sign-in link expired. try again.",
  token_exchange_failed: "spotify rejected the sign-in. check the app's redirect uri matches the backend.",
  profile_failed: "signed in, but spotify wouldn't return your profile. try again.",
  session_expired: "your session expired. sign in again.",
  backend_outdated: "the backend is still updating. give it a minute and try again.",
};

const RIBBON = ["your rotation", "your song", "your city", "your shows"];

export default function LandingPage() {
  const { login, authError } = useAuth();

  return (
    <div className="landing">
      <header className="landing-nav container">
        <span className="wordmark">trill</span>
        <button className="mono tiny link-btn" onClick={() => login("/dashboard")}>connect spotify</button>
      </header>

      <section className="landing-hero container">
        <div className="hero-glow" />
        <div className="mono tiny dim eyebrow-mono">ai music from what you actually play</div>
        <h1 className="wordmark wordmark-hero">trill</h1>
        <p className="landing-lede">a song made out of your rotation.</p>
        <div className="row row-wrap" style={{ gap: 10, marginTop: 26 }}>
          <button className="btn btn-cream" onClick={() => login("/dashboard")}>connect spotify</button>
        </div>
        {authError && <div className="alert alert-error" style={{ marginTop: 20, maxWidth: 520 }}>{ERRORS[authError] || `sign-in failed (${authError}).`}</div>}
      </section>

      <div className="ribbon" aria-hidden>
        <div className="ribbon-track">
          {Array.from({ length: 4 }).flatMap((_, k) => RIBBON.map((t, i) => <span key={`${k}-${i}`} className="wordmark ribbon-item">{t} ·</span>))}
        </div>
      </div>

      <footer className="landing-foot container mono tiny dim">
        <span>© {new Date().getFullYear()} trill</span>
        <span>not affiliated with spotify</span>
      </footer>
    </div>
  );
}
