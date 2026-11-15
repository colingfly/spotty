import React, { useMemo, useRef } from "react";

type Props = {
  peaks: number[] | null | undefined;
  progress?: number; // 0..1
  onSeek?: (fraction: number) => void;
  /** Selected range as fractions of the track; bars inside it are highlighted. */
  selection?: { from: number; to: number };
  /** Drag across the waveform to choose a range. Replaces click-to-seek on this instance. */
  onSelect?: (from: number, to: number) => void;
  bars?: number;
  className?: string;
};

const FLAT = Array.from({ length: 48 }, () => 0.5);

export default function Waveform({ peaks, progress = 0, onSeek, selection, onSelect, bars = 48, className }: Props) {
  const data = useMemo(() => {
    const src = peaks && peaks.length ? peaks : FLAT;
    if (src.length === bars) return src;
    const out: number[] = [];
    for (let i = 0; i < bars; i++) {
      const a = Math.floor((i / bars) * src.length);
      const b = Math.max(a + 1, Math.floor(((i + 1) / bars) * src.length));
      let m = 0;
      for (let j = a; j < b && j < src.length; j++) m = Math.max(m, src[j]);
      out.push(m);
    }
    return out;
  }, [peaks, bars]);

  const anchor = useRef<number | null>(null);
  const fraction = (e: React.PointerEvent<HTMLDivElement>) => {
    const rect = e.currentTarget.getBoundingClientRect();
    return Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width));
  };
  const drag = onSelect ? {
    onPointerDown: (e: React.PointerEvent<HTMLDivElement>) => {
      anchor.current = fraction(e);
      e.currentTarget.setPointerCapture(e.pointerId);
      onSelect(anchor.current, anchor.current);
    },
    onPointerMove: (e: React.PointerEvent<HTMLDivElement>) => {
      if (anchor.current === null) return;
      const f = fraction(e);
      onSelect(Math.min(anchor.current, f), Math.max(anchor.current, f));
    },
    onPointerUp: () => { anchor.current = null; },
    onPointerCancel: () => { anchor.current = null; },
  } : {};

  const handle = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSeek) return;
    const rect = e.currentTarget.getBoundingClientRect();
    onSeek(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)));
  };

  return (
    <div className={`wave ${onSelect ? "selectable" : ""} ${className || ""}`} onClick={onSelect ? undefined : handle} {...drag}
      role={onSeek && !onSelect ? "slider" : undefined} aria-label={onSelect ? "drag to choose a section" : onSeek ? "seek" : undefined} aria-valuenow={Math.round(progress * 100)}>
      {data.map((v, i) => {
        const at = (i + 0.5) / data.length;
        const picked = selection && at >= selection.from && at <= selection.to;
        return <span key={i} className={picked ? "picked" : i / data.length < progress ? "played" : ""} style={{ height: `${Math.max(6, v * 100)}%` }} />;
      })}
    </div>
  );
}
