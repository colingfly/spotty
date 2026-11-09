import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { Check, Eye, FileText, Layers, Music2, PenLine, Play, RotateCcw, Sparkles, Tent, Wand2, X, type LucideIcon } from "lucide-react";
import TasteRadar from "../components/TasteRadar";
import TrackCard from "../components/TrackCard";
import { EngineBadge, EmptyState, PlaceholderArt, Skeleton, Toggle } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useBatches } from "../hooks/useBatch";
import { useToast } from "../hooks/useToast";
import { api } from "../lib/api";
import { fmtTime } from "../lib/format";
import type { Artist, AudioFeatureKey, Composed, Features, GenerateRequest, Generation, Mode, Paged, Preset, TasteProfile } from "../types";
import { AUDIO_FEATURES, FEATURE_HINTS, FEATURE_LABELS, MODES, MODE_META } from "../types";
import { FESTIVAL_KEY } from "./ScanPage";

const MODE_ICONS: Record<Mode, LucideIcon> = {
  taste: Music2,
  mood: Layers,
  lyrics: PenLine,
  fusion: Sparkles,
  brief: FileText,
  festival: Tent,
};

const BRIEF_IDEAS = [
  "a rainy 2am drive through Tokyo, neon reflections, half asleep",
  "last song of the night at a small basement club, everyone singing",
  "sunrise on a rooftop after not sleeping, hopeful but wrecked",
  "revenge anthem, stadium drums, no apologies",
  "slow dancing in a kitchen, one lamp on",
  "running late through a crowded station, heart racing",
];

type Stage = "idle" | "composing" | "composed" | "generating";

export default function StudioPage() {
  const { me } = useAuth();
  const toast = useToast();
  const [params, setParams] = useSearchParams();
  const batches = useBatches();

  const caps = me?.capabilities;
  const llmOn = !!caps?.llm.configured;
  const gpuOn = !!caps?.acestep;
  const maxVar = caps?.max_variations ?? 3;
  const maxDur = caps?.max_duration_seconds ?? 240;

  const [taste, setTaste] = useState<TasteProfile | null>(null);
  const [presets, setPresets] = useState<Preset[]>([]);
  const [topArtists, setTopArtists] = useState<Artist[]>([]);

  const initialMode = (params.get("mode") as Mode) || "taste";
  const [mode, setMode] = useState<Mode>(MODES.includes(initialMode) ? initialMode : "taste");
  const [preset, setPreset] = useState<string | null>(null);
  const [overrides, setOverrides] = useState<Partial<Features>>({});
  const [lyrics, setLyrics] = useState("");
  const [theme, setTheme] = useState("");
  const [brief, setBrief] = useState("");
  const [vocals, setVocals] = useState<boolean | null>(null);
  const [duration, setDuration] = useState<number>(caps?.default_duration_seconds ?? 60);
  const [variations, setVariations] = useState(1);
  const [fusionIds, setFusionIds] = useState<string[]>([]);
  const [festivalNames, setFestivalNames] = useState<string[]>([]);
  const [festivalInput, setFestivalInput] = useState("");

  const [stage, setStage] = useState<Stage>("idle");
  const [composed, setComposed] = useState<Composed | null>(null);
  const [edits, setEdits] = useState<Partial<Composed>>({});
  const [writing, setWriting] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const startedAt = useRef<number | null>(null);
  const resultsRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    api.get<TasteProfile>("/api/me/taste").then(setTaste).catch((e) => toast.error(e.message));
    api.get<{ items: Preset[] }>("/api/generate/presets").then((r) => setPresets(r.items)).catch(() => undefined);
    api.get<Paged<Artist>>("/api/me/top-artists?time_range=medium_term&limit=24").then((r) => setTopArtists(r.items)).catch(() => undefined);
    const stored = sessionStorage.getItem(FESTIVAL_KEY);
    if (stored) {
      try {
        const names = JSON.parse(stored) as string[];
        if (Array.isArray(names) && names.length) setFestivalNames(names.slice(0, 10));
      } catch { /* ignore */ }
      sessionStorage.removeItem(FESTIVAL_KEY);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  useEffect(() => {
    if (caps?.default_duration_seconds) setDuration((d) => (d === 60 ? caps.default_duration_seconds : d));
  }, [caps?.default_duration_seconds]);

  useEffect(() => {
    if (!batches.anyActive) { startedAt.current = null; setElapsed(0); return; }
    if (!startedAt.current) startedAt.current = Date.now();
    const id = window.setInterval(() => setElapsed(Math.round((Date.now() - (startedAt.current || Date.now())) / 1000)), 500);
    return () => window.clearInterval(id);
  }, [batches.anyActive]);

  const switchMode = (m: Mode) => {
    setMode(m);
    setComposed(null);
    setEdits({});
    setStage("idle");
    const next = new URLSearchParams(params);
    next.set("mode", m);
    setParams(next, { replace: true });
  };

  const setOverride = (key: AudioFeatureKey, value: number) => setOverrides((o) => ({ ...o, [key]: value }));
  const wantVocals = vocals ?? (mode === "lyrics" ? true : (taste ? taste.instrumentalness < 0.5 : true));

  const request = useMemo<GenerateRequest>(() => ({
    mode,
    preset,
    overrides: mode === "mood" ? overrides : Object.keys(overrides).length ? overrides : undefined,
    lyrics: mode === "lyrics" && lyrics.trim() ? lyrics.trim() : undefined,
    lyrics_theme: mode === "lyrics" && !lyrics.trim() && theme.trim() ? theme.trim() : undefined,
    brief: mode === "brief" ? brief.trim() : undefined,
    vocals: vocals === null ? undefined : vocals,
    duration,
    variations,
    artist_ids: mode === "fusion" ? fusionIds : undefined,
    artist_names: mode === "festival" ? festivalNames : undefined,
  }), [mode, preset, overrides, lyrics, theme, brief, vocals, duration, variations, fusionIds, festivalNames]);

  const validation = useMemo<string | null>(() => {
    if (mode === "lyrics" && !lyrics.trim() && !theme.trim()) return "Add lyrics, or a theme for Claude to write from.";
    if (mode === "brief" && brief.trim().length < 8) return "Describe the track in a sentence or two.";
    if (mode === "fusion" && fusionIds.length < 2) return "Pick at least two artists to fuse.";
    if (mode === "festival" && festivalNames.length === 0) return "Add at least one act from the lineup.";
    return null;
  }, [mode, lyrics, theme, brief, fusionIds, festivalNames]);

  const compose = async () => {
    if (validation) { toast.error(validation); return; }
    setStage("composing");
    setComposed(null);
    setEdits({});
    try {
      const r = await api.post<{ composed: Composed }>("/api/generate/preview", request);
      setComposed(r.composed);
      setStage("composed");
    } catch (e: any) {
      toast.error(e.message);
      setStage("idle");
    }
  };

  const generate = async (direct = false) => {
    if (validation) { toast.error(validation); return; }
    if (!gpuOn) { toast.error("The ACE-Step GPU server is offline. Start it and try again."); return; }
    setStage("generating");
    try {
      const body: GenerateRequest = { ...request };
      if (!direct && composed) {
        body.edits = {
          title: edits.title ?? composed.title,
          prompt: edits.prompt ?? composed.prompt,
          lyrics: edits.lyrics ?? composed.lyrics,
          bpm: edits.bpm ?? composed.bpm,
          key_scale: edits.key_scale ?? composed.key_scale,
          duration: edits.duration ?? composed.duration,
        };
      }
      const r = await api.post<{ batch_id: string; items: Generation[]; composed: Composed }>("/api/generate", body);
      batches.track(r.batch_id, r.items);
      toast.success(variations > 1 ? `Rendering ${variations} takes of “${r.composed.title}”.` : `Rendering “${r.composed.title}”.`);
      setStage("idle");
      setComposed(null);
      setEdits({});
      window.setTimeout(() => resultsRef.current?.scrollIntoView({ behavior: "smooth", block: "start" }), 80);
    } catch (e: any) {
      toast.error(e.message);
      setStage(composed ? "composed" : "idle");
    }
  };

  const writeLyrics = async () => {
    if (!theme.trim()) { toast.error("Give Claude a theme first."); return; }
    setWriting(true);
    try {
      const r = await api.post<{ title: string; lyrics: string }>("/api/compose/lyrics", { theme: theme.trim() });
      setLyrics(r.lyrics);
      toast.success(`Wrote “${r.title}”. Edit anything you like.`);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setWriting(false);
    }
  };

  const addFestivalName = () => {
    const parts = festivalInput.split(/[,\n]/).map((s) => s.trim()).filter(Boolean);
    if (!parts.length) return;
    setFestivalNames((xs) => Array.from(new Set([...xs, ...parts])).slice(0, 10));
    setFestivalInput("");
  };

  const toggleFusion = (id: string) => setFusionIds((xs) => (xs.includes(id) ? xs.filter((x) => x !== id) : xs.length >= 3 ? xs : [...xs, id]));

  const results = batches.items;
  const completed = results.filter((g) => g.status === "completed");
  const busy = stage === "composing" || stage === "generating";

  const removeResult = useCallback(async (g: Generation) => {
    try {
      await api.del(`/api/generate/${g.generation_id}`);
      batches.remove(g.generation_id);
    } catch (e: any) {
      toast.error(e.message);
    }
  }, [batches, toast]);

  const favResult = useCallback(async (g: Generation) => {
    try {
      batches.update(await api.post<Generation>(`/api/generate/${g.generation_id}/favorite`));
    } catch (e: any) {
      toast.error(e.message);
    }
  }, [batches, toast]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Studio</h1>
          <p className="page-sub">Pick a way in, shape the brief, render. {llmOn ? "Claude writes each brief from your profile." : "Running on the template composer."}</p>
        </div>
        <div className="row">
          {!gpuOn && <span className="alert alert-warn" style={{ padding: "8px 12px" }}>GPU server offline. You can still compose previews.</span>}
        </div>
      </div>

      <div className="studio-layout">
        {/* ---------------- Left: controls ---------------- */}
        <div className="stack" style={{ gap: 16 }}>
          <div className="mode-grid">
            {MODES.map((m) => {
              const Icon = MODE_ICONS[m];
              return (
                <button key={m} className={`mode-card ${mode === m ? "active" : ""}`} onClick={() => switchMode(m)}>
                  <span className="mode-icon"><Icon size={16} /></span>
                  <span className="mode-name">{MODE_META[m].label}</span>
                  <span className="mode-blurb">{MODE_META[m].blurb}</span>
                </button>
              );
            })}
          </div>

          {/* Mode body */}
          <div className="card">
            {mode === "taste" && (
              <div className="row" style={{ gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>
                {taste ? <TasteRadar features={taste} size={240} /> : <Skeleton w={240} h={240} r={120} />}
                <div className="stack" style={{ flex: 1, minWidth: 220 }}>
                  <div className="card-title">Straight from your profile</div>
                  <p className="small muted">
                    {taste ? `Built on ${taste.genre_weights.slice(0, 3).map((g) => g.genre).join(", ")} with ${Math.round(taste.energy * 100)}% energy and a ${Math.round(taste.tempo)} BPM centre.` : "Loading your profile…"}
                  </p>
                  {taste && (
                    <div className="genre-cloud">
                      {taste.genre_weights.slice(0, 8).map((g) => <span key={g.genre} className="chip chip-xs">{g.genre}</span>)}
                    </div>
                  )}
                  <p className="tiny dim">Add a preset below to tilt it without touching the sliders.</p>
                </div>
              </div>
            )}

            {mode === "mood" && (
              <div className="row" style={{ gap: 20, alignItems: "flex-start", flexWrap: "wrap" }}>
                <div style={{ flex: "0 0 auto" }}>
                  {taste ? <TasteRadar features={taste} overrides={overrides} compareTo={Object.keys(overrides).length ? taste : null} interactive onChange={setOverride} size={260} /> : <Skeleton w={260} h={260} r={130} />}
                  <div className="tiny dim" style={{ textAlign: "center", marginTop: 4 }}>Drag the points, or use the sliders</div>
                </div>
                <div className="stack" style={{ flex: 1, minWidth: 260 }}>
                  {AUDIO_FEATURES.map((k) => {
                    const base = taste?.[k] ?? 0;
                    const val = overrides[k] ?? base;
                    const isTempo = k === "tempo";
                    const pct = isTempo ? ((val - 40) / 180) * 100 : val * 100;
                    return (
                      <div key={k} className={`slider-row ${overrides[k] !== undefined ? "changed" : ""}`}>
                        <div>
                          <div className="slider-name">{FEATURE_LABELS[k]}</div>
                        </div>
                        <div>
                          <input type="range" className="range" min={isTempo ? 40 : 0} max={isTempo ? 220 : 100} value={isTempo ? Math.round(val) : Math.round(val * 100)}
                            onChange={(e) => setOverride(k, isTempo ? Number(e.target.value) : Number(e.target.value) / 100)} style={{ ["--p" as any]: `${Math.max(0, Math.min(100, pct))}%` }} aria-label={FEATURE_LABELS[k]} />
                          <div className="hint"><span>{FEATURE_HINTS[k][0]}</span><span>{FEATURE_HINTS[k][1]}</span></div>
                        </div>
                        <span className="slider-val">{isTempo ? `${Math.round(val)}` : `${Math.round(val * 100)}%`}</span>
                      </div>
                    );
                  })}
                  <div>
                    <button className="btn btn-ghost btn-sm" onClick={() => setOverrides({})} disabled={!Object.keys(overrides).length}><RotateCcw size={13} /> Reset to my profile</button>
                  </div>
                </div>
              </div>
            )}

            {mode === "lyrics" && (
              <div className="stack">
                <div className="field">
                  <label className="label">Theme (optional if you paste lyrics)</label>
                  <div className="row">
                    <input className="input" placeholder="e.g. leaving a city you loved" value={theme} onChange={(e) => setTheme(e.target.value)} maxLength={200} />
                    {llmOn && (
                      <button className="btn btn-ai" onClick={writeLyrics} disabled={writing || !theme.trim()} title="Claude writes lyrics in your sound">
                        {writing ? <span className="spinner" /> : <Sparkles size={15} />} Write for me
                      </button>
                    )}
                  </div>
                  {!llmOn && <span className="help">Without a Claude key the template engine builds a simple verse/chorus from the theme.</span>}
                </div>
                <div className="field">
                  <label className="label">Lyrics</label>
                  <textarea className="textarea mono" rows={10} value={lyrics} onChange={(e) => setLyrics(e.target.value)} maxLength={4096}
                    placeholder={"[verse]\nWrite your lines here…\n\n[chorus]\nThe hook goes here and repeats…"} />
                  <span className="help">{lyrics.length} / 4096 · Section tags like [verse], [chorus], [bridge] steer the structure.</span>
                </div>
              </div>
            )}

            {mode === "fusion" && (
              <div className="stack">
                <div className="row between">
                  <div>
                    <div className="card-title">Pick two or three artists</div>
                    <div className="tiny dim">{fusionIds.length} / 3 selected · from your last six months</div>
                  </div>
                  {fusionIds.length > 0 && <button className="btn btn-ghost btn-sm" onClick={() => setFusionIds([])}>Clear</button>}
                </div>
                {topArtists.length === 0 ? <Skeleton h={160} /> : (
                  <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fill, minmax(110px, 1fr))", gap: 8 }}>
                    {topArtists.map((a) => {
                      const on = fusionIds.includes(a.id);
                      return (
                        <div key={a.id} className={`artist-tile selectable ${on ? "selected" : ""}`} onClick={() => toggleFusion(a.id)} role="checkbox" aria-checked={on} title={a.genres.slice(0, 3).join(", ")}>
                          {a.image ? <img src={a.image} alt={a.name} loading="lazy" /> : <PlaceholderArt size={22} />}
                          {on && <span className="check"><Check size={14} /></span>}
                          <div className="overlay"><div className="name truncate" style={{ fontSize: 12 }}>{a.name}</div></div>
                        </div>
                      );
                    })}
                  </div>
                )}
              </div>
            )}

            {mode === "brief" && (
              <div className="stack">
                <div className="field">
                  <label className="label">Creative brief</label>
                  <textarea className="textarea" rows={4} value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={600} placeholder="Describe a scene, a feeling, a reference point. The more concrete, the better." />
                  <span className="help">{brief.length} / 600 · Your profile still sets the sonic palette.</span>
                </div>
                <div className="genre-cloud">
                  {BRIEF_IDEAS.map((idea) => <button key={idea} className="chip chip-xs" onClick={() => setBrief(idea)}>{idea}</button>)}
                </div>
              </div>
            )}

            {mode === "festival" && (
              <div className="stack">
                <div className="card-title">The lineup</div>
                <div className="row">
                  <input className="input" placeholder="Add acts, comma separated" value={festivalInput} onChange={(e) => setFestivalInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addFestivalName()} />
                  <button className="btn btn-secondary" onClick={addFestivalName}>Add</button>
                </div>
                {festivalNames.length === 0 ? (
                  <p className="small dim">Scan a poster on the Scan page, or type the acts here. Up to ten.</p>
                ) : (
                  <div className="genre-cloud">
                    {festivalNames.map((n) => (
                      <span key={n} className="chip active">{n}<button onClick={() => setFestivalNames((xs) => xs.filter((x) => x !== n))} style={{ background: "none", border: 0, color: "inherit", padding: 0, display: "inline-flex" }} aria-label={`Remove ${n}`}><X size={12} /></button></span>
                    ))}
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Presets + render settings */}
          <div className="card">
            <div className="section-title">Preset</div>
            <div className="genre-cloud" style={{ marginBottom: 18 }}>
              <button className={`chip ${!preset ? "active" : ""}`} onClick={() => setPreset(null)}>None</button>
              {presets.map((p) => (
                <button key={p.id} className={`chip ${preset === p.id ? "active" : ""}`} onClick={() => setPreset(preset === p.id ? null : p.id)} title={p.tags.join(" · ")}>
                  <span>{p.emoji}</span> {p.label}
                </button>
              ))}
            </div>

            <div className="grid grid-3" style={{ gap: 18 }}>
              <div className="field">
                <label className="label">Length · {fmtTime(duration)}</label>
                <input type="range" className="range" min={15} max={maxDur} step={5} value={duration} onChange={(e) => setDuration(Number(e.target.value))} style={{ ["--p" as any]: `${((duration - 15) / (maxDur - 15)) * 100}%` }} />
                <span className="help">Longer takes proportionally longer to render.</span>
              </div>
              <div className="field">
                <label className="label">Takes</label>
                <div className="segmented">
                  {Array.from({ length: maxVar }, (_, i) => i + 1).map((n) => <button key={n} className={variations === n ? "active" : ""} onClick={() => setVariations(n)}>{n}</button>)}
                </div>
                <span className="help">Same brief, different seeds.</span>
              </div>
              <div className="field">
                <label className="label">Vocals</label>
                <div className="row">
                  <Toggle on={wantVocals} onChange={(v) => setVocals(v)} label="Vocals" />
                  <span className="small muted">{wantVocals ? "Sung or rapped" : "Instrumental"}</span>
                  {vocals !== null && <button className="btn btn-ghost btn-sm" onClick={() => setVocals(null)}>auto</button>}
                </div>
                {mode === "lyrics" && <span className="help">Lyric mode always sings.</span>}
              </div>
            </div>
          </div>

          {/* Actions */}
          <div className="row row-wrap">
            <button className="btn btn-secondary btn-lg" onClick={compose} disabled={busy || !!validation}>
              {stage === "composing" ? <span className="spinner" /> : <Eye size={17} />} Preview brief
            </button>
            <button className="btn btn-primary btn-lg" onClick={() => generate(true)} disabled={busy || !!validation || !gpuOn} title={!gpuOn ? "ACE-Step is offline" : undefined}>
              {stage === "generating" ? <span className="spinner" /> : <Wand2 size={17} />} Generate{variations > 1 ? ` ${variations} takes` : ""}
            </button>
            {validation && <span className="small dim">{validation}</span>}
          </div>
        </div>

        {/* ---------------- Right: brief + results ---------------- */}
        <div className="stack" style={{ gap: 16 }} ref={resultsRef}>
          {stage === "composing" && (
            <div className="card card-glow stack">
              <div className="row"><span className="spinner" /><span className="muted small">{llmOn ? "Claude is reading your profile…" : "Composing brief…"}</span></div>
              <Skeleton h={22} w="50%" /><Skeleton h={12} /><Skeleton h={12} /><Skeleton h={12} w="70%" />
            </div>
          )}

          {composed && stage !== "composing" && (
            <div className="card card-glow stack">
              <div className="row between">
                <div className="row"><EngineBadge engine={composed.engine} /><span className="tiny dim">{MODE_META[composed.mode].label}{composed.preset ? ` · ${presets.find((p) => p.id === composed.preset)?.label}` : ""}</span></div>
                <button className="btn btn-ghost btn-sm" onClick={() => { setComposed(null); setEdits({}); setStage("idle"); }} aria-label="Discard"><X size={14} /></button>
              </div>
              <div className="field">
                <label className="label">Title</label>
                <input className="input" value={edits.title ?? composed.title} onChange={(e) => setEdits((x) => ({ ...x, title: e.target.value }))} maxLength={80} />
              </div>
              <div className="field">
                <label className="label">Style caption</label>
                <textarea className="textarea" rows={4} value={edits.prompt ?? composed.prompt} onChange={(e) => setEdits((x) => ({ ...x, prompt: e.target.value }))} />
              </div>
              <div className="grid grid-2" style={{ gap: 10 }}>
                <div className="field">
                  <label className="label">BPM</label>
                  <input className="input" type="number" min={40} max={220} value={edits.bpm ?? composed.bpm} onChange={(e) => setEdits((x) => ({ ...x, bpm: Number(e.target.value) }))} />
                </div>
                <div className="field">
                  <label className="label">Key</label>
                  <input className="input" value={edits.key_scale ?? composed.key_scale ?? ""} placeholder="e.g. F# minor" onChange={(e) => setEdits((x) => ({ ...x, key_scale: e.target.value }))} />
                </div>
              </div>
              <div className="field">
                <label className="label">Lyrics</label>
                {(edits.lyrics ?? composed.lyrics) === "[Instrumental]" ? (
                  <div className="row"><span className="badge badge-gray">Instrumental</span><button className="btn btn-ghost btn-sm" onClick={() => setEdits((x) => ({ ...x, lyrics: "[verse]\n" }))}>Add lyrics</button></div>
                ) : (
                  <textarea className="textarea mono" rows={8} value={edits.lyrics ?? composed.lyrics} onChange={(e) => setEdits((x) => ({ ...x, lyrics: e.target.value }))} />
                )}
              </div>
              {composed.rationale && <p className="small muted" style={{ fontStyle: "italic" }}>{composed.rationale}</p>}
              {composed.tags.length > 0 && <div className="genre-cloud">{composed.tags.map((t) => <span key={t} className="chip chip-xs">{t}</span>)}</div>}
              <div className="row">
                <button className="btn btn-primary" onClick={() => generate(false)} disabled={busy || !gpuOn}>
                  {stage === "generating" ? <span className="spinner" /> : <Play size={15} />} Render this brief{variations > 1 ? ` × ${variations}` : ""}
                </button>
                <button className="btn btn-ghost" onClick={compose} disabled={busy}><RotateCcw size={14} /> Recompose</button>
              </div>
            </div>
          )}

          {batches.anyActive && (
            <div className="card">
              <div className="row between" style={{ marginBottom: 10 }}>
                <div className="row"><span className="spinner" /><span style={{ fontWeight: 600 }}>Rendering on ACE-Step</span></div>
                <span className="mono small dim">{fmtTime(elapsed)}</span>
              </div>
              <div className="progress"><i style={{ width: `${Math.min(92, (elapsed / 35) * 100)}%` }} /></div>
              <div className="tiny dim" style={{ marginTop: 8 }}>A 60-second take usually lands in 20 to 40 seconds. You can leave this page; it keeps rendering.</div>
            </div>
          )}

          {results.length === 0 && !composed && stage === "idle" ? (
            <EmptyState title="Your session" body="Previews and rendered takes show up here. Press Preview to read the brief before spending GPU time, or Generate to go straight to audio." />
          ) : (
            <div className="stack" style={{ gap: 10 }}>
              {results.length > 0 && (
                <div className="row between">
                  <div className="section-title" style={{ margin: 0 }}>This session · {completed.length} ready</div>
                  <button className="btn btn-ghost btn-sm" onClick={batches.clear}>Clear</button>
                </div>
              )}
              {[...results].reverse().map((g) => (
                <TrackCard key={g.generation_id} gen={g} queue={completed} onChange={batches.update} onDelete={removeResult} onToggleFavorite={favResult} />
              ))}
              {results.length > 0 && composed === null && stage === "idle" && (
                <div className="tiny dim" style={{ textAlign: "center" }}>Lyrics and full captions are kept with each track in the Library.</div>
              )}
            </div>
          )}

        </div>
      </div>
    </div>
  );
}
