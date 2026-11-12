import React, { useMemo, useState } from "react";
import type { AudioFeatureKey, Features } from "../types";
import { AUDIO_FEATURES, FEATURE_LABELS } from "../types";

type Props = {
  features: Partial<Features> | null;
  overrides?: Partial<Features>;
  size?: number;
  interactive?: boolean;
  onChange?: (key: AudioFeatureKey, value: number) => void;
  compareTo?: Partial<Features> | null;
};

const norm = (key: AudioFeatureKey, v: number | undefined) => {
  if (v === undefined || v === null || isNaN(v)) return 0;
  return key === "tempo" ? Math.min(1, Math.max(0, (v - 40) / 180)) : Math.min(1, Math.max(0, v));
};
const denorm = (key: AudioFeatureKey, n: number) => (key === "tempo" ? Math.round(40 + n * 180) : Math.round(n * 100) / 100);

export default function TasteRadar({ features, overrides, size = 280, interactive = false, onChange, compareTo }: Props) {
  const PAD = 70; // horizontal room for the left and right axis labels
  const width = size + PAD * 2;
  const cx = width / 2;
  const cy = size / 2;
  const maxR = size / 2 - 48;
  const n = AUDIO_FEATURES.length;
  const [drag, setDrag] = useState<AudioFeatureKey | null>(null);

  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pt = (i: number, r: number) => ({ x: cx + r * Math.cos(angle(i)), y: cy + r * Math.sin(angle(i)) });

  const values = useMemo(() => AUDIO_FEATURES.map((k) => norm(k, overrides?.[k] ?? features?.[k])), [features, overrides]);
  const ghost = useMemo(() => (compareTo ? AUDIO_FEATURES.map((k) => norm(k, compareTo[k])) : null), [compareTo]);
  const poly = (vals: number[]) => vals.map((v, i) => { const p = pt(i, v * maxR); return `${p.x},${p.y}`; }).join(" ");

  const setFromPointer = (key: AudioFeatureKey, e: React.PointerEvent<SVGSVGElement>) => {
    if (!onChange) return;
    const rect = e.currentTarget.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) / rect.width) * width;
    const sy = ((e.clientY - rect.top) / rect.height) * size;
    const i = AUDIO_FEATURES.indexOf(key);
    const proj = (sx - cx) * Math.cos(angle(i)) + (sy - cy) * Math.sin(angle(i));
    onChange(key, denorm(key, Math.max(0, Math.min(1, proj / maxR))));
  };

  return (
    <svg
      className="radar"
      width={width}
      height={size}
      viewBox={`0 0 ${width} ${size}`}
      style={{ display: "block", maxWidth: "100%", height: "auto", touchAction: "none", userSelect: "none" }}
      onPointerMove={(e) => drag && setFromPointer(drag, e)}
      onPointerUp={() => setDrag(null)}
      onPointerLeave={() => setDrag(null)}
      role="img"
      aria-label="taste radar"
    >
      {[0.5, 1].map((ring) => (
        <polygon key={ring} points={poly(AUDIO_FEATURES.map(() => ring))} fill="none" stroke="#fff" strokeWidth={1} />
      ))}
      {AUDIO_FEATURES.map((_, i) => {
        const p = pt(i, maxR);
        return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="#fff" strokeWidth={1} />;
      })}
      {ghost && <polygon points={poly(ghost)} fill="none" stroke="#fff" strokeDasharray="3 3" strokeWidth={1} />}
      <polygon points={poly(values)} fill="none" stroke="#c9a7ff" strokeWidth={2} strokeLinejoin="miter" />
      {values.map((v, i) => {
        const p = pt(i, v * maxR);
        const key = AUDIO_FEATURES[i];
        return (
          <g key={key}>
            {interactive && <rect x={p.x - 16} y={p.y - 16} width={32} height={32} fill="transparent" style={{ cursor: "grab" }} onPointerDown={(e) => { (e.target as Element).setPointerCapture?.(e.pointerId); setDrag(key); }} />}
            <rect x={p.x - 4} y={p.y - 4} width={8} height={8} fill="#c9a7ff" style={{ pointerEvents: "none" }} />
          </g>
        );
      })}
      {AUDIO_FEATURES.map((key, i) => {
        const c = Math.cos(angle(i));
        const side = Math.abs(c) > 0.3; // labels left or right of the chart hang off the axis end
        const p = pt(i, maxR + (side ? 10 : 22));
        const anchor = !side ? "middle" : c > 0 ? "start" : "end";
        const raw = overrides?.[key] ?? features?.[key];
        const val = raw === undefined || raw === null ? "–" : key === "tempo" ? `${Math.round(raw)}` : `${Math.round(raw * 100)}`;
        return (
          <text key={key} x={p.x} y={p.y} textAnchor={anchor} dominantBaseline="middle">
            {FEATURE_LABELS[key].toLowerCase()} {val}
          </text>
        );
      })}
    </svg>
  );
}
