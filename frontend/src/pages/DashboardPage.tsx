import React, { useCallback, useEffect, useState } from "react";
import { Link, useNavigate } from "react-router-dom";
import { ArrowRight, ExternalLink, RefreshCw, Sparkles } from "lucide-react";
import TasteRadar from "../components/TasteRadar";
import TrackCard from "../components/TrackCard";
import { PlaceholderArt, Skeleton } from "../components/ui";
import { useAuth } from "../hooks/useAuth";
import { useToast } from "../hooks/useToast";
import { api, qs } from "../lib/api";
import { fmtBpm, fmtPct, relativeTime } from "../lib/format";
import type { Artist, Generation, Narrative, Paged, Stats, TasteProfile, Track } from "../types";
import { AUDIO_FEATURES, FEATURE_LABELS } from "../types";

type Range = "short_term" | "medium_term" | "long_term";
const RANGES: { id: Range; label: string }[] = [
  { id: "short_term", label: "4 weeks" },
  { id: "medium_term", label: "6 months" },
  { id: "long_term", label: "All time" },
];

export default function DashboardPage() {
  const { me } = useAuth();
  const toast = useToast();
  const navigate = useNavigate();
  const [taste, setTaste] = useState<TasteProfile | null>(null);
  const [narrative, setNarrative] = useState<Narrative | null>(null);
  const [narrativeLoading, setNarrativeLoading] = useState(true);
  const [stats, setStats] = useState<Stats | null>(null);
  const [artists, setArtists] = useState<Artist[]>([]);
  const [tracks, setTracks] = useState<Track[]>([]);
  const [recent, setRecent] = useState<Generation[]>([]);
  const [range, setRange] = useState<Range>("medium_term");
  const [refreshing, setRefreshing] = useState(false);
  const [err, setErr] = useState<string | null>(null);

  const llmOn = !!me?.capabilities.llm.configured;

  const loadTaste = useCallback(async () => {
    try {
      const t = await api.get<TasteProfile>("/api/me/taste");
      setTaste(t);
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
    api.get<Paged<Track>>("/api/me/top-tracks?time_range=short_term&limit=8").then((r) => setTracks(r.items)).catch(() => undefined);
    api.get<Paged<Generation>>("/api/generate/history?limit=4&status=completed").then((r) => setRecent(r.items)).catch(() => undefined);
  }, [loadTaste, loadNarrative]);

  useEffect(() => {
    api.get<Paged<Artist>>(`/api/me/top-artists${qs({ time_range: range, limit: 18 })}`).then((r) => setArtists(r.items)).catch(() => undefined);
  }, [range]);

  const refreshProfile = async () => {
    setRefreshing(true);
    try {
      const t = await api.post<TasteProfile>("/api/me/taste/refresh");
      setTaste(t);
      toast.success("Profile rebuilt from your latest listening.");
      void loadNarrative(true);
    } catch (e: any) {
      toast.error(e.message);
    } finally {
      setRefreshing(false);
    }
  };

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">{me ? `Hey, ${me.display_name.split(" ")[0]}` : "Your sound"}</h1>
          <p className="page-sub">
            {taste?.updated_at ? `Profile built ${relativeTime(taste.updated_at)} from ${taste.top_artists.length} artists and ${taste.genres.length} genre tags.` : "Reading your Spotify history…"}
          </p>
        </div>
        <div className="row">
          <button className="btn btn-secondary" onClick={refreshProfile} disabled={refreshing}>
            <RefreshCw size={15} style={refreshing ? { animation: "spin 1s linear infinite" } : undefined} /> Rebuild profile
          </button>
          <Link to="/studio" className="btn btn-primary">Open Studio <ArrowRight size={16} /></Link>
        </div>
      </div>

      {err && <div className="alert alert-error" style={{ marginBottom: 16 }}>{err}</div>}

      <div className="grid" style={{ gridTemplateColumns: "minmax(0, 3fr) minmax(0, 2fr)", alignItems: "stretch" }}>
        {/* Sound DNA */}
        <div className="card card-glow" style={{ display: "flex", flexDirection: "column" }}>
          <div className="card-head">
            <div className="card-title"><Sparkles size={16} color="var(--violet-2)" /> Sound DNA</div>
            {llmOn && (
              <button className="btn btn-ghost btn-sm" onClick={() => void loadNarrative(true)} disabled={narrativeLoading}>Rewrite</button>
            )}
          </div>
          {narrativeLoading && !narrative ? (
            <div className="stack">
              <Skeleton h={28} w="60%" />
              <Skeleton h={14} /><Skeleton h={14} /><Skeleton h={14} w="80%" />
              <div className="row row-wrap" style={{ marginTop: 6 }}><Skeleton h={26} w={90} r={999} /><Skeleton h={26} w={120} r={999} /><Skeleton h={26} w={70} r={999} /></div>
            </div>
          ) : narrative ? (
            <>
              <h2 style={{ fontSize: 26, fontWeight: 800, marginBottom: 6 }}>{narrative.headline}</h2>
              <div className="tiny" style={{ color: "var(--violet-2)", fontWeight: 600, marginBottom: 12 }}>{narrative.persona}</div>
              <p className="muted" style={{ fontSize: 15, lineHeight: 1.6 }}>{narrative.summary}</p>
              <div className="genre-cloud" style={{ marginTop: 14 }}>
                {narrative.signature_sounds.map((s) => <span key={s} className="chip chip-xs ai active">{s}</span>)}
                {narrative.eras.map((s) => <span key={s} className="chip chip-xs">{s}</span>)}
              </div>
              {narrative.suggested_modes.length > 0 && (
                <div style={{ marginTop: 16 }}>
                  <div className="section-title" style={{ marginBottom: 8 }}>Try next</div>
                  <div className="stack" style={{ gap: 6 }}>
                    {narrative.suggested_modes.map((s) => <div key={s} className="small muted">· {s}</div>)}
                  </div>
                </div>
              )}
            </>
          ) : (
            <div className="stack" style={{ flex: 1, justifyContent: "center" }}>
              <h2 style={{ fontSize: 22 }}>{taste?.genres.slice(0, 3).map((g) => g).join(" · ") || "Your profile"}</h2>
              <p className="muted small">
                {llmOn
                  ? "Claude hasn't written your profile yet. It will appear here on the next load."
                  : "Set ANTHROPIC_API_KEY on the backend and Claude will write a short, specific read of your taste here, and compose every track brief."}
              </p>
              {taste && (
                <div className="genre-cloud">
                  {taste.genre_weights.slice(0, 10).map((g) => <span key={g.genre} className="chip chip-xs">{g.genre}</span>)}
                </div>
              )}
            </div>
          )}
        </div>

        {/* Radar */}
        <div className="card" style={{ display: "flex", flexDirection: "column", alignItems: "center" }}>
          <div className="card-head" style={{ width: "100%" }}>
            <div className="card-title">Taste radar</div>
            <span className="tiny dim">{taste ? fmtBpm(taste.tempo) : ""}</span>
          </div>
          {taste ? <TasteRadar features={taste} size={300} /> : <Skeleton w={260} h={260} r={130} />}
        </div>
      </div>

      {/* Stats + feature bars */}
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-head"><div className="card-title">Eight dimensions</div></div>
          <div className="stack" style={{ gap: 10 }}>
            {AUDIO_FEATURES.map((k) => {
              const v = taste?.[k];
              const pct = k === "tempo" ? (v ? Math.min(1, Math.max(0, (v - 40) / 180)) : 0) : v || 0;
              return (
                <div key={k} className="feature-bar">
                  <span className="muted">{FEATURE_LABELS[k]}</span>
                  <div className="bar"><i style={{ width: `${pct * 100}%` }} /></div>
                  <span className="mono tiny dim" style={{ textAlign: "right" }}>{k === "tempo" ? Math.round(v || 0) : fmtPct(v)}</span>
                </div>
              );
            })}
          </div>
        </div>
        <div className="stack">
          <div className="grid grid-2">
            <div className="card card-sm stat"><span className="stat-value">{stats?.completed ?? "–"}</span><span className="stat-label">Tracks made</span></div>
            <div className="card card-sm stat"><span className="stat-value">{stats?.favorites ?? "–"}</span><span className="stat-label">Favorites</span></div>
            <div className="card card-sm stat"><span className="stat-value">{stats ? stats.minutes_generated : "–"}</span><span className="stat-label">Minutes of audio</span></div>
            <div className="card card-sm stat"><span className="stat-value">{stats?.plays ?? "–"}</span><span className="stat-label">Plays</span></div>
          </div>
          <div className="card card-sm">
            <div className="section-title">Weighted genres</div>
            <div className="genre-cloud">
              {taste ? taste.genre_weights.slice(0, 14).map((g, i) => (
                <span key={g.genre} className={`chip chip-xs ${i < 3 ? "active" : ""}`} title={`${Math.round(g.weight * 100)}% of your profile`}>{g.genre}</span>
              )) : <Skeleton h={24} />}
            </div>
          </div>
        </div>
      </div>

      {/* Top artists */}
      <div className="card" style={{ marginTop: 16 }}>
        <div className="card-head">
          <div className="card-title">Top artists</div>
          <div className="segmented">
            {RANGES.map((r) => <button key={r.id} className={range === r.id ? "active" : ""} onClick={() => setRange(r.id)}>{r.label}</button>)}
          </div>
        </div>
        <div className="grid grid-auto" style={{ gap: 10 }}>
          {artists.length === 0 ? Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} h={170} r={14} />) : artists.map((a, i) => (
            <a key={a.id} className="artist-tile" href={a.external_url || "#"} target="_blank" rel="noreferrer" title={`Open ${a.name} on Spotify`}>
              {a.image ? <img src={a.image} alt={a.name} loading="lazy" /> : <PlaceholderArt size={28} />}
              <span className="rank">#{i + 1}</span>
              <div className="overlay">
                <div className="name truncate">{a.name}</div>
                <div className="genres truncate">{a.genres.slice(0, 2).join(", ") || " "}</div>
              </div>
            </a>
          ))}
        </div>
        <div className="row" style={{ marginTop: 14, justifyContent: "flex-end" }}>
          <button className="btn btn-ai btn-sm" onClick={() => navigate("/studio?mode=fusion")}><Sparkles size={14} /> Fuse two of these</button>
        </div>
      </div>

      {/* Recent obsessions + latest tracks */}
      <div className="grid grid-2" style={{ marginTop: 16 }}>
        <div className="card">
          <div className="card-head"><div className="card-title">On repeat lately</div><span className="tiny dim">last 4 weeks</span></div>
          {tracks.length === 0 ? <p className="small dim">No recent top tracks from Spotify.</p> : (
            <div className="stack" style={{ gap: 8 }}>
              {tracks.map((t) => (
                <a key={t.id} href={t.external_url || "#"} target="_blank" rel="noreferrer" className="row" style={{ color: "inherit", textDecoration: "none" }}>
                  <div style={{ width: 40, height: 40, borderRadius: 8, overflow: "hidden", flexShrink: 0 }}>
                    {t.image ? <img src={t.image} alt="" loading="lazy" style={{ width: "100%", height: "100%", objectFit: "cover" }} /> : <PlaceholderArt />}
                  </div>
                  <div style={{ minWidth: 0, flex: 1 }}>
                    <div className="truncate" style={{ fontWeight: 600, fontSize: 14 }}>{t.name}</div>
                    <div className="truncate tiny dim">{t.artists.join(", ")}</div>
                  </div>
                  <ExternalLink size={14} className="dim" />
                </a>
              ))}
            </div>
          )}
        </div>
        <div className="card">
          <div className="card-head"><div className="card-title">Latest from the studio</div><Link to="/library" className="small">Library →</Link></div>
          {recent.length === 0 ? (
            <div className="stack" style={{ alignItems: "flex-start" }}>
              <p className="small dim">Nothing generated yet.</p>
              <Link to="/studio" className="btn btn-primary btn-sm">Make your first track</Link>
            </div>
          ) : (
            <div className="stack" style={{ gap: 8 }}>
              {recent.map((g) => <TrackCard key={g.generation_id} gen={g} queue={recent} compact showCaption={false} />)}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
