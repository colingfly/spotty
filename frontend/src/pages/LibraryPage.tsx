import React, { useEffect, useState } from "react";
import { API_BASE } from "../config";
import type { Generation } from "../types";
import AudioPlayer from "../components/AudioPlayer";

type Props = { sid: string };

const TYPE_LABELS: Record<string, string> = {
  taste_to_track: "Taste",
  mood_slider: "Mood",
  lyric_mode: "Lyrics",
  artist_fusion: "Fusion",
  cover: "Cover",
  festival: "Festival",
};

export default function LibraryPage({ sid }: Props) {
  const [generations, setGenerations] = useState<Generation[]>([]);
  const [loading, setLoading] = useState(true);
  const [selected, setSelected] = useState<Generation | null>(null);

  const fetchHistory = async () => {
    setLoading(true);
    try {
      const res = await fetch(
        `${API_BASE}/api/generate/history?spotify_user_id=${encodeURIComponent(sid)}&limit=50`
      );
      if (res.ok) {
        const data = await res.json();
        setGenerations(data.items || []);
      }
    } catch {
      // silent
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    fetchHistory();
  }, [sid]);

  const toggleFavorite = async (gen: Generation) => {
    await fetch(`${API_BASE}/api/generate/${gen.generation_id}/favorite`, {
      method: "POST",
    });
    fetchHistory();
  };

  const deleteGen = async (gen: Generation) => {
    await fetch(`${API_BASE}/api/generate/${gen.generation_id}`, {
      method: "DELETE",
    });
    if (selected?.generation_id === gen.generation_id) setSelected(null);
    fetchHistory();
  };

  return (
    <div>
      <h2 style={{ fontSize: 32, marginBottom: 4 }}>Library</h2>
      <p style={{ color: "#888", marginBottom: 24 }}>
        Your generated tracks ({generations.length})
      </p>

      {loading ? (
        <div style={{ color: "#888" }}>Loading...</div>
      ) : generations.length === 0 ? (
        <div style={{ color: "#888" }}>
          No generations yet. Go to Generate to create your first track.
        </div>
      ) : (
        <div style={{ display: "flex", gap: 24, flexWrap: "wrap" }}>
          {/* List */}
          <div style={{ flex: "1 1 400px" }}>
            {generations.map((gen) => (
              <div
                key={gen.generation_id}
                onClick={() => setSelected(gen)}
                style={{
                  display: "flex",
                  alignItems: "center",
                  gap: 12,
                  padding: "12px 16px",
                  marginBottom: 4,
                  background:
                    selected?.generation_id === gen.generation_id
                      ? "#1a1a1a"
                      : "transparent",
                  borderRadius: 8,
                  cursor: "pointer",
                  border:
                    selected?.generation_id === gen.generation_id
                      ? "1px solid #333"
                      : "1px solid transparent",
                }}
              >
                {/* Type badge */}
                <span
                  style={{
                    background: "#1db954",
                    color: "white",
                    fontSize: 10,
                    fontWeight: 700,
                    padding: "2px 8px",
                    borderRadius: 10,
                    textTransform: "uppercase",
                    whiteSpace: "nowrap",
                  }}
                >
                  {TYPE_LABELS[gen.feature_type] || gen.feature_type}
                </span>

                {/* Info */}
                <div style={{ flex: 1, overflow: "hidden" }}>
                  <div
                    style={{
                      fontSize: 14,
                      fontWeight: 500,
                      whiteSpace: "nowrap",
                      overflow: "hidden",
                      textOverflow: "ellipsis",
                    }}
                  >
                    {gen.title || gen.caption || "Untitled"}
                  </div>
                  <div style={{ fontSize: 11, color: "#888" }}>
                    {gen.created_at
                      ? new Date(gen.created_at).toLocaleDateString()
                      : ""}
                    {" · "}
                    {gen.status}
                  </div>
                </div>

                {/* Actions */}
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    toggleFavorite(gen);
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontSize: 18,
                    color: gen.is_favorite ? "#1db954" : "#555",
                  }}
                  title="Favorite"
                >
                  {gen.is_favorite ? "\u2605" : "\u2606"}
                </button>
                <button
                  onClick={(e) => {
                    e.stopPropagation();
                    deleteGen(gen);
                  }}
                  style={{
                    background: "none",
                    border: "none",
                    cursor: "pointer",
                    fontSize: 14,
                    color: "#555",
                  }}
                  title="Delete"
                >
                  x
                </button>
              </div>
            ))}
          </div>

          {/* Player */}
          <div style={{ flex: "1 1 320px", minWidth: 280 }}>
            {selected?.audio_url ? (
              <>
                <AudioPlayer
                  audioUrl={selected.audio_url}
                  title={selected.title || selected.caption || "Generated Track"}
                />
                {selected.caption && (
                  <div
                    style={{
                      marginTop: 12,
                      padding: 12,
                      background: "#1a1a1a",
                      borderRadius: 8,
                      fontSize: 13,
                      color: "#888",
                      fontStyle: "italic",
                    }}
                  >
                    {selected.caption}
                  </div>
                )}
              </>
            ) : selected ? (
              <div style={{ color: "#888", padding: 24 }}>
                {selected.status === "pending" || selected.status === "processing"
                  ? "This track is still generating..."
                  : "No audio available for this track."}
              </div>
            ) : (
              <div style={{ color: "#555", padding: 24 }}>
                Select a track to play
              </div>
            )}
          </div>
        </div>
      )}
    </div>
  );
}
