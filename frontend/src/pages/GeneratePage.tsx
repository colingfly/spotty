import React, { useEffect, useState } from "react";
import { API_BASE } from "../config";
import type { TasteProfile, AudioFeatureKey } from "../types";
import { AUDIO_FEATURES } from "../types";
import TasteRadar from "../components/TasteRadar";
import AudioPlayer from "../components/AudioPlayer";
import GenerateButton from "../components/GenerateButton";
import { useGeneration } from "../hooks/useGeneration";

type Props = { sid: string };

type Tab = "taste" | "mood" | "lyrics";

export default function GeneratePage({ sid }: Props) {
  const [taste, setTaste] = useState<TasteProfile | null>(null);
  const [loadingTaste, setLoadingTaste] = useState(false);
  const [activeTab, setActiveTab] = useState<Tab>("taste");
  const [overrides, setOverrides] = useState<Partial<Record<AudioFeatureKey, number>>>({});
  const [lyrics, setLyrics] = useState("");
  const { status, generation, error, generate, reset } = useGeneration();

  useEffect(() => {
    const fetchTaste = async () => {
      setLoadingTaste(true);
      try {
        const res = await fetch(
          `${API_BASE}/api/me/taste?spotify_user_id=${encodeURIComponent(sid)}`
        );
        if (res.ok) {
          setTaste(await res.json());
        }
      } catch {
        // silent
      } finally {
        setLoadingTaste(false);
      }
    };
    fetchTaste();
  }, [sid]);

  const handleGenerate = () => {
    if (activeTab === "taste") {
      generate("/api/generate/taste-to-track", {
        spotify_user_id: sid,
      });
    } else if (activeTab === "mood") {
      generate("/api/generate/custom", {
        spotify_user_id: sid,
        overrides,
      });
    } else if (activeTab === "lyrics") {
      generate("/api/generate/lyric-mode", {
        spotify_user_id: sid,
        lyrics,
        overrides,
      });
    }
  };

  const handleOverride = (key: AudioFeatureKey, value: number) => {
    setOverrides((prev) => ({ ...prev, [key]: value }));
  };

  const captionPreview = generation?.caption || null;

  return (
    <div>
      <h2 style={{ fontSize: 32, marginBottom: 4 }}>Generate Music</h2>
      <p style={{ color: "#888", marginBottom: 24 }}>
        Your Spotify taste drives AI music generation
      </p>

      {/* Tabs */}
      <div style={{ display: "flex", gap: 0, marginBottom: 24 }}>
        {(
          [
            ["taste", "Taste to Track"],
            ["mood", "Mood Sliders"],
            ["lyrics", "Lyric Mode"],
          ] as [Tab, string][]
        ).map(([key, label]) => (
          <button
            key={key}
            onClick={() => {
              setActiveTab(key);
              reset();
            }}
            style={{
              padding: "10px 20px",
              background: activeTab === key ? "#1db954" : "#222",
              color: activeTab === key ? "white" : "#888",
              border: "none",
              borderBottom:
                activeTab === key ? "2px solid #1db954" : "2px solid #333",
              cursor: "pointer",
              fontSize: 14,
              fontWeight: activeTab === key ? 600 : 400,
            }}
          >
            {label}
          </button>
        ))}
      </div>

      <div style={{ display: "flex", gap: 32, flexWrap: "wrap" }}>
        {/* Left: Controls */}
        <div style={{ flex: "1 1 320px", minWidth: 280 }}>
          {loadingTaste ? (
            <div style={{ color: "#888" }}>Loading taste profile...</div>
          ) : !taste ? (
            <div style={{ color: "#888" }}>
              Could not load taste profile. Make sure Spotify is connected.
            </div>
          ) : (
            <>
              <TasteRadar
                taste={taste}
                overrides={activeTab === "mood" ? overrides : undefined}
                onOverride={activeTab === "mood" ? handleOverride : undefined}
                interactive={activeTab === "mood"}
                size={280}
              />

              {activeTab === "mood" && (
                <div style={{ marginTop: 16 }}>
                  <div
                    style={{
                      fontSize: 12,
                      color: "#666",
                      marginBottom: 8,
                    }}
                  >
                    Click the dots on the radar to adjust values. Excludes
                    tempo.
                  </div>
                  {AUDIO_FEATURES.filter((k) => k !== "tempo").map((key) => (
                    <div
                      key={key}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        gap: 8,
                        marginBottom: 6,
                      }}
                    >
                      <span
                        style={{
                          width: 100,
                          fontSize: 13,
                          color: "#aaa",
                          textTransform: "capitalize",
                        }}
                      >
                        {key}
                      </span>
                      <input
                        type="range"
                        min={0}
                        max={100}
                        value={Math.round(
                          (overrides[key] ?? taste[key]) * 100
                        )}
                        onChange={(e) =>
                          handleOverride(key, parseInt(e.target.value) / 100)
                        }
                        style={{ flex: 1, accentColor: "#1db954" }}
                      />
                      <span
                        style={{
                          width: 36,
                          fontSize: 12,
                          color: "#888",
                          textAlign: "right",
                        }}
                      >
                        {Math.round((overrides[key] ?? taste[key]) * 100)}%
                      </span>
                    </div>
                  ))}
                  <button
                    onClick={() => setOverrides({})}
                    style={{
                      marginTop: 8,
                      padding: "6px 12px",
                      background: "#333",
                      color: "#aaa",
                      border: "none",
                      borderRadius: 6,
                      cursor: "pointer",
                      fontSize: 12,
                    }}
                  >
                    Reset to my profile
                  </button>
                </div>
              )}

              {activeTab === "lyrics" && (
                <div style={{ marginTop: 16 }}>
                  <textarea
                    value={lyrics}
                    onChange={(e) => setLyrics(e.target.value)}
                    placeholder={`[verse]\nWrite your lyrics here...\n\n[chorus]\nYour chorus goes here...`}
                    rows={10}
                    style={{
                      width: "100%",
                      background: "#1a1a1a",
                      color: "#eee",
                      border: "1px solid #333",
                      borderRadius: 8,
                      padding: 12,
                      fontSize: 14,
                      fontFamily: "monospace",
                      resize: "vertical",
                    }}
                  />
                  <div style={{ fontSize: 12, color: "#666", marginTop: 4 }}>
                    {lyrics.length} / 4096 chars. Use [verse], [chorus], [bridge]
                    tags.
                  </div>
                </div>
              )}

              <div style={{ marginTop: 24 }}>
                <GenerateButton
                  onClick={handleGenerate}
                  status={status}
                  disabled={activeTab === "lyrics" && !lyrics.trim()}
                />
                {activeTab === "lyrics" && !lyrics.trim() && (
                  <div style={{ color: "#666", fontSize: 12, marginTop: 6 }}>
                    Enter lyrics above to enable generation
                  </div>
                )}
              </div>

              {error && (
                <div
                  style={{
                    color: "#ff4444",
                    marginTop: 12,
                    fontSize: 14,
                  }}
                >
                  {error}
                </div>
              )}

              {captionPreview && (
                <div
                  style={{
                    marginTop: 16,
                    padding: 12,
                    background: "#1a1a1a",
                    borderRadius: 8,
                    fontSize: 13,
                    color: "#aaa",
                    fontStyle: "italic",
                  }}
                >
                  <strong style={{ color: "#888" }}>Caption:</strong>{" "}
                  {captionPreview}
                </div>
              )}
            </>
          )}
        </div>

        {/* Right: Output */}
        <div style={{ flex: "1 1 320px", minWidth: 280 }}>
          {status === "generating" && (
            <div
              style={{
                textAlign: "center",
                padding: 40,
                color: "#888",
              }}
            >
              <div
                style={{
                  width: 48,
                  height: 48,
                  border: "3px solid #333",
                  borderTopColor: "#1db954",
                  borderRadius: "50%",
                  animation: "spin 1s linear infinite",
                  margin: "0 auto 16px",
                }}
              />
              <div>Generating your track...</div>
              <div style={{ fontSize: 12, marginTop: 4 }}>
                This usually takes 15-30 seconds
              </div>
            </div>
          )}

          {generation?.audio_url && (
            <AudioPlayer
              audioUrl={generation.audio_url}
              title={generation.title || "Generated Track"}
            />
          )}

          {generation?.params && status === "complete" && (
            <div
              style={{
                marginTop: 16,
                padding: 12,
                background: "#1a1a1a",
                borderRadius: 8,
                fontSize: 12,
                color: "#666",
              }}
            >
              <div>
                <strong>BPM:</strong> {generation.params.bpm}
              </div>
              <div>
                <strong>Duration:</strong> {generation.params.audio_duration}s
              </div>
              <div>
                <strong>Type:</strong> {generation.feature_type}
              </div>
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
