import React, { useMemo } from "react";

type Props = {
  peaks: number[] | null | undefined;
  progress?: number; // 0..1
  onSeek?: (fraction: number) => void;
  bars?: number;
  className?: string;
};

const FLAT = Array.from({ length: 48 }, () => 0.5);

export default function Waveform({ peaks, progress = 0, onSeek, bars = 48, className }: Props) {
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

  const handle = (e: React.MouseEvent<HTMLDivElement>) => {
    if (!onSeek) return;
    const rect = e.currentTarget.getBoundingClientRect();
    onSeek(Math.max(0, Math.min(1, (e.clientX - rect.left) / rect.width)));
  };

  return (
    <div className={`wave ${className || ""}`} onClick={handle} role={onSeek ? "slider" : undefined} aria-label={onSeek ? "seek" : undefined} aria-valuenow={Math.round(progress * 100)}>
      {data.map((v, i) => (
        <span key={i} className={i / data.length < progress ? "played" : ""} style={{ height: `${Math.max(6, v * 100)}%` }} />
      ))}
    </div>
  );
}
