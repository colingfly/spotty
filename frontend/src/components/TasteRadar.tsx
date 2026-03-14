import React, { useMemo } from "react";
import type { TasteProfile, AudioFeatureKey } from "../types";
import { AUDIO_FEATURES } from "../types";

type Props = {
  taste: TasteProfile | null;
  overrides?: Partial<Record<AudioFeatureKey, number>>;
  onOverride?: (key: AudioFeatureKey, value: number) => void;
  interactive?: boolean;
  size?: number;
};

const LABELS: Record<AudioFeatureKey, string> = {
  danceability: "Dance",
  energy: "Energy",
  valence: "Mood",
  acousticness: "Acoustic",
  instrumentalness: "Instrum.",
  liveness: "Live",
  speechiness: "Speech",
  tempo: "Tempo",
};

export default function TasteRadar({
  taste,
  overrides,
  onOverride,
  interactive = false,
  size = 280,
}: Props) {
  const cx = size / 2;
  const cy = size / 2;
  const maxR = size / 2 - 40;
  const n = AUDIO_FEATURES.length;

  const values = useMemo(() => {
    if (!taste) return AUDIO_FEATURES.map(() => 0);
    return AUDIO_FEATURES.map((key) => {
      const raw = overrides?.[key] ?? taste[key];
      // Normalize tempo to 0-1 range (30-300 BPM)
      if (key === "tempo") return Math.min(raw / 200, 1);
      return Math.min(raw, 1);
    });
  }, [taste, overrides]);

  const points = useMemo(() => {
    return values.map((v, i) => {
      const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
      const r = v * maxR;
      return {
        x: cx + r * Math.cos(angle),
        y: cy + r * Math.sin(angle),
      };
    });
  }, [values, cx, cy, maxR, n]);

  const polygon = points.map((p) => `${p.x},${p.y}`).join(" ");

  // Grid rings
  const rings = [0.25, 0.5, 0.75, 1.0];

  const handleClick = (idx: number, e: React.MouseEvent<SVGCircleElement>) => {
    if (!interactive || !onOverride || !taste) return;
    const key = AUDIO_FEATURES[idx];
    const current = overrides?.[key] ?? taste[key];
    // Cycle: low -> mid -> high -> reset
    const normalized = key === "tempo" ? current / 200 : current;
    let next: number;
    if (normalized < 0.33) next = 0.5;
    else if (normalized < 0.66) next = 0.85;
    else next = 0.15;
    if (key === "tempo") next = next * 200;
    onOverride(key, parseFloat(next.toFixed(3)));
  };

  return (
    <div style={{ display: "inline-block" }}>
      <svg width={size} height={size} viewBox={`0 0 ${size} ${size}`}>
        {/* Grid rings */}
        {rings.map((ring) => (
          <polygon
            key={ring}
            points={AUDIO_FEATURES.map((_, i) => {
              const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
              const r = ring * maxR;
              return `${cx + r * Math.cos(angle)},${cy + r * Math.sin(angle)}`;
            }).join(" ")}
            fill="none"
            stroke="#333"
            strokeWidth={0.5}
            opacity={0.3}
          />
        ))}

        {/* Axis lines */}
        {AUDIO_FEATURES.map((_, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          return (
            <line
              key={i}
              x1={cx}
              y1={cy}
              x2={cx + maxR * Math.cos(angle)}
              y2={cy + maxR * Math.sin(angle)}
              stroke="#444"
              strokeWidth={0.5}
              opacity={0.3}
            />
          );
        })}

        {/* Data polygon */}
        <polygon
          points={polygon}
          fill="rgba(29, 185, 84, 0.25)"
          stroke="#1db954"
          strokeWidth={2}
        />

        {/* Data points */}
        {points.map((p, i) => (
          <circle
            key={i}
            cx={p.x}
            cy={p.y}
            r={interactive ? 6 : 4}
            fill="#1db954"
            stroke="white"
            strokeWidth={1.5}
            style={{ cursor: interactive ? "pointer" : "default" }}
            onClick={(e) => handleClick(i, e)}
          />
        ))}

        {/* Labels */}
        {AUDIO_FEATURES.map((key, i) => {
          const angle = (Math.PI * 2 * i) / n - Math.PI / 2;
          const labelR = maxR + 24;
          const lx = cx + labelR * Math.cos(angle);
          const ly = cy + labelR * Math.sin(angle);
          return (
            <text
              key={key}
              x={lx}
              y={ly}
              textAnchor="middle"
              dominantBaseline="middle"
              fontSize={11}
              fill="#ccc"
              fontFamily="system-ui, sans-serif"
            >
              {LABELS[key]}
            </text>
          );
        })}
      </svg>
    </div>
  );
}
