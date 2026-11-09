import React, { useEffect } from "react";
import { Sparkles, Wand2 } from "lucide-react";
import type { Generation, Mode } from "../types";
import { FEATURE_TYPE_TO_MODE, MODE_META } from "../types";

export function Spinner({ size = 16 }: { size?: number }) {
  return <span className="spinner" style={{ width: size, height: size }} aria-label="Loading" />;
}

export function Skeleton({ w = "100%", h = 14, r = 8, style }: { w?: number | string; h?: number | string; r?: number; style?: React.CSSProperties }) {
  return <div className="skeleton" style={{ width: w, height: h, borderRadius: r, ...style }} />;
}

export function EmptyState({ title, body, action }: { title: string; body?: string; action?: React.ReactNode }) {
  return (
    <div className="empty">
      <h3>{title}</h3>
      {body && <p className="small">{body}</p>}
      {action && <div style={{ marginTop: 16 }}>{action}</div>}
    </div>
  );
}

export function Toggle({ on, onChange, label }: { on: boolean; onChange: (v: boolean) => void; label?: string }) {
  return (
    <button type="button" className={`toggle ${on ? "on" : ""}`} role="switch" aria-checked={on} aria-label={label} onClick={() => onChange(!on)} />
  );
}

export function Modal({ open, onClose, title, children, footer }: { open: boolean; onClose: () => void; title: string; children: React.ReactNode; footer?: React.ReactNode }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => e.key === "Escape" && onClose();
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open, onClose]);
  if (!open) return null;
  return (
    <div className="modal-backdrop" onClick={onClose} role="dialog" aria-modal="true" aria-label={title}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <h3 style={{ fontSize: 18, marginBottom: 10 }}>{title}</h3>
        <div className="muted small">{children}</div>
        {footer && <div className="row" style={{ justifyContent: "flex-end", marginTop: 20 }}>{footer}</div>}
      </div>
    </div>
  );
}

export function modeOf(g: Pick<Generation, "mode" | "feature_type">): Mode {
  return g.mode || FEATURE_TYPE_TO_MODE[g.feature_type] || "taste";
}

const MODE_BADGE: Record<Mode, string> = {
  taste: "badge-green",
  mood: "badge-cyan",
  lyrics: "badge-amber",
  fusion: "badge-violet",
  brief: "badge-violet",
  festival: "badge-rose",
};

export function ModeBadge({ mode }: { mode: Mode }) {
  return <span className={`badge ${MODE_BADGE[mode]}`}>{MODE_META[mode].short}</span>;
}

export function EngineBadge({ engine, compact }: { engine: "llm" | "template" | null | undefined; compact?: boolean }) {
  if (engine === "llm") {
    return (
      <span className="badge badge-violet" title="Composed by Claude">
        <Sparkles size={11} /> {compact ? "AI" : "Claude"}
      </span>
    );
  }
  return (
    <span className="badge badge-gray" title="Composed by the template engine">
      <Wand2 size={11} /> {compact ? "T" : "Template"}
    </span>
  );
}

export function StatusBadge({ status }: { status: Generation["status"] }) {
  const cls = status === "completed" ? "badge-green" : status === "failed" ? "badge-rose" : "badge-amber";
  return <span className={`badge ${cls}`}>{status}</span>;
}

export function Eq() {
  return (
    <span className="eq" aria-hidden>
      <span /><span /><span /><span />
    </span>
  );
}

export function PlaceholderArt({ size = 20 }: { size?: number }) {
  return (
    <div className="placeholder-art">
      <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round">
        <path d="M4 16c3-5 13-5 16 0M6 11c2.5-3.5 9.5-3.5 12 0M8 6.5c1.5-2 6.5-2 8 0" />
      </svg>
    </div>
  );
}

export function LyricsBlock({ text, maxHeight }: { text: string; maxHeight?: number }) {
  const parts = text.split(/(\[[^\]]+\])/g);
  return (
    <div className="lyrics-block" style={maxHeight ? { maxHeight } : undefined}>
      {parts.map((p, i) => (/^\[[^\]]+\]$/.test(p) ? <span key={i} className="tag">{p}</span> : <React.Fragment key={i}>{p}</React.Fragment>))}
    </div>
  );
}
