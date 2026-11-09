import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { Camera, Check, ExternalLink, Sparkles, Upload } from "lucide-react";
import CameraScan from "../components/CameraScan";
import { EmptyState, PlaceholderArt } from "../components/ui";
import { useToast } from "../hooks/useToast";
import { api } from "../lib/api";
import type { ScanArtist } from "../types";

export const FESTIVAL_KEY = "trill.festival";

async function compressToJpeg(file: File, maxDim = 1600, quality = 0.9): Promise<Blob> {
  if (!file.type.startsWith("image/")) return file;
  const img = await createImageBitmap(file);
  const scale = Math.min(1, maxDim / Math.max(img.width, img.height));
  const canvas = document.createElement("canvas");
  canvas.width = Math.round(img.width * scale);
  canvas.height = Math.round(img.height * scale);
  const ctx = canvas.getContext("2d");
  if (!ctx) throw new Error("Canvas not supported");
  ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
  return new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("toBlob failed"))), "image/jpeg", quality));
}

export function mapScanResults(data: any): ScanArtist[] {
  return ((data?.items || []) as any[]).map((x) => ({
    id: x.spotify_artist_id,
    name: x.resolved_name,
    candidate: x.candidate,
    genres: x.genres || [],
    image: x.image,
    external_url: x.external_url,
    popularity: x.popularity ?? null,
    in_library: !!x.in_library,
    matchTotal: Math.round((x.scores?.total ?? 0) * 100),
    nameSim: Math.round(x.scores?.name ?? 0),
    genreSim: Math.round((x.scores?.genre ?? 0) * 100),
  }));
}

export default function ScanPage() {
  const toast = useToast();
  const navigate = useNavigate();
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState<string | null>(null);
  const [scanning, setScanning] = useState(false);
  const [results, setResults] = useState<ScanArtist[] | null>(null);
  const [selected, setSelected] = useState<Set<string>>(new Set());
  const [useCamera, setUseCamera] = useState(false);

  const pick = (f: File | null) => {
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const onResults = (items: ScanArtist[]) => {
    setResults(items);
    setSelected(new Set(items.slice(0, 6).map((a) => a.id)));
    if (items.length === 0) toast.info("No artists recognised. Try a sharper, straight-on photo.");
  };

  const scan = async () => {
    if (!file) return;
    setScanning(true);
    try {
      const form = new FormData();
      form.append("file", await compressToJpeg(file), "poster.jpg");
      const data = await api.post<any>("/api/scan", form);
      onResults(mapScanResults(data));
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setScanning(false);
    }
  };

  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });

  const chosen = useMemo(() => (results || []).filter((a) => selected.has(a.id)), [results, selected]);

  const makeTrack = () => {
    sessionStorage.setItem(FESTIVAL_KEY, JSON.stringify(chosen.map((a) => a.name)));
    navigate("/studio?mode=festival");
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Poster scanner</h1>
          <p className="page-sub">see a flyer on a pole. point your phone at it. trill reads the names, finds them on Spotify and scores each against what you already play.</p>
        </div>
        <div className="segmented">
          <button className={!useCamera ? "active" : ""} onClick={() => setUseCamera(false)}><Upload size={14} style={{ verticalAlign: -2 }} /> Upload</button>
          <button className={useCamera ? "active" : ""} onClick={() => setUseCamera(true)}><Camera size={14} style={{ verticalAlign: -2 }} /> Camera</button>
        </div>
      </div>

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 2fr) minmax(0, 3fr)" }}>
        <div className="card">
          {useCamera ? (
            <CameraScan onResults={onResults} />
          ) : (
            <div className="stack">
              <label className="empty" style={{ cursor: "pointer", padding: preview ? 0 : undefined, overflow: "hidden" }}>
                {preview ? <img src={preview} alt="Poster preview" style={{ width: "100%", maxHeight: 360, objectFit: "contain", borderRadius: 18 }} /> : (
                  <>
                    <Upload size={22} style={{ margin: "0 auto 8px" }} />
                    <h3>Drop a poster or click to choose</h3>
                    <p className="small">JPG, PNG or HEIC. Fill the frame with the text, avoid glare.</p>
                  </>
                )}
                <input type="file" accept="image/*" style={{ display: "none" }} onChange={(e) => pick(e.target.files?.[0] ?? null)} />
              </label>
              <div className="row">
                <button className="btn btn-primary" onClick={scan} disabled={!file || scanning}>
                  {scanning ? <span className="spinner" /> : <Sparkles size={15} />} {scanning ? "Reading poster…" : "Scan poster"}
                </button>
                {file && <button className="btn btn-ghost" onClick={() => { pick(null); setResults(null); }}>Clear</button>}
              </div>
            </div>
          )}
        </div>

        <div className="stack">
          {results === null ? (
            <EmptyState title="Results appear here" body="Each recognised act gets a match score from name confidence, genre overlap with your profile and who you already listen to." />
          ) : results.length === 0 ? (
            <EmptyState title="No artists found" body="The OCR didn't pick out any names. Try a higher-resolution photo." />
          ) : (
            <>
              <div className="card card-sm row between">
                <div>
                  <div style={{ fontWeight: 700 }}>{results.length} acts recognised · {chosen.length} selected</div>
                  <div className="tiny dim">Select the acts you'd see, then build a track from the night.</div>
                </div>
                <button className="btn btn-ai" onClick={makeTrack} disabled={chosen.length === 0}><Sparkles size={15} /> Make a festival track</button>
              </div>
              <div className="grid grid-auto" style={{ gap: 10 }}>
                {results.map((a) => {
                  const on = selected.has(a.id);
                  return (
                    <div key={a.id} className={`artist-tile selectable ${on ? "selected" : ""}`} onClick={() => toggle(a.id)} role="checkbox" aria-checked={on}>
                      {a.image ? <img src={a.image} alt={a.name} loading="lazy" /> : <PlaceholderArt size={28} />}
                      {on && <span className="check"><Check size={14} /></span>}
                      <span className="rank">{a.matchTotal}% match</span>
                      <div className="overlay">
                        <div className="name truncate">{a.name}</div>
                        <div className="genres truncate">{a.in_library ? "In your top artists · " : ""}{a.genres.slice(0, 2).join(", ")}</div>
                        <a className="tiny" href={a.external_url || "#"} target="_blank" rel="noreferrer" onClick={(e) => e.stopPropagation()} style={{ marginTop: 4, display: "inline-flex", gap: 4, alignItems: "center" }}>
                          Spotify <ExternalLink size={10} />
                        </a>
                      </div>
                    </div>
                  );
                })}
              </div>
            </>
          )}
        </div>
      </div>
    </div>
  );
}
