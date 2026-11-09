import React from "react";
import { usePlayer } from "../hooks/usePlayer";
import { api } from "../lib/api";
import { fmtTime } from "../lib/format";
import { engineLabel, modeLabel } from "./ui";
import Waveform from "./Waveform";

export default function PlayerBar() {
  const p = usePlayer();
  if (!p.current) return null;
  const t = p.current;
  const progress = p.duration ? p.time / p.duration : 0;
  const idx = p.queue.findIndex((q) => q.generation_id === t.generation_id);

  return (
    <div className="player" role="region" aria-label="player">
      <div style={{ minWidth: 0 }}>
        <div className="b break">{t.title || "untitled"}</div>
        <div className="small">{modeLabel(t)} · {engineLabel(t.engine)}{p.queue.length > 1 ? ` · ${idx + 1}/${p.queue.length}` : ""}</div>
      </div>
      <div className="stack" style={{ gap: 4 }}>
        <div className="row" style={{ gap: 0 }}>
          <div className="actions">
            <button onClick={p.prev} disabled={idx <= 0}>prev</button>
            <button className="primary" onClick={p.toggle}>{p.playing ? "pause" : "play"}</button>
            <button onClick={p.next} disabled={idx < 0 || idx >= p.queue.length - 1}>next</button>
          </div>
          <span className="time" style={{ marginLeft: 12 }}>{fmtTime(p.time)} / {fmtTime(p.duration || t.duration_seconds)}</span>
        </div>
        <Waveform peaks={t.waveform} progress={progress} onSeek={(f) => p.seek(f * (p.duration || t.duration_seconds || 0))} bars={72} />
      </div>
      <div className="row vol">
        {t.download_url && <a href={api.url(t.download_url)} download>download</a>}
        <label className="small" style={{ display: "flex", alignItems: "center", gap: 6 }}>
          vol
          <input type="range" min={0} max={100} value={Math.round(p.volume * 100)} onChange={(e) => p.setVolume(Number(e.target.value) / 100)} aria-label="volume" />
        </label>
      </div>
    </div>
  );
}
