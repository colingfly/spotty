import { useEffect, useState } from "react";

export function useSpotifyUserId() {
  const [sid, setSid] = useState<string | null>(null);

  useEffect(() => {
    const hash = window.location.hash;
    const m = /sid=([^&]+)/.exec(hash);
    if (m?.[1]) {
      localStorage.setItem("spotify_user_id", m[1]);
      setSid(m[1]);
      history.replaceState(null, "", window.location.pathname);
      return;
    }
    const saved = localStorage.getItem("spotify_user_id");
    if (saved) setSid(saved);
  }, []);

  const unlink = () => {
    localStorage.removeItem("spotify_user_id");
    setSid(null);
    window.location.href = "/";
  };

  return { sid, unlink };
}
