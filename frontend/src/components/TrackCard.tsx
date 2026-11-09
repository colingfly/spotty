import React, { useState } from "react";
import { Check, Download, Heart, Loader2, Pause, Pencil, Play, Trash2, X } from "lucide-react";
import { usePlayer } from "../hooks/usePlayer";
import { api } from "../lib/api";
import { fmtTime, relativeTime } from "../lib/format";
import type { Generation } from "../types";
import { EngineBadge, Eq, ModeBadge, PlaceholderArt, StatusBadge, modeOf } from "./ui";
import Waveform from "./Waveform";

type Props = {
  gen: Generation;
  queue?: Generation[];
  onChange?: (g: Generation) => void;
  onDelete?: (g: Generation) => void;
  onToggleFavorite?: (g: Generation) => void;
  showCaption?: boolean;
  compact?: boolean;
};

export default function TrackCard({ gen, queue, onChange, onDelete, onToggleFavorite, showCaption = true, compact = false }: Props) {
  const player = usePlayer();
  const [editing, setEditing] = useState(false);
  const [title, setTitle] = useState(gen.title || "");
  const [saving, setSaving] = useState(false);

  const isCurrent = player.isCurrent(gen.generation_id);
  const playing = isCurrent && player.playing;
  const ready = gen.status === "completed" && !!gen.audio_url;
  const active = gen.status === "pending" || gen.status === "processing";
  const mode = modeOf(gen);

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

  return (
    <div className={`card card-sm card-hover track-card ${isCurrent ? "is-playing" : ""}`}>
      <div className="track-art">
        {ready ? (
          <>
            <PlaceholderArt size={22} />
            <button className={`play-overlay ${isCurrent ? "show" : ""}`} onClick={() => player.play(gen, queue)} aria-label={playing ? "Pause" : "Play"}>
              {playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" />}
            </button>
          </>
        ) : active ? (
          <Loader2 size={20} className="muted" style={{ animation: "spin 1s linear infinite" }} />
        ) : (
          <PlaceholderArt size={22} />
        )}
      </div>

      <div style={{ minWidth: 0 }}>
        <div className="row" style={{ gap: 8, alignItems: "flex-start" }}>
          <div style={{ minWidth: 0, flex: 1 }}>
            {editing ? (
              <div className="row" style={{ gap: 6 }}>
                <input className="inline-edit" value={title} autoFocus maxLength={80} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void saveTitle(); if (e.key === "Escape") setEditing(false); }} />
                <button className="btn btn-icon btn-sm btn-primary" onClick={() => void saveTitle()} disabled={saving} aria-label="Save"><Check size={14} /></button>
                <button className="btn btn-icon btn-sm btn-ghost" onClick={() => setEditing(false)} aria-label="Cancel"><X size={14} /></button>
              </div>
            ) : (
              <div className="track-title truncate" title={gen.title || undefined}>
                {playing && <Eq />} {playing && " "}
                {gen.title || gen.caption?.split(",")[0] || "Untitled"}
              </div>
            )}
            <div className="track-meta">
              <ModeBadge mode={mode} />
              <EngineBadge engine={gen.engine} compact />
              {gen.status !== "completed" && <StatusBadge status={gen.status} />}
              {gen.duration_seconds ? <span>{fmtTime(gen.duration_seconds)}</span> : null}
              {gen.params && (gen.params as any).bpm ? <span>{(gen.params as any).bpm} BPM</span> : null}
              {gen.meta?.key_scale ? <span>{gen.meta.key_scale}</span> : null}
              <span>{relativeTime(gen.created_at)}</span>
              {gen.play_count > 0 && <span>{gen.play_count} play{gen.play_count === 1 ? "" : "s"}</span>}
            </div>
          </div>
        </div>

        {gen.status === "failed" && gen.error && <div className="tiny" style={{ color: "var(--rose)", marginTop: 6 }}>{gen.error}</div>}

        {showCaption && gen.caption && !compact && <div className="track-caption">{gen.caption}</div>}

        {ready && (
          <div className="track-wave">
            <Waveform peaks={gen.waveform} progress={progress} onSeek={(f) => { if (!isCurrent) player.play(gen, queue); if (player.duration) player.seek(f * player.duration); }} variant={isCurrent ? "accent" : "static"} />
          </div>
        )}

        {!compact && (
          <div className="track-actions">
            {ready && (
              <button className="btn btn-sm btn-secondary" onClick={() => player.play(gen, queue)}>
                {playing ? <Pause size={14} /> : <Play size={14} />} {playing ? "Pause" : "Play"}
              </button>
            )}
            {onToggleFavorite && (
              <button className="btn btn-icon btn-sm btn-ghost" onClick={() => onToggleFavorite(gen)} aria-label="Favorite" title="Favorite" style={{ color: gen.is_favorite ? "var(--accent)" : undefined }}>
                <Heart size={15} fill={gen.is_favorite ? "currentColor" : "none"} />
              </button>
            )}
            {onChange && !editing && (
              <button className="btn btn-icon btn-sm btn-ghost" onClick={() => { setTitle(gen.title || ""); setEditing(true); }} aria-label="Rename" title="Rename"><Pencil size={15} /></button>
            )}
            {gen.download_url && (
              <a className="btn btn-icon btn-sm btn-ghost" href={api.url(gen.download_url)} download aria-label="Download" title="Download MP3"><Download size={15} /></a>
            )}
            <span className="spacer" />
            {onDelete && (
              <button className="btn btn-icon btn-sm btn-ghost" onClick={() => onDelete(gen)} aria-label="Delete" title="Delete" style={{ color: "var(--text-3)" }}><Trash2 size={15} /></button>
            )}
          </div>
        )}
      </div>
    </div>
  );
}
