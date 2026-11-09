import { useCallback, useEffect, useRef, useState } from "react";
import { POLL_INTERVAL_MS } from "../config";
import { api } from "../lib/api";
import type { Generation } from "../types";

type BatchState = { batch_id: string; done: boolean; items: Generation[] };

/**
 * Polls one or more batches until every generation in them has finished.
 * Items are kept in submission order and merged into a single flat list.
 */
export function useBatches() {
  const [batches, setBatches] = useState<Record<string, BatchState>>({});
  const timers = useRef<Record<string, number>>({});

  const stop = useCallback((id: string) => {
    if (timers.current[id]) {
      window.clearTimeout(timers.current[id]);
      delete timers.current[id];
    }
  }, []);

  const poll = useCallback(
    async (id: string) => {
      try {
        const data = await api.get<BatchState>(`/api/generate/batch/${id}`);
        setBatches((b) => ({ ...b, [id]: data }));
        if (!data.done) timers.current[id] = window.setTimeout(() => void poll(id), POLL_INTERVAL_MS);
        else stop(id);
      } catch (e: any) {
        if (e?.status === 404) {
          stop(id);
          setBatches((b) => { const { [id]: _omit, ...rest } = b; return rest; });
          return;
        }
        timers.current[id] = window.setTimeout(() => void poll(id), POLL_INTERVAL_MS * 2);
      }
    },
    [stop]
  );

  const track = useCallback(
    (batch_id: string, items: Generation[]) => {
      setBatches((b) => ({ ...b, [batch_id]: { batch_id, done: false, items } }));
      stop(batch_id);
      timers.current[batch_id] = window.setTimeout(() => void poll(batch_id), 1200);
    },
    [poll, stop]
  );

  const update = useCallback((g: Generation) => {
    setBatches((b) => {
      if (!g.batch_id || !b[g.batch_id]) return b;
      return { ...b, [g.batch_id]: { ...b[g.batch_id], items: b[g.batch_id].items.map((x) => (x.generation_id === g.generation_id ? g : x)) } };
    });
  }, []);

  const remove = useCallback((generation_id: number) => {
    setBatches((b) => {
      const out: Record<string, BatchState> = {};
      for (const [k, v] of Object.entries(b)) {
        const items = v.items.filter((x) => x.generation_id !== generation_id);
        if (items.length) out[k] = { ...v, items };
      }
      return out;
    });
  }, []);

  const clear = useCallback(() => {
    Object.keys(timers.current).forEach(stop);
    setBatches({});
  }, [stop]);

  useEffect(() => () => Object.keys(timers.current).forEach(stop), [stop]);

  const ordered = Object.values(batches);
  const items = ordered.flatMap((b) => b.items);
  const anyActive = items.some((g) => g.status === "pending" || g.status === "processing");
  return { batches: ordered, items, anyActive, track, update, remove, clear };
}
