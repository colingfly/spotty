import React, { useEffect, useState } from "react";
import { API_BASE } from "../config";
import type { Artist, TasteProfile } from "../types";
import TasteRadar from "../components/TasteRadar";

type Props = { sid: string };

export default function DashboardPage({ sid }: Props) {
  const [taste, setTaste] = useState<TasteProfile | null>(null);
  const [artists, setArtists] = useState<Artist[]>([]);
  const [timeRange, setTimeRange] = useState<string>("long_term");
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    fetch(`${API_BASE}/api/me/taste?spotify_user_id=${encodeURIComponent(sid)}`)
      .then((r) => {
        if (!r.ok) return null;
        return r.json();
      })
      .then((data) => { if (data) setTaste(data); })
      .catch(() => {});
  }, [sid]);

  const fetchArtists = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/me/top-artists?spotify_user_id=${encodeURIComponent(sid)}&time_range=${timeRange}&limit=24`
      );
      const data = await res.json();
      if (res.ok) setArtists(data.items || []);
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchArtists();
  }, [sid, timeRange]);

  return (
    <div>
      <h2 style={{ fontSize: 32, marginBottom: 4 }}>Your Music Profile</h2>
      <p style={{ color: "#888", marginBottom: 24 }}>
        Linked as <code style={{ color: "#1db954" }}>{sid}</code>
      </p>

      <div style={{ display: "flex", gap: 32, flexWrap: "wrap", marginBottom: 32 }}>
        {/* Taste radar */}
        <div>
          <h3 style={{ fontSize: 18, marginBottom: 12, color: "#ccc" }}>
            Taste Profile
          </h3>
          <TasteRadar taste={taste} size={260} />
          {taste && (
            <div style={{ marginTop: 8, fontSize: 12, color: "#666" }}>
              Top genres: {(taste.genres || []).slice(0, 5).join(", ")}
            </div>
          )}
        </div>

        {/* Stats */}
        <div style={{ flex: 1, minWidth: 200 }}>
          <h3 style={{ fontSize: 18, marginBottom: 12, color: "#ccc" }}>
            Audio Features
          </h3>
          {taste && (
            <div style={{ display: "grid", gridTemplateColumns: "1fr 1fr", gap: 8 }}>
              {(
                [
                  ["Danceability", taste.danceability],
                  ["Energy", taste.energy],
                  ["Mood (Valence)", taste.valence],
                  ["Acousticness", taste.acousticness],
                  ["Instrumentalness", taste.instrumentalness],
                  ["Liveness", taste.liveness],
                  ["Speechiness", taste.speechiness],
                  ["Tempo", taste.tempo],
                ] as [string, number][]
              ).map(([label, val]) => (
                <div key={label}>
                  <div style={{ fontSize: 12, color: "#888" }}>{label}</div>
                  <div style={{ fontSize: 20, fontWeight: 600 }}>
                    {label === "Tempo"
                      ? `${Math.round(val)} BPM`
                      : `${Math.round(val * 100)}%`}
                  </div>
                </div>
              ))}
            </div>
          )}
        </div>
      </div>

      {/* Top artists */}
      <div style={{ display: "flex", gap: 12, alignItems: "center", marginBottom: 16 }}>
        <h3 style={{ fontSize: 18, margin: 0, color: "#ccc" }}>Top Artists</h3>
        <select
          value={timeRange}
          onChange={(e) => setTimeRange(e.target.value)}
          style={{
            background: "#222",
            color: "#ccc",
            border: "1px solid #444",
            borderRadius: 6,
            padding: "4px 8px",
            fontSize: 13,
          }}
        >
          <option value="short_term">Last 4 weeks</option>
          <option value="medium_term">Last 6 months</option>
          <option value="long_term">All time</option>
        </select>
        {loading && <span style={{ color: "#888", fontSize: 13 }}>Loading...</span>}
      </div>

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(180px, 1fr))",
          gap: 12,
        }}
      >
        {artists.map((a) => (
          <div
            key={a.id}
            style={{
              background: "#1a1a1a",
              borderRadius: 10,
              padding: 10,
              overflow: "hidden",
            }}
          >
            <img
              src={a.image || "https://via.placeholder.com/180x180?text=?"}
              alt={a.name}
              style={{
                width: "100%",
                aspectRatio: "1",
                objectFit: "cover",
                borderRadius: 8,
              }}
            />
            <div
              style={{
                marginTop: 8,
                fontSize: 14,
                fontWeight: 600,
                whiteSpace: "nowrap",
                overflow: "hidden",
                textOverflow: "ellipsis",
              }}
            >
              {a.name}
            </div>
            <div style={{ fontSize: 11, color: "#888", marginTop: 2 }}>
              {a.genres?.slice(0, 2).join(", ")}
            </div>
          </div>
        ))}
      </div>
    </div>
  );
}
