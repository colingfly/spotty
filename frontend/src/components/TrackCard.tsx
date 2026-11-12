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
  compact?: boolean;
};

export default function TrackCard({ gen, queue, onChange, onDelete, onToggleFavorite, compact = false }: Props) {
  const player = usePlayer();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(gen.title || "");
  const [saving, setSaving] = useState(false);

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
    gen.status !== "completed" ? gen.status : null,
    gen.duration_seconds ? fmtTime(gen.duration_seconds) : null,
    bpm ? `${bpm} bpm` : null,
    gen.meta?.key_scale || null,
    relativeTime(gen.created_at),
    gen.play_count > 0 ? `${gen.play_count} play${gen.play_count === 1 ? "" : "s"}` : null,
    gen.is_favorite ? "favorite" : null,
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
            {gen.download_url && <a className="btn" href={api.url(gen.download_url)} download>download mp3</a>}
            {onDelete && <button onClick={() => onDelete(gen)}>delete</button>}
          </div>
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
