import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Loading, Lyrics, Modal, engineLabel, modeLabel } from "../components/ui";
import { usePlayer } from "../hooks/usePlayer";
import { useToast } from "../hooks/useToast";
import { api, qs } from "../lib/api";
import { fmtTime, relativeTime } from "../lib/format";
import type { Generation, Mode, Paged } from "../types";
import { MODES, MODE_META } from "../types";

type Sort = "newest" | "oldest" | "plays";

export default function LibraryPage() {
  const toast = useToast();
  const player = usePlayer();
  const [items, setItems] = useState<Generation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [fav, setFav] = useState(false);
  const [mode, setMode] = useState<Mode | "">("");
  const [sort, setSort] = useState<Sort>("newest");
  const [confirm, setConfirm] = useState<Generation | null>(null);
  const [renaming, setRenaming] = useState<number | null>(null);
  const [title, setTitle] = useState("");

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(q.trim()), 250);
    return () => window.clearTimeout(id);
  }, [q]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const r = await api.get<Paged<Generation>>(`/api/generate/history${qs({ limit: 200, q: debounced, favorites: fav, mode, sort })}`);
      setItems(r.items);
      setTotal(r.total ?? r.items.length);
    } catch (e: any) {
      if (!silent) toast.error(e.message);
    } finally {
      setLoading(false);
    }
  }, [debounced, fav, mode, sort, toast]);

  useEffect(() => { void load(); }, [load]);

  const anyActive = items.some((g) => g.status === "pending" || g.status === "processing");
  useEffect(() => {
    if (!anyActive) return;
    const id = window.setInterval(() => void load(true), 4000);
    return () => window.clearInterval(id);
  }, [anyActive, load]);

  const replace = (g: Generation) => setItems((xs) => xs.map((x) => (x.generation_id === g.generation_id ? g : x)));

  const toggleFav = async (g: Generation) => {
    try {
      const u = await api.post<Generation>(`/api/generate/${g.generation_id}/favorite`);
      replace(u);
      if (fav && !u.is_favorite) setItems((xs) => xs.filter((x) => x.generation_id !== u.generation_id));
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const saveTitle = async (g: Generation) => {
    try {
      const u = await api.patch<Generation>(`/api/generate/${g.generation_id}`, { title });
      replace(u);
      player.updateTrack({ generation_id: g.generation_id, title: u.title });
      setRenaming(null);
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const doDelete = async () => {
    if (!confirm) return;
    const g = confirm;
    setConfirm(null);
    try {
      await api.del(`/api/generate/${g.generation_id}`);
      setItems((xs) => xs.filter((x) => x.generation_id !== g.generation_id));
      setTotal((t) => Math.max(0, t - 1));
      toast.success("deleted.");
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const queue = useMemo(() => items.filter((g) => g.status === "completed" && g.audio_url), [items]);

  return (
    <div>
      <h1>library</h1>
      <p className="small">{total} track{total === 1 ? "" : "s"}{fav ? " in favorites" : ""} · space pauses and resumes</p>

      <div className="grid" style={{ gridTemplateColumns: "repeat(auto-fit, minmax(200px, 1fr))", marginTop: 12 }}>
        <label className="field"><span className="label">search</span><input placeholder="title, caption, lyrics" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label className="field"><span className="label">mode</span>
          <select value={mode} onChange={(e) => setMode(e.target.value as Mode | "")}>
            <option value="">all</option>
            {MODES.map((m) => <option key={m} value={m}>{MODE_META[m].short.toLowerCase()}</option>)}
          </select>
        </label>
        <label className="field"><span className="label">sort</span>
          <select value={sort} onChange={(e) => setSort(e.target.value as Sort)}>
            <option value="newest">newest</option>
            <option value="oldest">oldest</option>
            <option value="plays">most played</option>
          </select>
        </label>
        <div className="field"><span className="label">filter</span><label className="check"><input type="checkbox" checked={fav} onChange={(e) => setFav(e.target.checked)} /> favorites only</label></div>
      </div>

      {loading ? <Loading what="library" /> : items.length === 0 ? (
        <div className="box" style={{ marginTop: 12 }}>
          {debounced || fav || mode ? "nothing matches these filters." : <>no tracks yet. <Link to="/studio">open the studio</Link>.</>}
        </div>
      ) : (
        <div className="table-wrap" style={{ marginTop: 12 }}>
          <table>
            <thead>
              <tr><th></th><th>title</th><th>mode</th><th>composer</th><th className="num">bpm</th><th className="num">length</th><th>created</th><th className="num">plays</th><th>status</th><th>actions</th></tr>
            </thead>
            <tbody>
              {items.map((g) => {
                const ready = g.status === "completed" && !!g.audio_url;
                const isCur = player.isCurrent(g.generation_id);
                const playing = isCur && player.playing;
                const bpm = (g.params as any)?.bpm;
                return (
                  <tr key={g.generation_id} style={isCur ? { outline: "2px solid #c9a7ff", outlineOffset: -2 } : undefined}>
                    <td><button onClick={() => player.play(g, queue)} disabled={!ready} style={{ minWidth: 70 }}>{playing ? "pause" : "play"}</button></td>
                    <td style={{ minWidth: 220 }}>
                      {renaming === g.generation_id ? (
                        <div className="row">
                          <input value={title} autoFocus maxLength={80} onChange={(e) => setTitle(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void saveTitle(g); if (e.key === "Escape") setRenaming(null); }} aria-label="title" />
                          <div className="actions"><button className="primary" onClick={() => void saveTitle(g)}>save</button><button onClick={() => setRenaming(null)}>cancel</button></div>
                        </div>
                      ) : (
                        <>
                          <div><span className="b break">{g.title || "untitled"}</span>{g.is_favorite ? " · favorite" : ""}</div>
                          {(g.caption || (g.lyrics && g.lyrics !== "[Instrumental]")) && (
                            <details className="inline">
                              <summary>brief</summary>
                              {g.caption && <div className="break small">{g.caption}</div>}
                              {g.lyrics && g.lyrics !== "[Instrumental]" && <div className="small"><Lyrics text={g.lyrics} /></div>}
                            </details>
                          )}
                        </>
                      )}
                    </td>
                    <td>{modeLabel(g)}</td>
                    <td>{engineLabel(g.engine)}</td>
                    <td className="num">{bpm ?? "–"}</td>
                    <td className="num">{g.duration_seconds ? fmtTime(g.duration_seconds) : "–"}</td>
                    <td className="nowrap">{relativeTime(g.created_at)}</td>
                    <td className="num">{g.play_count}</td>
                    <td>{g.status}{g.error ? <div className="small break">{g.error}</div> : null}</td>
                    <td>
                      <div className="actions">
                        <button aria-pressed={g.is_favorite} onClick={() => toggleFav(g)}>{g.is_favorite ? "unfav" : "fav"}</button>
                        <button onClick={() => { setTitle(g.title || ""); setRenaming(g.generation_id); }}>rename</button>
                        {g.download_url && <a className="btn" href={api.url(g.download_url)} download>mp3</a>}
                        <button onClick={() => setConfirm(g)}>delete</button>
                      </div>
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      )}

      <Modal open={!!confirm} onClose={() => setConfirm(null)} title="delete this track?"
        footer={<><button className="primary" onClick={doDelete}>delete</button><button onClick={() => setConfirm(null)}>keep</button></>}>
        "{confirm?.title || "untitled"}" and its audio file will be removed. this cannot be undone.
      </Modal>
    </div>
  );
}
