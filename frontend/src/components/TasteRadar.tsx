import React, { useMemo, useState } from "react";
import type { AudioFeatureKey, Features } from "../types";
import { AUDIO_FEATURES, FEATURE_LABELS } from "../types";

type Props = {
  features: Partial<Features> | null;
  overrides?: Partial<Features>;
  size?: number;
  interactive?: boolean;
  onChange?: (key: AudioFeatureKey, value: number) => void;
  compareTo?: Partial<Features> | null; // ghost polygon (e.g. baseline while editing)
};

const norm = (key: AudioFeatureKey, v: number | undefined) => {
  if (v === undefined || v === null || isNaN(v)) return 0;
  return key === "tempo" ? Math.min(1, Math.max(0, (v - 40) / 180)) : Math.min(1, Math.max(0, v));
};
const denorm = (key: AudioFeatureKey, n: number) => (key === "tempo" ? Math.round(40 + n * 180) : Math.round(n * 100) / 100);

export default function TasteRadar({ features, overrides, size = 280, interactive = false, onChange, compareTo }: Props) {
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size / 2 - 44;
  const n = AUDIO_FEATURES.length;
  const [drag, setDrag] = useState<AudioFeatureKey | null>(null);

  const angle = (i: number) => (Math.PI * 2 * i) / n - Math.PI / 2;
  const pt = (i: number, r: number) => ({ x: cx + r * Math.cos(angle(i)), y: cy + r * Math.sin(angle(i)) });

  const values = useMemo(
    () => AUDIO_FEATURES.map((k) => norm(k, overrides?.[k] ?? features?.[k])),
    [features, overrides]
  );
  const ghost = useMemo(() => (compareTo ? AUDIO_FEATURES.map((k) => norm(k, compareTo[k])) : null), [compareTo]);

  const poly = (vals: number[]) => vals.map((v, i) => { const p = pt(i, v * maxR); return `${p.x},${p.y}`; }).join(" ");

  const setFromPointer = (key: AudioFeatureKey, e: React.PointerEvent<SVGSVGElement>) => {
    if (!onChange) return;
    const svg = e.currentTarget;
    const rect = svg.getBoundingClientRect();
    const sx = ((e.clientX - rect.left) / rect.width) * size;
    const sy = ((e.clientY - rect.top) / rect.height) * size;
    const i = AUDIO_FEATURES.indexOf(key);
    const dx = sx - cx;
    const dy = sy - cy;
    const proj = dx * Math.cos(angle(i)) + dy * Math.sin(angle(i));
    const frac = Math.max(0, Math.min(1, proj / maxR));
    onChange(key, denorm(key, frac));
  };

  return (
    <svg
      width={size}
      height={size}
      viewBox={`0 0 ${size} ${size}`}
      style={{ display: "block", maxWidth: "100%", height: "auto", touchAction: "none", userSelect: "none" }}
      onPointerMove={(e) => drag && setFromPointer(drag, e)}
      onPointerUp={() => setDrag(null)}
      onPointerLeave={() => setDrag(null)}
    >
      <defs>
        <linearGradient id="radarFill" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#c9a7ff" stopOpacity="0.45" />
          <stop offset="100%" stopColor="#5a1230" stopOpacity="0.55" />
        </linearGradient>
        <linearGradient id="radarStroke" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#c9a7ff" />
          <stop offset="100%" stopColor="#7c4dff" />
        </linearGradient>
      </defs>

      {[0.25, 0.5, 0.75, 1].map((ring) => (
        <polygon key={ring} points={poly(AUDIO_FEATURES.map(() => ring))} fill="none" stroke="rgba(255,255,255,0.08)" strokeWidth={1} />
      ))}
      {AUDIO_FEATURES.map((_, i) => {
        const p = pt(i, maxR);
        return <line key={i} x1={cx} y1={cy} x2={p.x} y2={p.y} stroke="rgba(255,255,255,0.08)" strokeWidth={1} />;
      })}

      {ghost && <polygon points={poly(ghost)} fill="rgba(255,255,255,0.06)" stroke="rgba(255,255,255,0.25)" strokeDasharray="4 4" strokeWidth={1.5} />}

      <polygon points={poly(values)} fill="url(#radarFill)" stroke="url(#radarStroke)" strokeWidth={2.5} strokeLinejoin="round" style={{ transition: "all 0.25s ease" }} />

      {values.map((v, i) => {
        const p = pt(i, v * maxR);
        const key = AUDIO_FEATURES[i];
        const changed = overrides?.[key] !== undefined;
        return (
          <g key={key}>
            {interactive && <circle cx={p.x} cy={p.y} r={16} fill="transparent" style={{ cursor: "grab" }} onPointerDown={(e) => { (e.target as Element).setPointerCapture?.(e.pointerId); setDrag(key); }} />}
            <circle cx={p.x} cy={p.y} r={interactive ? 6 : 4} fill={changed ? "#f3eee4" : "#c9a7ff"} stroke={changed ? "#c9a7ff" : "#0b0a0e"} strokeWidth={2} style={{ pointerEvents: "none", transition: "all 0.25s ease" }} />
          </g>
        );
      })}

      {AUDIO_FEATURES.map((key, i) => {
        const p = pt(i, maxR + 26);
        const raw = overrides?.[key] ?? features?.[key];
        const label = key === "tempo" ? (raw ? `${Math.round(raw)}` : "–") : raw !== undefined && raw !== null ? `${Math.round(raw * 100)}` : "–";
        return (
          <text key={key} x={p.x} y={p.y} textAnchor="middle" dominantBaseline="middle" fontSize={11} fill="#b9b1a7" fontFamily="Inter, system-ui, sans-serif" fontWeight={600}>
            {FEATURE_LABELS[key]}
            <tspan x={p.x} dy={12} fontSize={10} fill="#7f766f" fontWeight={500}>{label}</tspan>
          </text>
        );
      })}
    </svg>
  );
}
