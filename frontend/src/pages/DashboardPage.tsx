import React, { useCallback, useEffect, useState } from "react";
import { Link } from "react-router-dom";
import TasteRadar from "../components/TasteRadar";
import TrackCard from "../components/TrackCard";
import { Loading, Section, Thumb } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { api, qs } from "../lib/api";
import { fmtPct, relativeTime } from "../lib/format";
import type { Artist, Generation, Narrative, Paged, Stats, TasteProfile, Track } from "../types";
import { AUDIO_FEATURES, FEATURE_HINTS, FEATURE_LABELS } from "../types";

type Range = "short_term" | "medium_term" | "long_term";
const RANGES: { id: Range; label: string }[] = [
  { id: "short_term", label: "last 4 weeks" },
  { id: "medium_term", label: "last 6 months" },
  { id: "long_term", label: "all time" },
];

export default function DashboardPage() {
  const { me } = useAuth();
  const toast = useToast();
  const [taste, setTaste] = useState<TasteProfile | null>(null);
  const [narrative, setNarrative] = useState<Narrative | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(true);
  const [stats, setStats] = useState<Stats | null>(null);
  const [artists, setArtists] = useState<Artist[] | null>(null);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [recent, setRecent] = useState<Generation[]>([]);
  const [range, setRange] = useState<Range>("medium_term");
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const llmOn = !!me?.capabilities.llm.configured;

  const loadTaste = useCallback(async () => {
    try {
      setTaste(await api.get<TasteProfile>("/api/me/taste"));
      setErr(null);
    } catch (e: any) {
      setErr(e.message);
    }
  }, []);

  const loadNarrative = useCallback(async (force = false) => {
    setNarrativeLoading(true);
    try {
      const r = await api.get<{ narrative: Narrative | null }>(`/api/me/insights${qs({ refresh: force })}`);
      setNarrative(r.narrative);
    } catch {
      /* non-fatal */
    } finally {
      setNarrativeLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadTaste();
    void loadNarrative();
    api.get<Stats>("/api/me/stats").then(setStats).catch(() => undefined);
    api.get<Paged<Track>>("/api/me/top-tracks?time_range=short_term&limit=10").then((r) => setTracks(r.items)).catch(() => undefined);
    api.get<Paged<Generation>>("/api/generate/history?limit=5&status=completed").then((r) => setRecent(r.items)).catch(() => undefined);
  }, [loadTaste, loadNarrative]);

  useEffect(() => {
    setArtists(null);
    api.get<Paged<Artist>>(`/api/me/top-artists${qs({ time_range: range, limit: 20 })}`).then((r) => setArtists(r.items)).catch(() => setArtists([]));
  }, [range]);

  const refreshProfile = async () => {
    setRefreshing(true);
    try {
      setTaste(await api.post<TasteProfile>("/api/me/taste/refresh"));
      toast.success("profile rebuilt from current spotify data.");
      void loadNarrative(true);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div>
      <h1>profile{me ? ` · ${me.display_name}` : ""}</h1>
      <p className="small">
        {taste?.updated_at ? `built ${relativeTime(taste.updated_at)} from ${taste.top_artists.length} artists and ${taste.genres.length} genre tags` : "reading spotify history…"}
      </p>
      {err && <p className="notice">error: {err}</p>}

      <Section n="01" title="taste profile" right={<button onClick={refreshProfile} disabled={refreshing}>{refreshing ? "rebuilding…" : "rebuild from spotify"}</button>}>
        <div className="cols">
          <div className="table-wrap">
            <table>
              <thead><tr><th>axis</th><th>low → high</th><th className="num">value</th></tr></thead>
              <tbody>
                {AUDIO_FEATURES.map((k) => (
                  <tr key={k}>
                    <td>{FEATURE_LABELS[k].toLowerCase()}</td>
                    <td className="small">{FEATURE_HINTS[k][0]} → {FEATURE_HINTS[k][1]}</td>
                    <td className="num">{taste ? (k === "tempo" ? `${Math.round(taste[k])} bpm` : fmtPct(taste[k])) : "…"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="box">{taste ? <TasteRadar features={taste} size={320} /> : <Loading what="profile" />}</div>
        </div>
      </Section>

      <Section n="02" title="sound dna" right={llmOn ? <button onClick={() => void loadNarrative(true)} disabled={narrativeLoading}>rewrite</button> : undefined}>
        <div className="box">
          {narrativeLoading && !narrative ? (
            <Loading what={llmOn ? "claude is writing" : "loading"} />
          ) : narrative ? (
            <div className="stack">
              <p className="b">{narrative.headline} · {narrative.persona}</p>
              <p>{narrative.summary}</p>
              <dl className="kv">
                <dt>signature sounds</dt><dd>{narrative.signature_sounds.join(", ")}</dd>
                <dt>eras</dt><dd>{narrative.eras.join(", ")}</dd>
                <dt>try next</dt><dd>{narrative.suggested_modes.map((s, i) => <div key={i}>{s}</div>)}</dd>
              </dl>
            </div>
          ) : (
            <p>{llmOn ? "not written yet. it appears on the next load." : "not available. set ANTHROPIC_API_KEY on the backend to enable the claude composer and this summary."}</p>
          )}
        </div>
      </Section>

      <Section n="03" title="genres" right={taste ? `${taste.genre_weights.length} weighted tags` : undefined}>
        {taste ? (
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>genre</th><th className="num">weight</th></tr></thead>
              <tbody>
                {taste.genre_weights.slice(0, 15).map((g, i) => (
                  <tr key={g.genre}><td>{i + 1}</td><td>{g.genre}</td><td className="num">{Math.round(g.weight * 100)}%</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : <Loading />}
      </Section>

      <Section n="04" title="top artists" right={
        <select value={range} onChange={(e) => setRange(e.target.value as Range)} aria-label="time range" style={{ width: "auto", minHeight: 36 }}>
          {RANGES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}
        </select>
      }>
        {artists === null ? <Loading what="artists" /> : artists.length === 0 ? <div className="box">spotify returned no artists.</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th></th><th>artist</th><th>genres</th><th className="num">popularity</th><th>link</th></tr></thead>
              <tbody>
                {artists.map((a, i) => (
                  <tr key={a.id}>
                    <td>{i + 1}</td>
                    <td><Thumb src={a.image} alt={a.name} /></td>
                    <td>{a.name}</td>
                    <td className="small">{a.genres.slice(0, 3).join(", ")}</td>
                    <td className="num">{a.popularity ?? "–"}</td>
                    <td>{a.external_url ? <a href={a.external_url} target="_blank" rel="noreferrer">spotify</a> : ""}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="small" style={{ marginTop: 8 }}><Link to="/studio?mode=fusion">fuse two of these in the studio</Link></p>
      </Section>

      <Section n="05" title="on repeat" right="last 4 weeks">
        {tracks.length === 0 ? <div className="box">no recent top tracks.</div> : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>#</th><th>track</th><th>artists</th><th>link</th></tr></thead>
              <tbody>
                {tracks.map((t, i) => (
                  <tr key={t.id}><td>{i + 1}</td><td>{t.name}</td><td className="small">{t.artists.join(", ")}</td><td>{t.external_url ? <a href={t.external_url} target="_blank" rel="noreferrer">spotify</a> : ""}</td></tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section n="06" title="library" right={<Link to="/library">open library</Link>}>
        <dl className="kv">
          <dt>tracks made</dt><dd>{stats?.completed ?? "…"}</dd>
          <dt>favorites</dt><dd>{stats?.favorites ?? "…"}</dd>
          <dt>minutes of audio</dt><dd>{stats ? stats.minutes_generated : "…"}</dd>
          <dt>plays</dt><dd>{stats?.plays ?? "…"}</dd>
          <dt>by mode</dt><dd>{stats ? Object.entries(stats.by_mode).map(([k, v]) => `${k} ${v}`).join(", ") || "–" : "…"}</dd>
          <dt>by composer</dt><dd>{stats ? Object.entries(stats.by_engine).map(([k, v]) => `${k === "llm" ? "claude" : k} ${v}`).join(", ") || "–" : "…"}</dd>
        </dl>
        {recent.length === 0 ? (
          <p style={{ marginTop: 8 }}>nothing generated yet. <Link to="/studio">open the studio</Link>.</p>
        ) : (
          <div style={{ marginTop: 8 }}>
            {recent.map((g) => <TrackCard key={g.generation_id} gen={g} queue={recent} compact />)}
          </div>
        )}
      </Section>
    </div>
  );
}
