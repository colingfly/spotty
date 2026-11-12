import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import TasteRadar from "../components/TasteRadar";
import TrackCard from "../components/TrackCard";
import { Loading, Section, engineLabel } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useBatches } from "../hooks/useBatch";
import { useToast } from "../hooks/useToast";
import { api } from "../lib/api";
import { fmtTime } from "../lib/format";
import type { Artist, AudioFeatureKey, Composed, Features, GenerateRequest, Generation, Mode, Paged, Preset, TasteProfile } from "../types";
import { AUDIO_FEATURES, FEATURE_HINTS, FEATURE_LABELS, MODES, MODE_META } from "../types";
import { FESTIVAL_KEY } from "./ScanPage";

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
  const [preset, setPreset] = useState<string>("");
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

  useEffect(() => {
    api.get<TasteProfile>("/api/me/taste").then(setTaste).catch((e) => toast.error(e.message));
    api.get<{ items: Preset[] }>("/api/generate/presets").then((r) => setPresets(r.items)).catch(() => undefined);
    api.get<Paged<Artist>>("/api/me/top-artists?time_range=medium_term&limit=30").then((r) => setTopArtists(r.items)).catch(() => undefined);
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
    const id = window.setInterval(() => setElapsed(Math.round((Date.now() - (startedAt.current || Date.now())) / 1000)), 1000);
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
  const wantVocals = vocals ?? (mode === "lyrics" ? true : taste ? taste.instrumentalness < 0.5 : true);

  const request = useMemo<GenerateRequest>(() => ({
    mode,
    preset: preset || null,
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
    if (mode === "lyrics" && !lyrics.trim() && !theme.trim()) return "add lyrics, or a theme to write from.";
    if (mode === "brief" && brief.trim().length < 8) return "describe the track in a sentence.";
    if (mode === "fusion" && fusionIds.length < 2) return "pick at least two artists.";
    if (mode === "festival" && festivalNames.length === 0) return "add at least one act.";
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
    if (!gpuOn) { toast.error("the ace-step gpu server is offline."); return; }
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
      toast.success(`rendering ${variations > 1 ? `${variations} takes of ` : ""}"${r.composed.title}".`);
      setStage("idle");
      setComposed(null);
      setEdits({});
    } catch (e: any) {
      toast.error(e.message);
      setStage(composed ? "composed" : "idle");
    }
  };

  const writeLyrics = async () => {
    if (!theme.trim()) { toast.error("enter a theme first."); return; }
    setWriting(true);
    try {
      const r = await api.post<{ title: string; lyrics: string }>("/api/compose/lyrics", { theme: theme.trim() });
      setLyrics(r.lyrics);
      toast.success(`wrote "${r.title}". edit anything.`);
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
    <div>
      <h1>studio</h1>
      <p className="small">composer: {llmOn ? "claude" : "template"} · gpu: {gpuOn ? "online" : "offline"}{!gpuOn ? " (previews still work)" : ""}</p>

      <div className="cols split">
        <div>
          <Section n="01" title="mode">
            <fieldset>
              <div className="radio-list">
                {MODES.map((m, i) => (
                  <label key={m}>
                    <input type="radio" name="mode" value={m} checked={mode === m} onChange={() => switchMode(m)} />
                    <span><span className="b">{String(i + 1).padStart(2, "0")} {MODE_META[m].label.toLowerCase()}</span><br /><span className="small">{MODE_META[m].blurb.toLowerCase()}</span></span>
                  </label>
                ))}
              </div>
            </fieldset>
          </Section>

          <Section n="02" title={MODE_META[mode].label.toLowerCase()}>
            {mode === "taste" && (
              <div className="box">
                {taste ? (
                  <div className="cols">
                    <TasteRadar features={taste} size={280} />
                    <dl className="kv">
                      <dt>top genres</dt><dd>{taste.genre_weights.slice(0, 5).map((g) => g.genre).join(", ")}</dd>
                      <dt>energy</dt><dd>{Math.round(taste.energy * 100)}%</dd>
                      <dt>tempo</dt><dd>{Math.round(taste.tempo)} bpm</dd>
                      <dt>artists</dt><dd>{taste.top_artists.length}</dd>
                    </dl>
                  </div>
                ) : <Loading what="profile" />}
              </div>
            )}

            {mode === "mood" && (
              <div className="cols">
                <div className="box">
                  {taste ? <TasteRadar features={taste} overrides={overrides} compareTo={Object.keys(overrides).length ? taste : null} interactive onChange={setOverride} size={280} /> : <Loading what="profile" />}
                  <p className="small">drag the points, or use the sliders. dashed line is your profile.</p>
                </div>
                <div className="table-wrap">
                  <table>
                    <tbody>
                      {AUDIO_FEATURES.map((k) => {
                        const base = taste?.[k] ?? 0;
                        const val = overrides[k] ?? base;
                        const isTempo = k === "tempo";
                        return (
                          <tr key={k}>
                            <td style={{ width: 110 }}>{FEATURE_LABELS[k].toLowerCase()}{overrides[k] !== undefined ? " *" : ""}</td>
                            <td>
                              <input type="range" min={isTempo ? 40 : 0} max={isTempo ? 220 : 100} value={isTempo ? Math.round(val) : Math.round(val * 100)} onChange={(e) => setOverride(k, isTempo ? Number(e.target.value) : Number(e.target.value) / 100)} aria-label={FEATURE_LABELS[k]} />
                              <div className="small row between"><span>{FEATURE_HINTS[k][0]}</span><span>{FEATURE_HINTS[k][1]}</span></div>
                            </td>
                            <td className="num" style={{ width: 70 }}>{isTempo ? Math.round(val) : `${Math.round(val * 100)}%`}</td>
                          </tr>
                        );
                      })}
                      <tr><td colSpan={3}><button onClick={() => setOverrides({})} disabled={!Object.keys(overrides).length}>reset to profile</button></td></tr>
                    </tbody>
                  </table>
                </div>
              </div>
            )}

            {mode === "lyrics" && (
              <div className="stack">
                <label className="field"><span className="label">theme (optional if you paste lyrics)</span>
                  <div className="row">
                    <input placeholder="e.g. leaving a city you loved" value={theme} onChange={(e) => setTheme(e.target.value)} maxLength={200} style={{ flex: 1, minWidth: 200 }} />
                    {llmOn && <button onClick={writeLyrics} disabled={writing || !theme.trim()}>{writing ? "writing…" : "write lyrics with claude"}</button>}
                  </div>
                </label>
                {!llmOn && <p className="small">without a claude key the template engine builds a simple verse/chorus from the theme.</p>}
                <label className="field"><span className="label">lyrics · {lyrics.length}/4096</span>
                  <textarea rows={10} value={lyrics} onChange={(e) => setLyrics(e.target.value)} maxLength={4096} placeholder={"[verse]\n…\n\n[chorus]\n…"} />
                </label>
                <p className="small">section tags: [intro] [verse] [pre-chorus] [chorus] [bridge] [outro]</p>
              </div>
            )}

            {mode === "fusion" && (
              <div className="stack">
                <p className="small">{fusionIds.length}/3 selected · last six months</p>
                {topArtists.length === 0 ? <Loading what="artists" /> : (
                  <div className="table-wrap">
                    <table>
                      <thead><tr><th>use</th><th>#</th><th>artist</th><th>genres</th></tr></thead>
                      <tbody>
                        {topArtists.map((a, i) => {
                          const on = fusionIds.includes(a.id);
                          return (
                            <tr key={a.id}>
                              <td><input type="checkbox" checked={on} disabled={!on && fusionIds.length >= 3} onChange={() => toggleFusion(a.id)} aria-label={`use ${a.name}`} /></td>
                              <td>{i + 1}</td>
                              <td>{a.name}</td>
                              <td className="small">{a.genres.slice(0, 3).join(", ")}</td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                )}
              </div>
            )}

            {mode === "brief" && (
              <label className="field"><span className="label">creative brief · {brief.length}/600</span>
                <textarea rows={4} value={brief} onChange={(e) => setBrief(e.target.value)} maxLength={600} placeholder="a scene, a feeling, a reference point. your profile still sets the sound." />
              </label>
            )}

            {mode === "festival" && (
              <div className="stack">
                <div className="row">
                  <input placeholder="acts, comma separated" value={festivalInput} onChange={(e) => setFestivalInput(e.target.value)} onKeyDown={(e) => e.key === "Enter" && addFestivalName()} style={{ flex: 1, minWidth: 200 }} aria-label="acts" />
                  <button onClick={addFestivalName}>add</button>
                </div>
                {festivalNames.length === 0 ? <p className="small">scan a poster on the scan page, or type the acts here. up to ten.</p> : (
                  <ul>
                    {festivalNames.map((n) => <li key={n}>{n} <button className="link" onClick={() => setFestivalNames((xs) => xs.filter((x) => x !== n))}>remove</button></li>)}
                  </ul>
                )}
              </div>
            )}
          </Section>

          <Section n="03" title="render settings">
            <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(170px, 1fr))" }}>
              <label className="field"><span className="label">preset</span>
                <select value={preset} onChange={(e) => setPreset(e.target.value)}>
                  <option value="">none</option>
                  {presets.map((p) => <option key={p.id} value={p.id}>{p.label.toLowerCase()} · {p.tempo} bpm</option>)}
                </select>
              </label>
              <label className="field"><span className="label">length · {fmtTime(duration)}</span>
                <input type="range" min={15} max={maxDur} step={5} value={duration} onChange={(e) => setDuration(Number(e.target.value))} />
              </label>
              <label className="field"><span className="label">takes</span>
                <select value={variations} onChange={(e) => setVariations(Number(e.target.value))}>
                  {Array.from({ length: maxVar }, (_, i) => i + 1).map((n) => <option key={n} value={n}>{n}</option>)}
                </select>
              </label>
              <div className="field"><span className="label">vocals</span>
                <label className="check"><input type="checkbox" checked={wantVocals} disabled={mode === "lyrics"} onChange={(e) => setVocals(e.target.checked)} /> {wantVocals ? "sung or rapped" : "instrumental"}{vocals === null ? " (auto)" : ""}</label>
              </div>
            </div>
            <div className="actions" style={{ marginTop: 12 }}>
              <button onClick={compose} disabled={busy || !!validation}>{stage === "composing" ? "composing…" : "preview brief"}</button>
              <button className="primary" onClick={() => generate(true)} disabled={busy || !!validation || !gpuOn}>{stage === "generating" ? "submitting…" : `generate${variations > 1 ? ` ${variations} takes` : ""}`}</button>
            </div>
            {validation && <p className="small" style={{ marginTop: 6 }}>{validation}</p>}
          </Section>
        </div>

        <div>
          <Section n="04" title="brief" right={composed ? `${engineLabel(composed.engine)} · ${composed.mode}` : undefined}>
            {stage === "composing" ? <Loading what={llmOn ? "claude is composing" : "composing"} /> : composed ? (
              <div className="stack">
                <label className="field"><span className="label">title</span><input value={edits.title ?? composed.title} onChange={(e) => setEdits((x) => ({ ...x, title: e.target.value }))} maxLength={80} /></label>
                <label className="field"><span className="label">style caption</span><textarea rows={4} value={edits.prompt ?? composed.prompt} onChange={(e) => setEdits((x) => ({ ...x, prompt: e.target.value }))} /></label>
                <div className="row">
                  <label className="field" style={{ flex: 1 }}><span className="label">bpm</span><input type="number" min={40} max={220} value={edits.bpm ?? composed.bpm} onChange={(e) => setEdits((x) => ({ ...x, bpm: Number(e.target.value) }))} /></label>
                  <label className="field" style={{ flex: 1 }}><span className="label">key</span><input value={edits.key_scale ?? composed.key_scale ?? ""} placeholder="F# minor" onChange={(e) => setEdits((x) => ({ ...x, key_scale: e.target.value }))} /></label>
                </div>
                <label className="field"><span className="label">lyrics</span>
                  <textarea rows={8} value={edits.lyrics ?? composed.lyrics} onChange={(e) => setEdits((x) => ({ ...x, lyrics: e.target.value }))} />
                </label>
                {composed.rationale && <p className="small">{composed.rationale}</p>}
                <div className="actions">
                  <button className="primary" onClick={() => generate(false)} disabled={busy || !gpuOn}>{stage === "generating" ? "submitting…" : `render this brief${variations > 1 ? ` × ${variations}` : ""}`}</button>
                  <button onClick={compose} disabled={busy}>recompose</button>
                  <button onClick={() => { setComposed(null); setEdits({}); setStage("idle"); }}>discard</button>
                </div>
              </div>
            ) : <div className="box">no brief yet. preview composes it without using the gpu; generate skips straight to audio.</div>}
          </Section>

          <Section n="05" title="session" right={results.length ? <button className="link" onClick={batches.clear}>clear</button> : undefined}>
            {batches.anyActive && (
              <div className="box">
                <div className="row between"><span className="b">rendering on ace-step</span><span className="small">{fmtTime(elapsed)}</span></div>
                <div className="progress" style={{ marginTop: 6 }}><i style={{ width: `${Math.min(95, (elapsed / 40) * 100)}%` }} /></div>
                <p className="small" style={{ marginTop: 6 }}>a 60-second take usually takes 20 to 40 seconds. leaving this page does not stop it.</p>
              </div>
            )}
            {results.length === 0 && !batches.anyActive ? <div className="box">{completed.length} ready. rendered takes appear here and in the library.</div> : (
              <div>
                {[...results].reverse().map((g) => (
                  <TrackCard key={g.generation_id} gen={g} queue={completed} onChange={batches.update} onDelete={removeResult} onToggleFavorite={favResult} />
                ))}
              </div>
            )}
          </Section>
        </div>
      </div>
    </div>
  );
}
