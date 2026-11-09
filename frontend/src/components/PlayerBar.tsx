import React from "react";
import { Download, Pause, Play, SkipBack, SkipForward, Volume2, VolumeX } from "lucide-react";
import { usePlayer } from "../hooks/usePlayer";
import { api } from "../lib/api";
import { fmtTime } from "../lib/format";
import { EngineBadge, ModeBadge, modeOf } from "./ui";
import Waveform from "./Waveform";

export default function PlayerBar() {
  const p = usePlayer();
  if (!p.current) return null;
  const t = p.current;
  const progress = p.duration ? p.time / p.duration : 0;
  const idx = p.queue.findIndex((q) => q.generation_id === t.generation_id);

  return (
    <div className="player">
      <div className="container player-inner">
        <div style={{ minWidth: 0 }}>
          <div className="player-title truncate">{t.title || "Untitled"}</div>
          <div className="player-sub row" style={{ gap: 6 }}>
            <ModeBadge mode={modeOf(t)} />
            <EngineBadge engine={t.engine} compact />
            {p.queue.length > 1 && <span>{idx + 1} / {p.queue.length}</span>}
          </div>
        </div>

        <div className="player-center">
          <div className="player-controls">
            <button className="btn btn-icon btn-ghost" onClick={p.prev} disabled={idx <= 0} aria-label="Previous"><SkipBack size={18} /></button>
            <button className="btn btn-round btn-primary" onClick={p.toggle} aria-label={p.playing ? "Pause" : "Play"}>
              {p.playing ? <Pause size={20} fill="currentColor" /> : <Play size={20} fill="currentColor" style={{ marginLeft: 2 }} />}
            </button>
            <button className="btn btn-icon btn-ghost" onClick={p.next} disabled={idx < 0 || idx >= p.queue.length - 1} aria-label="Next"><SkipForward size={18} /></button>
          </div>
          <div className="player-scrub">
            <span style={{ textAlign: "right" }}>{fmtTime(p.time)}</span>
            <div style={{ height: 26 }}>
              <Waveform peaks={t.waveform} progress={progress} onSeek={(f) => p.seek(f * (p.duration || t.duration_seconds || 0))} bars={72} />
            </div>
            <span>{fmtTime(p.duration || t.duration_seconds)}</span>
          </div>
        </div>

        <div className="player-right">
          {t.download_url && (
            <a className="btn btn-icon btn-ghost" href={api.url(t.download_url)} download aria-label="Download" title="Download MP3"><Download size={16} /></a>
          )}
          <button className="btn btn-icon btn-ghost" onClick={() => p.setVolume(p.volume === 0 ? 0.9 : 0)} aria-label="Mute">
            {p.volume === 0 ? <VolumeX size={16} /> : <Volume2 size={16} />}
          </button>
          <input className="range volume" type="range" min={0} max={100} value={Math.round(p.volume * 100)} onChange={(e) => p.setVolume(Number(e.target.value) / 100)} style={{ ["--p" as any]: `${p.volume * 100}%` }} aria-label="Volume" />
        </div>
      </div>
    </div>
  );
}
