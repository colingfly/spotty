import React, { useEffect, useMemo, useState } from "react";
import {
  BrowserRouter,
  Routes,
  Route,
  NavLink,
  Navigate,
} from "react-router-dom";
import { API_BASE } from "./config";
import { useSpotifyUserId } from "./hooks/useSpotifyUserId";
import DashboardPage from "./pages/DashboardPage";
import GeneratePage from "./pages/GeneratePage";
import LibraryPage from "./pages/LibraryPage";
import ScanPage from "./pages/ScanPage";

function LandingPage() {
  const loginUrl = `${API_BASE}/login`;
  return (
    <div
      style={{
        display: "flex",
        flexDirection: "column",
        alignItems: "center",
        justifyContent: "center",
        minHeight: "80vh",
        textAlign: "center",
      }}
    >
      <h1 style={{ fontSize: 56, marginBottom: 8, fontWeight: 800 }}>
        Spotty
      </h1>
      <p
        style={{
          fontSize: 20,
          color: "#888",
          maxWidth: 480,
          marginBottom: 32,
          lineHeight: 1.5,
        }}
      >
        Your Spotify taste profile drives AI music generation.
        Connect to discover your sound DNA and create tracks that match it.
      </p>
      <a href={loginUrl}>
        <button
          style={{
            background: "#1db954",
            color: "white",
            border: "none",
            borderRadius: 28,
            padding: "16px 40px",
            fontSize: 18,
            fontWeight: 600,
            cursor: "pointer",
          }}
        >
          Connect Spotify
        </button>
      </a>
    </div>
  );
}

function NavBar({
  sid,
  onUnlink,
}: {
  sid: string;
  onUnlink: () => void;
}) {
  const [acestepOk, setAcestepOk] = useState<boolean | null>(null);

  useEffect(() => {
    const check = () =>
      fetch(`${API_BASE}/api/acestep/health`)
        .then((r) => r.json())
        .then((d) => setAcestepOk(d.ok))
        .catch(() => setAcestepOk(false));
    check();
    const interval = setInterval(check, 30000);
    return () => clearInterval(interval);
  }, []);

  const linkStyle = (isActive: boolean): React.CSSProperties => ({
    color: isActive ? "#1db954" : "#888",
    textDecoration: "none",
    fontWeight: isActive ? 600 : 400,
    fontSize: 14,
    padding: "6px 0",
    borderBottom: isActive ? "2px solid #1db954" : "2px solid transparent",
  });

  return (
    <nav
      style={{
        display: "flex",
        alignItems: "center",
        gap: 24,
        padding: "12px 0",
        marginBottom: 24,
        borderBottom: "1px solid #222",
      }}
    >
      <span style={{ fontWeight: 800, fontSize: 20, marginRight: 8 }}>
        Spotty
      </span>

      <NavLink to="/dashboard" style={({ isActive }) => linkStyle(isActive)}>
        Dashboard
      </NavLink>
      <NavLink to="/generate" style={({ isActive }) => linkStyle(isActive)}>
        Generate
      </NavLink>
      <NavLink to="/library" style={({ isActive }) => linkStyle(isActive)}>
        Library
      </NavLink>
      <NavLink to="/scan" style={({ isActive }) => linkStyle(isActive)}>
        Scan
      </NavLink>

      <div style={{ flex: 1 }} />

      {/* ACE-Step health indicator */}
      <span
        title={
          acestepOk === null
            ? "Checking ACE-Step..."
            : acestepOk
            ? "ACE-Step GPU server online"
            : "ACE-Step GPU server offline"
        }
        style={{
          width: 8,
          height: 8,
          borderRadius: "50%",
          background:
            acestepOk === null ? "#555" : acestepOk ? "#1db954" : "#ff4444",
          display: "inline-block",
        }}
      />

      <span style={{ fontSize: 12, color: "#666" }}>{sid}</span>
      <button
        onClick={onUnlink}
        style={{
          background: "#222",
          color: "#888",
          border: "none",
          borderRadius: 6,
          padding: "4px 10px",
          fontSize: 12,
          cursor: "pointer",
        }}
      >
        Unlink
      </button>
    </nav>
  );
}

export default function App() {
  const { sid, unlink } = useSpotifyUserId();

  return (
    <BrowserRouter>
      <main
        style={{
          maxWidth: 1100,
          margin: "0 auto",
          padding: "16px 24px",
          minHeight: "100vh",
        }}
      >
        {!sid ? (
          <Routes>
            <Route path="*" element={<LandingPage />} />
          </Routes>
        ) : (
          <>
            <NavBar sid={sid} onUnlink={unlink} />
            <Routes>
              <Route
                path="/dashboard"
                element={<DashboardPage sid={sid} />}
              />
              <Route
                path="/generate"
                element={<GeneratePage sid={sid} />}
              />
              <Route
                path="/library"
                element={<LibraryPage sid={sid} />}
              />
              <Route path="/scan" element={<ScanPage sid={sid} />} />
              <Route
                path="*"
                element={<Navigate to="/dashboard" replace />}
              />
            </Routes>
          </>
        )}
      </main>
    </BrowserRouter>
  );
}
