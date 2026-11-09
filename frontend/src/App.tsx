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

function Routed() {
  const { token, me, loading, pendingNext, clearPendingNext } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  useEffect(() => {
    if (token && pendingNext) {
      clearPendingNext();
      navigate(pendingNext.startsWith("/") ? pendingNext : "/dashboard", { replace: true });
    }
  }, [token, pendingNext, clearPendingNext, navigate]);

  useEffect(() => {
    const titles: Record<string, string> = { "/dashboard": "profile", "/studio": "studio", "/library": "library", "/scan": "scan" };
    document.title = titles[location.pathname] ? `${titles[location.pathname]} · trill` : "trill";
  }, [location.pathname]);

  if (!token) {
    return (
      <Routes>
        <Route path="*" element={<LandingPage />} />
      </Routes>
    );
  }
  if (loading && !me) return <p className="page">loading…</p>;

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
