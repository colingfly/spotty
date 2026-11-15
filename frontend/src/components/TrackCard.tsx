import React, { useState } from "react";
import { usePlayer } from "../hooks/usePlayer";
import { api } from "../lib/api";
import { fmtTime, relativeTime } from "../lib/format";
import type { Generation } from "../types";
import { Lyrics, engineLabel, modeLabel } from "./ui";
import Waveform from "./Waveform";

type Props = {
  gen: Generation;
  queue?: Generation[];
  onChange?: (g: Generation) => void;
  onDelete?: (g: Generation) => void;
  onToggleFavorite?: (g: Generation) => void;
  /** Render the same brief again: a fresh take, or the same seed on another model. */
  onRetake?: (g: Generation, opts: { same_seed?: boolean; model?: string }) => void;
  /** Offered as "same take on …" when the track was rendered on a different model. */
  upgradeModel?: { id: string; label: string };
  /** Re-render one time range of the track, optionally with new lyrics for it. */
  onRepaint?: (g: Generation, opts: { start: number; end: number; lyrics?: string }) => Promise<void> | void;
  /** Split the track into vocals, drums, bass and other. */
  onStems?: (g: Generation) => void;
  /** Open this track as a producer project. */
  onProject?: (g: Generation) => void;
  compact?: boolean;
};

export default function TrackCard({ gen, queue, onChange, onDelete, onToggleFavorite, onRetake, upgradeModel, onRepaint, onStems, onProject, compact = false }: Props) {
  const player = usePlayer();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(gen.title || "");
  const [saving, setSaving] = useState(false);
  const length = Math.floor(gen.duration_seconds || 0);
  const [from, setFrom] = useState(0);
  const [to, setTo] = useState(Math.min(15, length));
  const [sectionLyrics, setSectionLyrics] = useState(gen.lyrics && gen.lyrics !== "[Instrumental]" ? gen.lyrics : "");
  const [repainting, setRepainting] = useState(false);
  const sectionOk = to - from >= 2 && from >= 0 && to <= length;
  const edit = (gen.meta as any)?.edit as { start: number; end: number } | undefined;
  const reference = (gen.meta as any)?.reference as { name: string; strength: number } | undefined;

  const isCurrent = player.isCurrent(gen.generation_id);
  const playing = isCurrent && player.playing;
  const ready = gen.status === "completed" && !!gen.audio_url;
  const bpm = (gen.params as any)?.bpm as number | undefined;

  const saveTitle = async () => {
    setSaving(true);
    try {
      const updated = await api.patch<Generation>(`/api/generate/${gen.generation_id}`, { title });
      onChange?.(updated);
      player.updateTrack({ generation_id: gen.generation_id, title: updated.title });
      setEditing(false);
    } finally {
      setSaving(false);
    }
  };

  const progress = isCurrent && player.duration ? player.time / player.duration : 0;
  const meta = [
    modeLabel(gen),
    engineLabel(gen.engine),
    gen.model ? gen.model.replace(/^ace-/, "").replace(/-/g, " ") : null,
    gen.status !== "completed" ? gen.status : null,
    gen.duration_seconds ? fmtTime(gen.duration_seconds) : null,
    bpm ? `${bpm} bpm` : null,
    gen.meta?.key_scale || null,
    relativeTime(gen.created_at),
    gen.play_count > 0 ? `${gen.play_count} play${gen.play_count === 1 ? "" : "s"}` : null,
    gen.is_favorite ? "favorite" : null,
    edit ? `edited ${fmtTime(edit.start)}–${fmtTime(edit.end)}` : null,
    reference ? `follows ${reference.name} at ${Math.round(reference.strength * 100)}%` : null,
    !compact && typeof (gen.params as any)?.seed === "number" ? `seed ${(gen.params as any).seed}` : null,
  ].filter(Boolean).join(" · ");

  return (
    <div className={`track ${isCurrent ? "current" : ""}`}>
      {editing ? (
        <div className="row">
          <input value={title} autoFocus maxLength={80} style={{ flex: 1, minWidth: 200 }} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void saveTitle(); if (e.key === "Escape") setEditing(false); }} aria-label="title" />
          <div className="actions">
            <button className="primary" onClick={() => void saveTitle()} disabled={saving}>save</button>
            <button onClick={() => setEditing(false)}>cancel</button>
          </div>
        </div>
      ) : (
        <div className="b break">{playing ? "playing: " : ""}{gen.title || gen.caption?.split(",")[0] || "untitled"}</div>
      )}
      <div className="small">{meta}</div>
      {gen.status === "failed" && gen.error && <div className="small">error: {gen.error}</div>}

      {ready && (
        <Waveform peaks={gen.waveform} progress={progress} onSeek={(f) => { if (!isCurrent) player.play(gen, queue); if (player.duration) player.seek(f * player.duration); }} />
      )}

      {compact && ready && <button onClick={() => player.play(gen, queue)}>{playing ? "pause" : "play"}</button>}

      {!compact && (
        <>
          <div className="actions" style={{ marginTop: 6 }}>
            {ready && <button onClick={() => player.play(gen, queue)}>{playing ? "pause" : "play"}</button>}
            {onToggleFavorite && <button aria-pressed={gen.is_favorite} onClick={() => onToggleFavorite(gen)}>{gen.is_favorite ? "unfavorite" : "favorite"}</button>}
            {onChange && !editing && <button onClick={() => { setTitle(gen.title || ""); setEditing(true); }}>rename</button>}
            {onRetake && ready && <button onClick={() => onRetake(gen, {})}>new take</button>}
            {onRetake && ready && upgradeModel && gen.model !== upgradeModel.id && (
              <button onClick={() => onRetake(gen, { same_seed: true, model: upgradeModel.id })}>same take on {upgradeModel.label}</button>
            )}
            {gen.download_url && <a className="btn" href={api.url(gen.download_url)} download>download mp3</a>}
            {onStems && ready && (!gen.stems || gen.stems.status === "failed") && <button onClick={() => onStems(gen)}>{gen.stems ? "retry stems" : "stems"}</button>}
            {onProject && ready && <button onClick={() => onProject(gen)}>{gen.project_id ? "open project" : "open in producer"}</button>}
            {onDelete && <button onClick={() => onDelete(gen)}>delete</button>}
          </div>
          {gen.stems?.status === "processing" && <p className="small" role="status">separating stems… this takes up to a minute if the service is asleep.</p>}
          {gen.stems?.status === "failed" && <p className="small">stems failed: {gen.stems.error || "unknown error"}</p>}
          {gen.stems?.status === "ready" && gen.stems.files && (
            <div style={{ marginTop: 8 }}>
              <span className="label">stems · wav, 44.1 khz</span>
              <div className="actions">
                {["vocals", "drums", "bass", "other"].filter((n) => gen.stems!.files![n]).map((n) => (
                  <a key={n} className="btn" href={api.url(gen.stems!.files![n])} download>{n}</a>
                ))}
                {gen.stems.zip && <a className="btn" href={api.url(gen.stems.zip)} download>all + mix (.zip)</a>}
              </div>
            </div>
          )}
          {onRepaint && ready && length >= 4 && (
            <details style={{ marginTop: 8 }}>
              <summary>edit a section</summary>
              <p className="small">re-renders only the chosen range and keeps the rest of the track. the result is saved as a new track.</p>
              <div className="row">
                <label className="field"><span className="label">from · {fmtTime(from)}</span>
                  <input type="number" min={0} max={Math.max(0, length - 2)} step={1} value={from} onChange={(e) => setFrom(Number(e.target.value))} style={{ width: 90 }} />
                </label>
                <label className="field"><span className="label">to · {fmtTime(to)}</span>
                  <input type="number" min={2} max={length} step={1} value={to} onChange={(e) => setTo(Number(e.target.value))} style={{ width: 90 }} />
                </label>
              </div>
              <label className="field"><span className="label">lyrics for the new version (optional)</span>
                <textarea rows={4} value={sectionLyrics} maxLength={4096} onChange={(e) => setSectionLyrics(e.target.value)} />
              </label>
              <div className="actions">
                <button className="primary" disabled={!sectionOk || repainting} onClick={async () => {
                  setRepainting(true);
                  try { await onRepaint(gen, { start: from, end: to, lyrics: sectionLyrics.trim() || undefined }); } finally { setRepainting(false); }
                }}>{repainting ? "submitting…" : `re-render ${fmtTime(from)}–${fmtTime(to)}`}</button>
              </div>
              {!sectionOk && <p className="small">pick a range of at least 2 seconds inside 0:00–{fmtTime(length)}.</p>}
            </details>
          )}
          {(gen.caption || (gen.lyrics && gen.lyrics !== "[Instrumental]")) && (
            <details style={{ marginTop: 8 }}>
              <summary>brief</summary>
              {gen.caption && <div className="break"><span className="label">caption</span><br />{gen.caption}</div>}
              {gen.lyrics && gen.lyrics !== "[Instrumental]" && <div><span className="label">lyrics</span><Lyrics text={gen.lyrics} /></div>}
              {gen.meta?.rationale && <div className="small">{gen.meta.rationale}</div>}
            </details>
          )}
        </>
      )}
    </div>
  );
}
