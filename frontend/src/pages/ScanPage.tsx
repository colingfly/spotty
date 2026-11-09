import React, { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import CameraScan from "../components/CameraScan";
import { Section, Thumb } from "../components/ui";
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
  if (!ctx) throw new Error("canvas not supported");
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
  const [source, setSource] = useState<"upload" | "camera">("upload");

  const pick = (f: File | null) => {
    setFile(f);
    setPreview(f ? URL.createObjectURL(f) : null);
  };

  const onResults = (items: ScanArtist[]) => {
    setResults(items);
    setSelected(new Set(items.slice(0, 6).map((a) => a.id)));
  };

  const scan = async () => {
    if (!file) return;
    setScanning(true);
    try {
      const form = new FormData();
      form.append("file", await compressToJpeg(file), "poster.jpg");
      onResults(mapScanResults(await api.post<any>("/api/scan", form)));
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setScanning(false);
    }
  };

  const toggle = (id: string) => setSelected((s) => { const n = new Set(s); if (n.has(id)) n.delete(id); else n.add(id); return n; });
  const chosen = useMemo(() => (results || []).filter((a) => selected.has(a.id)), [results, selected]);

  const makeTrack = () => {
    sessionStorage.setItem(FESTIVAL_KEY, JSON.stringify(chosen.map((a) => a.name)));
    navigate("/studio?mode=festival");
  };

  return (
    <div>
      <h1>scan a flyer</h1>
      <p className="small">tesseract reads the poster, spotify resolves the names, each act is scored against your profile.</p>

      <Section n="01" title="image" right={
        <select value={source} onChange={(e) => setSource(e.target.value as any)} aria-label="source" style={{ width: "auto", minHeight: 36 }}>
          <option value="upload">upload</option>
          <option value="camera">camera</option>
        </select>
      }>
        <div className="cols">
          <div className="box">
            {source === "camera" ? <CameraScan onResults={onResults} /> : (
              <div className="stack">
                <input type="file" accept="image/*" onChange={(e) => pick(e.target.files?.[0] ?? null)} aria-label="poster image" />
                {preview && <figure><img src={preview} alt="selected poster" style={{ aspectRatio: "auto", maxHeight: 400, objectFit: "contain" }} /><figcaption>{file?.name}</figcaption></figure>}
                <div className="actions">
                  <button className="primary" onClick={scan} disabled={!file || scanning}>{scanning ? "reading poster…" : "scan poster"}</button>
                  {file && <button onClick={() => { pick(null); setResults(null); }}>clear</button>}
                </div>
              </div>
            )}
          </div>
          <div className="box small">
            score = 50% name match + 30% genre overlap with your profile + 10% co-occurrence with artists you play + 10% if already in your top artists. acts under 35% are dropped.
          </div>
        </div>
      </Section>

      <Section n="02" title="results" right={results ? `${results.length} acts · ${chosen.length} selected` : undefined}>
        {results === null ? <div className="box">no scan yet.</div> : results.length === 0 ? <div className="box">no artists recognised. try a sharper, straight-on photo.</div> : (
          <>
            <div className="table-wrap">
              <table>
                <thead><tr><th>use</th><th></th><th>artist</th><th className="num">match</th><th className="num">name</th><th className="num">genre</th><th>genres</th><th>read as</th><th>link</th></tr></thead>
                <tbody>
                  {results.map((a) => (
                    <tr key={a.id}>
                      <td><input type="checkbox" checked={selected.has(a.id)} onChange={() => toggle(a.id)} aria-label={`use ${a.name}`} /></td>
                      <td><Thumb src={a.image} alt={a.name} /></td>
                      <td>{a.name}{a.in_library ? <div className="small">in your top artists</div> : null}</td>
                      <td className="num">{a.matchTotal}%</td>
                      <td className="num">{a.nameSim}%</td>
                      <td className="num">{a.genreSim}%</td>
                      <td className="small">{a.genres.slice(0, 3).join(", ")}</td>
                      <td className="small">{a.candidate}</td>
                      <td>{a.external_url ? <a href={a.external_url} target="_blank" rel="noreferrer">spotify</a> : ""}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div style={{ marginTop: 8 }}>
              <button className="primary" onClick={makeTrack} disabled={chosen.length === 0}>make a track from {chosen.length} selected act{chosen.length === 1 ? "" : "s"}</button>
            </div>
          </>
        )}
      </Section>
    </div>
  );
}
