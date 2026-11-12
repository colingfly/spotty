import React, { useEffect } from "react";
import type { Generation, Mode } from "../types";
import { FEATURE_TYPE_TO_MODE, MODE_META } from "../types";

export function Section({ n, title, right, children }: { n: string; title: string; right?: React.ReactNode; children: React.ReactNode }) {
  return (
    <section className="section">
      <h2 className="row between">
        <span><span className="marker">[{n}]</span>{title}</span>
        {right && <span style={{ fontWeight: 400, textTransform: "none", letterSpacing: 0 }}>{right}</span>}
      </h2>
      {children}
    </section>
  );
}

export function Loading({ what = "loading" }: { what?: string }) {
  return <p className="small" role="status">{what}…</p>;
}

export function Empty({ children }: { children: React.ReactNode }) {
  return <div className="box">{children}</div>;
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
    <>
      <div className="modal-backdrop" onClick={onClose} />
      <div className="modal" role="dialog" aria-modal="true" aria-label={title}>
        <h3>{title}</h3>
        <div style={{ margin: "10px 0 16px" }}>{children}</div>
        {footer && <div className="actions">{footer}</div>}
      </div>
    </>
  );
}

export function modeOf(g: Pick<Generation, "mode" | "feature_type">): Mode {
  return g.mode || FEATURE_TYPE_TO_MODE[g.feature_type] || "taste";
}

export function modeLabel(g: Pick<Generation, "mode" | "feature_type">): string {
  return MODE_META[modeOf(g)].short.toLowerCase();
}

export function engineLabel(engine: "llm" | "template" | null | undefined): string {
  return engine === "llm" ? "claude" : "template";
}

export function Lyrics({ text }: { text: string }) {
  return <pre className="pre" style={{ margin: 0, font: "inherit" }}>{text}</pre>;
}

export function Thumb({ src, alt }: { src?: string | null; alt: string }) {
  if (src) return <img className="thumb" src={src} alt={alt} loading="lazy" />;
  return null;
}
