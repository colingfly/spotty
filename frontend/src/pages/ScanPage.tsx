import React, { useState } from "react";
import { API_BASE } from "../config";
import type { Artist } from "../types";

type Props = { sid: string };

async function compressToJpeg(
  file: File,
  maxDim = 1600,
  quality = 0.9
): Promise<Blob> {
  if (!file.type.startsWith("image/")) return file;
  const img = await createImageBitmap(file);
  const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
  const w = Math.round(img.width * scale);
  const h = Math.round(img.height * scale);
  const canvas = document.createElement("canvas");
  canvas.width = w;
  canvas.height = h;
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported");
  ctx.drawImage(img, 0, 0, w, h);
  return new Promise((resolve, reject) =>
    canvas.toBlob(
      (b) => (b ? resolve(b) : reject(new Error("toBlob failed"))),
      "image/jpeg",
      quality
    )
  );
}

export default function ScanPage({ sid }: Props) {
  const [selFile, setSelFile] = useState<File | null>(null);
  const [scanning, setScanning] = useState(false);
  const [artists, setArtists] = useState<Artist[]>([]);
  const [error, setError] = useState<string | null>(null);

  const handleScan = async () => {
    if (!selFile) return;
    setScanning(true);
    setError(null);
    try {
      const payload = await compressToJpeg(selFile);
      const form = new FormData();
      form.append("spotify_user_id", sid);
      form.append("file", payload, "poster.jpg");

      const res = await fetch(`${API_BASE}/api/scan`, {
        method: "POST",
        body: form,
      });
      const data = await res.json();

      if (!res.ok) {
        setError(
          data?.message ||
            (data?.error === "ocr_unavailable"
              ? "OCR is unavailable on the server."
              : `Scan failed (HTTP ${res.status})`)
        );
        return;
      }

      const items: Artist[] = (data.items || []).map((x: any) => ({
        id: x.spotify_artist_id,
        name: x.resolved_name,
        genres: x.genres || [],
        image: x.image,
        external_url: x.external_url,
        popularity: x.popularity ?? undefined,
        matchTotal: Math.round((x.scores?.total ?? 0) * 100),
        nameSim: Math.round(x.scores?.name ?? 0),
        genreSim: Math.round((x.scores?.genre ?? 0) * 100),
        fromScan: true,
      }));
      items.sort((a, b) => (b.matchTotal ?? 0) - (a.matchTotal ?? 0));
      setArtists(items);
      setSelFile(null);
    } catch (e: any) {
      setError(e?.message || "Scan failed.");
    } finally {
      setScanning(false);
    }
  };

  return (
    <div>
      <h2 style={{ fontSize: 32, marginBottom: 4 }}>Poster Scanner</h2>
      <p style={{ color: "#888", marginBottom: 24 }}>
        Scan a concert poster to find artists that match your taste
      </p>

      <div
        style={{
          display: "flex",
          gap: 12,
          alignItems: "center",
          marginBottom: 16,
          flexWrap: "wrap",
        }}
      >
        <input
          type="file"
          accept="image/*"
          capture="environment"
          onChange={(e) => setSelFile(e.target.files?.[0] ?? null)}
          style={{ color: "#ccc" }}
        />
        <button
          onClick={handleScan}
          disabled={!selFile || scanning}
          style={{
            padding: "8px 16px",
            background: selFile && !scanning ? "#1db954" : "#333",
            color: "white",
            border: "none",
            borderRadius: 8,
            cursor: selFile && !scanning ? "pointer" : "not-allowed",
          }}
        >
          {scanning ? "Scanning..." : "Scan Image"}
        </button>
      </div>

      {error && (
        <div style={{ color: "#ff4444", marginBottom: 12 }}>{error}</div>
      )}

      {artists.length === 0 && !error && (
        <div style={{ color: "#555" }}>
          Upload a poster image to scan for artists.
        </div>
      )}

      <div
        style={{
          display: "grid",
          gridTemplateColumns: "repeat(auto-fill, minmax(240px, 1fr))",
          gap: 12,
          marginTop: 16,
        }}
      >
        {artists.map((a) => (
          <div
            key={a.id}
            style={{
              background: "#1a1a1a",
              borderRadius: 10,
              padding: 12,
            }}
          >
            <img
              src={a.image || "https://via.placeholder.com/300x300?text=?"}
              alt={a.name}
              style={{
                width: "100%",
                height: 200,
                objectFit: "cover",
                borderRadius: 8,
              }}
            />
            <h3 style={{ margin: "10px 0 4px", fontSize: 16 }}>{a.name}</h3>
            <div style={{ fontSize: 12, color: "#888" }}>
              {a.genres?.slice(0, 3).join(", ")}
            </div>
            <div style={{ fontSize: 12, color: "#aaa", marginTop: 6, lineHeight: 1.6 }}>
              <div>
                <strong>Match:</strong> {a.matchTotal ?? "—"}%
              </div>
              <div>
                <strong>Name:</strong> {a.nameSim ?? "—"}% ·{" "}
                <strong>Genre:</strong> {a.genreSim ?? "—"}%
              </div>
            </div>
            <a
              href={a.external_url || "#"}
              target="_blank"
              rel="noreferrer"
              style={{
                display: "inline-block",
                marginTop: 8,
                fontSize: 12,
                color: "#1db954",
              }}
            >
              Open in Spotify
            </a>
          </div>
        ))}
      </div>
    </div>
  );
}
