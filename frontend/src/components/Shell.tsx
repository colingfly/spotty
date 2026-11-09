import React, { useEffect, useRef, useState } from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { Library, LogOut, RefreshCw, ScanLine, Sparkles, Wand2, LayoutDashboard } from "lucide-react";
import { useAuth } from "../hooks/useAuth";
import { usePlayer } from "../hooks/usePlayer";
import PlayerBar from "./PlayerBar";

const LINKS = [
  { to: "/dashboard", label: "Dashboard", icon: LayoutDashboard },
  { to: "/studio", label: "Studio", icon: Wand2 },
  { to: "/library", label: "Library", icon: Library },
  { to: "/scan", label: "Scan", icon: ScanLine },
];

function Avatar({ name, url }: { name: string; url: string | null }) {
  if (url) return <img className="avatar" src={url} alt={name} referrerPolicy="no-referrer" />;
  return <div className="avatar avatar-fallback">{name.slice(0, 1).toUpperCase()}</div>;
}

export default function Shell({ children }: { children: React.ReactNode }) {
  const { me, logout, login } = useAuth();
  const player = usePlayer();
  const navigate = useNavigate();
  const [open, setOpen] = useState(false);
  const menuRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    const onDoc = (e: MouseEvent) => { if (!menuRef.current?.contains(e.target as Node)) setOpen(false); };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [open]);

  const caps = me?.capabilities;
  const llmOn = !!caps?.llm?.configured;

  return (
    <div className={`shell ${player.current ? "shell--player" : ""}`}>
      <header className="nav">
        <div className="container nav-inner">
          <NavLink to="/dashboard" className="brand">
            <span className="brand-mark"><img src="/trill-tile.png" alt="" /></span>
            <span className="wordmark" style={{ fontSize: 24 }}>trill</span>
          </NavLink>
          <nav className="nav-links">
            {LINKS.map((l) => (
              <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
                <l.icon size={16} /> {l.label}
              </NavLink>
            ))}
          </nav>
          <div className="nav-right">
            <span className="status-pill" title={caps?.acestep ? "ACE-Step GPU server online" : "ACE-Step GPU server offline. Start it to generate."}>
              <span className={`status-dot ${caps ? (caps.acestep ? "ok" : "bad") : ""}`} />
              <span className="label">GPU</span>
            </span>
            <span className="status-pill" title={llmOn ? `Claude composer on (${caps?.llm.model})` : "Template composer. Set ANTHROPIC_API_KEY to enable Claude."}>
              <span className={`status-dot ${caps ? (llmOn ? "ai" : "") : ""}`} />
              <span className="label">{llmOn ? "Claude" : "Template"}</span>
              {llmOn && <Sparkles size={12} />}
            </span>
            {me && (
              <div style={{ position: "relative" }} ref={menuRef}>
                <button className="btn btn-ghost" style={{ padding: 4, borderRadius: 999 }} onClick={() => setOpen((o) => !o)} aria-haspopup="menu" aria-expanded={open}>
                  <Avatar name={me.display_name} url={me.avatar_url} />
                </button>
                {open && (
                  <div className="menu" role="menu">
                    <div style={{ padding: "8px 12px 10px" }}>
                      <div style={{ fontWeight: 700, fontSize: 14 }}>{me.display_name}</div>
                      <div className="tiny dim mono">{me.spotify_user_id}{me.product ? ` · ${me.product}` : ""}</div>
                    </div>
                    {me.needs_reauth && (
                      <button className="menu-item" onClick={() => login("/dashboard")}><RefreshCw size={15} /> Reconnect Spotify</button>
                    )}
                    <button className="menu-item" onClick={() => login("/dashboard", true)}><RefreshCw size={15} /> Switch account</button>
                    <button className="menu-item danger" onClick={() => { setOpen(false); logout(); navigate("/"); }}><LogOut size={15} /> Sign out</button>
                  </div>
                )}
              </div>
            )}
          </div>
        </div>
      </header>

      <main className="container" style={{ flex: 1 }}>
        {me?.needs_reauth && (
          <div className="alert alert-warn" style={{ marginTop: 16, alignItems: "center" }}>
            <RefreshCw size={16} />
            <span style={{ flex: 1 }}>Spotify disconnected this account. Your library still works; reconnect to refresh your profile and generate new tracks.</span>
            <button className="btn btn-primary btn-sm" onClick={() => login("/dashboard")}>Reconnect Spotify</button>
          </div>
        )}
        {children}
      </main>

      <nav className="mobile-nav">
        {LINKS.map((l) => (
          <NavLink key={l.to} to={l.to} className={({ isActive }) => `nav-link ${isActive ? "active" : ""}`}>
            <l.icon size={18} /> {l.label}
          </NavLink>
        ))}
      </nav>

      <PlayerBar />
    </div>
  );
}
