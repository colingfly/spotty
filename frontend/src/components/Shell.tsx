import React from "react";
import { NavLink, useNavigate } from "react-router-dom";
import { useAuth } from "../hooks/useAuth";
import { usePlayer } from "../hooks/usePlayer";
import PlayerBar from "./PlayerBar";

const LINKS = [
  { to: "/dashboard", label: "profile" },
  { to: "/studio", label: "studio" },
  { to: "/library", label: "library" },
  { to: "/scan", label: "scan" },
];

export default function Shell({ children }: { children: React.ReactNode }) {
  const { me, logout, login } = useAuth();
  const player = usePlayer();
  const navigate = useNavigate();
  const caps = me?.capabilities;

  return (
    <div className={`shell ${player.current ? "with-player" : ""}`}>
      <header className="topbar">
        <NavLink to="/dashboard" className="brand">trill</NavLink>
        <nav aria-label="main">
          {LINKS.map((l) => <NavLink key={l.to} to={l.to}>{l.label}</NavLink>)}
        </nav>
        <div className="meta">
          <span>gpu: {caps ? (caps.acestep ? "online" : "offline") : "…"}</span>
          <span>composer: {caps ? (caps.llm.configured ? "claude" : "template") : "…"}</span>
          {me && <span>user: {me.display_name}</span>}
          {me?.needs_reauth && <button onClick={() => login("/dashboard")}>reconnect spotify</button>}
          <button onClick={() => { logout(); navigate("/"); }}>sign out</button>
        </div>
      </header>
      <main className="page">
        {me?.needs_reauth && (
          <div className="notice">
            spotify disconnected this account. the library still works. reconnect to refresh the profile and generate new tracks.{" "}
            <button className="link" onClick={() => login("/dashboard")}>reconnect spotify</button>
          </div>
        )}
        {children}
      </main>
      <PlayerBar />
    </div>
  );
}
