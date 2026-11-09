import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { Heart, Search } from "lucide-react";
import TrackCard from "../components/TrackCard";
import { EmptyState, Modal, Skeleton } from "../components/ui";
import { useToast } from "../hooks/useToast";
import { api, qs } from "../lib/api";
import type { Generation, Mode, Paged } from "../types";
import { MODES, MODE_META } from "../types";

type Sort = "newest" | "oldest" | "plays";

export default function LibraryPage() {
  const toast = useToast();
  const [items, setItems] = useState<Generation[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [q, setQ] = useState("");
  const [debounced, setDebounced] = useState("");
  const [fav, setFav] = useState(false);
  const [mode, setMode] = useState<Mode | "">("");
  const [sort, setSort] = useState<Sort>("newest");
  const [confirm, setConfirm] = useState<Generation | null>(null);

  useEffect(() => {
    const id = window.setTimeout(() => setDebounced(q.trim()), 250);
    return () => window.clearTimeout(id);
  }, [q]);

  const load = useCallback(async (silent = false) => {
    if (!silent) setLoading(true);
    try {
      const r = await api.get<Paged<Generation>>(`/api/generate/history${qs({ limit: 100, q: debounced, favorites: fav, mode, sort })}`);
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
      replace({ ...g, is_favorite: !g.is_favorite });
      const u = await api.post<Generation>(`/api/generate/${g.generation_id}/favorite`);
      replace(u);
      if (fav && !u.is_favorite) setItems((xs) => xs.filter((x) => x.generation_id !== u.generation_id));
    } catch (e: any) {
      replace(g);
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
      toast.success("Track deleted.");
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  const queue = useMemo(() => items.filter((g) => g.status === "completed" && g.audio_url), [items]);

  return (
    <div className="page">
      <div className="page-head">
        <div>
          <h1 className="page-title">Library</h1>
          <p className="page-sub">{total} track{total === 1 ? "" : "s"}{fav ? " in favorites" : ""}. Press <span className="kbd">space</span> to pause and resume.</p>
        </div>
      </div>

      <div className="row row-wrap" style={{ marginBottom: 18, gap: 10 }}>
        <div className="search" style={{ flex: "1 1 260px" }}>
          <Search size={15} />
          <input className="input" placeholder="Search titles, captions, lyrics" value={q} onChange={(e) => setQ(e.target.value)} />
        </div>
        <button className={`chip ${fav ? "active" : ""}`} onClick={() => setFav((f) => !f)}><Heart size={13} fill={fav ? "currentColor" : "none"} /> Favorites</button>
        <div className="row row-wrap" style={{ gap: 6 }}>
          <button className={`chip ${mode === "" ? "active" : ""}`} onClick={() => setMode("")}>All</button>
          {MODES.map((m) => <button key={m} className={`chip ${mode === m ? "active" : ""}`} onClick={() => setMode(mode === m ? "" : m)}>{MODE_META[m].short}</button>)}
        </div>
        <select className="select" style={{ width: "auto" }} value={sort} onChange={(e) => setSort(e.target.value as Sort)} aria-label="Sort">
          <option value="newest">Newest</option>
          <option value="oldest">Oldest</option>
          <option value="plays">Most played</option>
        </select>
      </div>

      {loading ? (
        <div className="grid grid-cards">{Array.from({ length: 6 }).map((_, i) => <Skeleton key={i} h={150} r={14} />)}</div>
      ) : items.length === 0 ? (
        <EmptyState
          title={debounced || fav || mode ? "Nothing matches" : "No tracks yet"}
          body={debounced || fav || mode ? "Try clearing the filters." : "Head to the Studio and make the first one."}
          action={!debounced && !fav && !mode ? <Link to="/studio" className="btn btn-primary">Open Studio</Link> : undefined}
        />
      ) : (
        <div className="grid grid-cards">
          {items.map((g) => (
            <TrackCard key={g.generation_id} gen={g} queue={queue} onChange={replace} onDelete={setConfirm} onToggleFavorite={toggleFav} />
          ))}
        </div>
      )}

      <Modal open={!!confirm} onClose={() => setConfirm(null)} title="Delete this track?"
        footer={<><button className="btn btn-ghost" onClick={() => setConfirm(null)}>Keep it</button><button className="btn btn-danger" onClick={doDelete}>Delete</button></>}>
        “{confirm?.title || "Untitled"}” and its audio file will be removed. This can't be undone.
      </Modal>
    </div>
  );
}
