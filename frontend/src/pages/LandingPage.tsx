import React from "react";
import { Pause, Play, SkipBack, SkipForward } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import Waveform from "../components/Waveform";

const ERRORS: Record<string, string> = {
  access_denied: "spotify sign-in was cancelled.",
  invalid_state: "that sign-in link expired. try again.",
  token_exchange_failed: "spotify rejected the sign-in. check the app's redirect uri matches the backend.",
  profile_failed: "signed in, but spotify wouldn't return your profile. try again.",
  session_expired: "your session expired. sign in again to keep going.",
};

const RIBBON = ["your rotation", "your song", "your city", "your shows"];

export default function LandingPage() {
  const { login, authError } = useAuth();
  const year = new Date().getFullYear();

  return (
    <div className="landing">
      <header className="landing-nav container">
        <span className="wordmark">trill</span>
        <nav className="row" style={{ gap: 18 }}>
          <a href="#song" className="mono tiny">your song</a>
          <a href="#shows" className="mono tiny">shows</a>
          <button className="mono tiny link-btn" onClick={() => login("/dashboard")}>get it</button>
        </nav>
      </header>

      <section className="landing-hero container">
        <div className="hero-glow" />
        <div className="mono tiny dim eyebrow-mono">vol. 01 / ai music from what you actually play</div>
        <h1 className="wordmark wordmark-hero">trill</h1>
        <p className="landing-lede">
          a song made out of your rotation. then the shows worth pulling up to, matched to how you listen.
        </p>
        <div className="row row-wrap" style={{ gap: 10, marginTop: 26 }}>
          <button className="btn btn-cream" onClick={() => login("/studio")}>make my song</button>
          <button className="btn btn-outline" onClick={() => login("/scan")}>scan a flyer</button>
        </div>
        {authError && <div className="alert alert-error" style={{ marginTop: 20, maxWidth: 520 }}>{ERRORS[authError] || `sign-in failed (${authError}).`}</div>}
      </section>

      <div className="ribbon" aria-hidden>
        <div className="ribbon-track">
          {Array.from({ length: 4 }).flatMap((_, k) => RIBBON.map((t, i) => <span key={`${k}-${i}`} className="wordmark ribbon-item">{t} ·</span>))}
        </div>
      </div>

      <section id="song" className="landing-section container">
        <div className="landing-grid">
          <div>
            <div className="mono tiny dim">01 / your song</div>
            <h2 className="landing-h2">nobody else got this one.</h2>
            <p className="landing-copy">
              trill reads your listening history and makes a track in your lane. same mood, same tempo, same late-night energy as what you keep on repeat.
            </p>
            <ol className="steps">
              <li><span className="mono">01</span> connect spotify</li>
              <li><span className="mono">02</span> trill learns your rotation</li>
              <li><span className="mono">03</span> your song drops</li>
            </ol>
          </div>
          <div className="phone">
            <div className="row between mono tiny dim"><span>your song</span><span>made for you</span></div>
            <div className="phone-art">
              <img src="/trill-tile.png" alt="" />
            </div>
            <div style={{ fontWeight: 700, marginTop: 14 }}>[your track title]</div>
            <div className="tiny dim">built from your rotation</div>
            <div style={{ height: 34, marginTop: 14 }}><Waveform peaks={null} progress={0.38} variant="violet" bars={56} /></div>
            <div className="row between mono tiny dim" style={{ marginTop: 4 }}><span>1:12</span><span>3:04</span></div>
            <div className="row" style={{ justifyContent: "center", gap: 18, marginTop: 12 }}>
              <SkipBack size={16} className="dim" />
              <span className="btn btn-cream btn-round" style={{ width: 44, height: 44 }}><Play size={16} fill="currentColor" /></span>
              <SkipForward size={16} className="dim" />
            </div>
          </div>
        </div>
      </section>

      <section id="shows" className="landing-section container">
        <div className="landing-grid reverse">
          <div className="phone flyer">
            <div className="row between mono tiny dim"><span>scan a flyer</span><span>live</span></div>
            <div className="flyer-frame">
              <div className="flyer-paper">
                <div className="wordmark" style={{ fontSize: 28, color: "#15111b" }}>live</div>
                <div className="flyer-block" />
                <div className="mono" style={{ fontSize: 9, color: "#15111b", marginTop: 8 }}>[artist]<br />[venue] / [date]</div>
              </div>
            </div>
            <div className="mono tiny" style={{ color: "var(--accent)", marginTop: 12 }}>match found. similar shows near you</div>
            {[1, 2, 3].map((i) => (
              <div key={i} className="row between" style={{ marginTop: 8 }}>
                <div><div style={{ fontWeight: 600, fontSize: 12 }}>[artist]</div><div className="mono tiny dim">[venue] / [date]</div></div>
                <span className="btn btn-cream btn-sm" style={{ fontSize: 11 }}>tickets</span>
              </div>
            ))}
          </div>
          <div>
            <div className="mono tiny dim">02 / shows</div>
            <h2 className="landing-h2">see a flyer on a pole. point your phone at it.</h2>
            <p className="landing-copy">
              trill reads the poster, finds the show, and pulls up others like it nearby, ranked against what you already play.
            </p>
          </div>
        </div>
      </section>

      <section className="landing-outro container">
        <div className="wordmark wordmark-outro">stay trill.</div>
        <button className="btn btn-cream" onClick={() => login("/dashboard")}>get trill</button>
      </section>

      <footer className="landing-foot container mono tiny dim">
        <span>© {year} trill</span>
        <span>not affiliated with spotify</span>
      </footer>
      <span style={{ display: "none" }}><Pause /></span>
    </div>
  );
}
