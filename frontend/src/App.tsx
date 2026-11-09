import React, { useEffect } from "react";
import { BrowserRouter, Navigate, Route, Routes, useLocation, useNavigate } from "react-router-dom";
import Shell from "./components/Shell";
import { AuthProvider, useAuth } from "./hooks/useAuth";
import { PlayerProvider } from "./hooks/usePlayer";
import { ToastProvider } from "./hooks/useToast";
import DashboardPage from "./pages/DashboardPage";
import LandingPage from "./pages/LandingPage";
import LibraryPage from "./pages/LibraryPage";
import ScanPage from "./pages/ScanPage";
import StudioPage from "./pages/StudioPage";

function Splash() {
  return (
    <div style={{ minHeight: "100vh", display: "grid", placeItems: "center" }}>
      <div className="row" style={{ gap: 12 }}>
        <span className="spinner" style={{ width: 22, height: 22 }} />
        <span className="muted">loading trill…</span>
      </div>
    </div>
  );
}

function Routed() {
  const { token, me, loading, pendingNext, clearPendingNext } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  // After OAuth, land where the user was headed.
  useEffect(() => {
    if (token && pendingNext) {
      clearPendingNext();
      navigate(pendingNext.startsWith("/") ? pendingNext : "/dashboard", { replace: true });
    }
  }, [token, pendingNext, clearPendingNext, navigate]);

  useEffect(() => {
    const titles: Record<string, string> = { "/dashboard": "Dashboard", "/studio": "Studio", "/library": "Library", "/scan": "Scan" };
    document.title = titles[location.pathname] ? `${titles[location.pathname].toLowerCase()} · trill` : "trill";
  }, [location.pathname]);

  if (!token) {
    return (
      <Routes>
        <Route path="*" element={<LandingPage />} />
      </Routes>
    );
  }
  if (loading && !me) return <Splash />;

  return (
    <Shell>
      <Routes>
        <Route path="/" element={<Navigate to="/dashboard" replace />} />
        <Route path="/dashboard" element={<DashboardPage />} />
        <Route path="/studio" element={<StudioPage />} />
        <Route path="/generate" element={<Navigate to="/studio" replace />} />
        <Route path="/library" element={<LibraryPage />} />
        <Route path="/scan" element={<ScanPage />} />
        <Route path="*" element={<Navigate to="/dashboard" replace />} />
      </Routes>
    </Shell>
  );
}

export default function App() {
  return (
    <BrowserRouter>
      <ToastProvider>
        <AuthProvider>
          <PlayerProvider>
            <Routed />
          </PlayerProvider>
        </AuthProvider>
      </ToastProvider>
    </BrowserRouter>
  );
}
