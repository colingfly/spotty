import React, { useCallback, useEffect, useMemo, useState } from "react";
import { Link, useNavigate, useParams } from "react-router-dom";
import TrackCard from "../components/TrackCard";
import { Loading, Section } from "../components/ui";
import { usePlayer } from "../hooks/usePlayer";
import { useToast } from "../hooks/useToast";
import { api } from "../lib/api";
import { fmtTime, relativeTime } from "../lib/format";
import type { Generation, Paged, Project, SongModel } from "../types";

export default function ProducerPage() {
  const { id } = useParams();
  return id ? <Workspace id={Number(id)} /> : <ProjectList />;
}

/** Start a project from a track, or reopen the one it already belongs to. */
export async function openProject(generationId: number): Promise<number> {
  const p = await api.post<Project>("/api/projects", { generation_id: generationId });
  return p.project_id;
}

function ProjectList() {
  const toast = useToast();
  const navigate = useNavigate();
  const [projects, setProjects] = useState<Project[] | null>(null);
  const [tracks, setTracks] = useState<Generation[]>([]);

  useEffect(() => {
    api.get<{ items: Project[] }>("/api/projects").then((r) => setProjects(r.items)).catch((e) => { toast.error(e.message); setProjects([]); });
    api.get<Paged<Generation>>("/api/generate/history?limit=30").then((r) => setTracks(r.items.filter((g) => g.status === "completed" && !g.project_id))).catch(() => undefined);
  }, [toast]);

  const start = async (g: Generation) => {
    try {
      navigate(`/producer/${await openProject(g.generation_id)}`);
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  return (
    <div>
      <h1>producer</h1>
      <p className="small">one project per song. every take, section edit and model swap is kept as a version you can compare and branch from.</p>

      <Section n="01" title="projects">
        {projects === null ? <Loading what="projects" /> : projects.length === 0 ? (
          <div className="box">no projects yet. start one from a track below.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>project</th><th className="num">versions</th><th>latest</th><th>worked on</th></tr></thead>
              <tbody>
                {projects.map((p) => (
                  <tr key={p.project_id}>
                    <td><Link to={`/producer/${p.project_id}`}>{p.name}</Link></td>
                    <td className="num">{p.versions}</td>
                    <td>{p.latest ? `${p.latest.title || "untitled"} · ${p.latest.status}` : "–"}</td>
                    <td className="nowrap">{p.updated_at ? relativeTime(p.updated_at) : "–"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>

      <Section n="02" title="start from a track">
        {tracks.length === 0 ? (
          <div className="box">no finished tracks outside a project. <Link to="/studio">render one in the studio</Link>.</div>
        ) : (
          <div className="table-wrap">
            <table>
              <thead><tr><th>title</th><th className="num">length</th><th>created</th><th></th></tr></thead>
              <tbody>
                {tracks.map((g) => (
                  <tr key={g.generation_id}>
                    <td className="break">{g.title || "untitled"}</td>
                    <td className="num">{g.duration_seconds ? fmtTime(g.duration_seconds) : "–"}</td>
                    <td className="nowrap">{relativeTime(g.created_at)}</td>
                    <td><button onClick={() => void start(g)}>open as project</button></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Section>
    </div>
  );
}

type Detail = Project & { items: Generation[] };

function describe(g: Generation, byId: Map<number, Generation>, index: number): string {
  const edit = (g.meta as any)?.edit as { start: number; end: number } | undefined;
  if (edit) return `edit ${fmtTime(edit.start)}–${fmtTime(edit.end)}`;
  if ((g.meta as any)?.reference) return "from a reference track";
  const parent = g.parent_id ? byId.get(g.parent_id) : undefined;
  if (parent) return parent.model !== g.model ? `same take on ${(g.model || "").replace(/^ace-/, "").replace(/-/g, " ")}` : "new take";
  return index === 0 ? "original" : "new render";
}

function Workspace({ id }: { id: number }) {
  const toast = useToast();
  const player = usePlayer();
  const navigate = useNavigate();
  const [detail, setDetail] = useState<Detail | null>(null);
  const [missing, setMissing] = useState(false);
  const [a, setA] = useState<number | null>(null);
  const [b, setB] = useState<number | null>(null);
  const [models, setModels] = useState<SongModel[]>([]);
  const [name, setName] = useState<string | null>(null);

  const load = useCallback(async () => {
    try {
      const d = await api.get<Detail>(`/api/projects/${id}`);
      setDetail(d);
      setA((cur) => cur ?? [...d.items].reverse().find((g) => g.status === "completed")?.generation_id ?? d.items[0]?.generation_id ?? null);
    } catch (e: any) {
      if (e.status === 404) setMissing(true);
      else toast.error(e.message);
    }
  }, [id, toast]);

  useEffect(() => { void load(); }, [load]);
  useEffect(() => {
    api.get<{ models?: SongModel[] }>("/api/generate/presets").then((r) => setModels(r.models ?? [])).catch(() => undefined);
  }, []);

  const items = detail?.items ?? [];
  const working = items.some((g) => g.status === "pending" || g.status === "processing" || g.stems?.status === "processing");
  useEffect(() => {
    if (!working) return;
    const t = window.setInterval(() => void load(), 4000);
    return () => window.clearInterval(t);
  }, [working, load]);

  const byId = useMemo(() => new Map(items.map((g) => [g.generation_id, g])), [items]);
  const depth = useCallback((g: Generation) => {
    let d = 0;
    for (let p = g.parent_id ? byId.get(g.parent_id) : undefined; p && d < 12; p = p.parent_id ? byId.get(p.parent_id) : undefined) d++;
    return d;
  }, [byId]);
  // Children sit under their parent so the history reads as a tree.
  const ordered = useMemo(() => {
    const out: Generation[] = [];
    const walk = (parent: number | null) => items.filter((g) => (g.parent_id && byId.has(g.parent_id) ? g.parent_id : null) === parent).forEach((g) => { out.push(g); walk(g.generation_id); });
    walk(null);
    return out;
  }, [items, byId]);
  const numberOf = useMemo(() => new Map(items.map((g, i) => [g.generation_id, i + 1])), [items]);

  const act = async (label: string, path: string, body?: unknown) => {
    try {
      const r = await api.post<{ items?: Generation[] } | Generation>(path, body);
      const made = (r as any).items?.[0] as Generation | undefined;
      if (made) setA(made.generation_id);
      toast.success(label);
      await load();
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const replace = (g: Generation) => setDetail((d) => (d ? { ...d, items: d.items.map((x) => (x.generation_id === g.generation_id ? g : x)) } : d));

  const xl = models.find((m) => m.tier !== "free");
  const cardProps = {
    queue: items.filter((g) => g.status === "completed"),
    onChange: replace,
    onRetake: (g: Generation, opts: { same_seed?: boolean; model?: string }) => void act(opts.model ? "rendering the same take on another model." : "rendering a new take.", `/api/generate/${g.generation_id}/retake`, opts),
    onRepaint: (g: Generation, opts: { start: number; end: number; lyrics?: string }) => act(`re-rendering ${fmtTime(opts.start)}–${fmtTime(opts.end)}.`, `/api/generate/${g.generation_id}/repaint`, opts),
    onStems: (g: Generation) => void act("separating stems.", `/api/generate/${g.generation_id}/stems`),
    upgradeModel: xl ? { id: xl.id, label: xl.label.toLowerCase() } : undefined,
  };

  const va = a ? byId.get(a) : undefined;
  const vb = b ? byId.get(b) : undefined;
  const canSwap = !!va && !!vb && va.status === "completed" && vb.status === "completed";
  const swap = () => {
    if (!va || !vb) return;
    const at = player.time;
    const target = player.isCurrent(va.generation_id) ? vb : va;
    player.play(target, [va, vb]);
    window.setTimeout(() => player.seek(at), 350);  // wait for the new audio to load before seeking
  };

  const saveName = async () => {
    if (name === null) return;
    try {
      const p = await api.patch<Project>(`/api/projects/${id}`, { name });
      setDetail((d) => (d ? { ...d, name: p.name } : d));
      setName(null);
    } catch (e: any) {
      toast.error(e.message);
    }
  };
  const remove = async () => {
    try {
      await api.del(`/api/projects/${id}`);
      toast.success("project removed. its tracks are still in the library.");
      navigate("/producer");
    } catch (e: any) {
      toast.error(e.message);
    }
  };

  if (missing) return <div><h1>producer</h1><div className="box">that project does not exist. <Link to="/producer">back to projects</Link>.</div></div>;
  if (!detail) return <Loading what="project" />;

  return (
    <div>
      <p className="small"><Link to="/producer">projects</Link> / {detail.name}</p>
      {name === null ? (
        <h1>{detail.name}</h1>
      ) : (
        <div className="row">
          <input value={name} autoFocus maxLength={80} aria-label="project name" onChange={(e) => setName(e.target.value)} onKeyDown={(e) => { if (e.key === "Enter") void saveName(); if (e.key === "Escape") setName(null); }} />
          <div className="actions"><button className="primary" onClick={() => void saveName()}>save</button><button onClick={() => setName(null)}>cancel</button></div>
        </div>
      )}
      <div className="actions" style={{ marginTop: 8 }}>
        {name === null && <button onClick={() => setName(detail.name)}>rename project</button>}
        <Link className="btn" to={`/studio?project=${id}`}>new render in this project</Link>
        <button onClick={() => void remove()}>remove project</button>
      </div>

      <div className="cols split">
        <div>
          <Section n="01" title="versions" right={working ? "working…" : `${items.length} version${items.length === 1 ? "" : "s"}`}>
            <div className="table-wrap">
              <table>
                <thead><tr><th>a</th><th>b</th><th>version</th><th>model</th><th className="num">seed</th><th>status</th><th>made</th></tr></thead>
                <tbody>
                  {ordered.map((g) => (
                    <tr key={g.generation_id} style={g.generation_id === a ? { outline: "2px solid #c9a7ff", outlineOffset: -2 } : undefined}>
                      <td><input type="radio" name="version-a" checked={a === g.generation_id} onChange={() => { setA(g.generation_id); if (b === g.generation_id) setB(null); }} aria-label={`select version ${numberOf.get(g.generation_id)}`} /></td>
                      <td><input type="checkbox" checked={b === g.generation_id} disabled={a === g.generation_id} onChange={(e) => setB(e.target.checked ? g.generation_id : null)} aria-label={`compare version ${numberOf.get(g.generation_id)}`} /></td>
                      <td style={{ paddingLeft: 10 + depth(g) * 16 }}>
                        <span className="b">v{numberOf.get(g.generation_id)}</span> · {describe(g, byId, items.indexOf(g))}
                        {g.stems?.status === "ready" ? " · stems" : ""}
                      </td>
                      <td>{(g.model || "").replace(/^ace-/, "").replace(/-/g, " ")}</td>
                      <td className="num">{typeof (g.params as any)?.seed === "number" ? (g.params as any).seed : "–"}</td>
                      <td>{g.status}</td>
                      <td className="nowrap">{relativeTime(g.created_at)}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <p className="small">a is the version you are working on. tick b on another version to compare the two.</p>
          </Section>
        </div>

        <div>
          <Section n="02" title={va ? `version ${numberOf.get(va.generation_id)}` : "version"}>
            {va ? <TrackCard key={va.generation_id} gen={va} {...cardProps} /> : <div className="box">pick a version.</div>}
          </Section>
          {vb && (
            <Section n="03" title={`compare with version ${numberOf.get(vb.generation_id)}`} right={<button onClick={swap} disabled={!canSwap}>switch a/b at this position</button>}>
              <TrackCard key={vb.generation_id} gen={vb} {...cardProps} />
            </Section>
          )}
        </div>
      </div>
    </div>
  );
}
