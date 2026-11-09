import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { api } from "../lib/api";
import type { Generation } from "../types";

export type PlayerTrack = Pick<Generation, "generation_id" | "title" | "audio_url" | "waveform" | "duration_seconds" | "mode" | "feature_type" | "engine" | "caption" | "download_url" | "is_favorite">;

type PlayerState = {
  current: PlayerTrack | null;
  queue: PlayerTrack[];
  playing: boolean;
  time: number;
  duration: number;
  volume: number;
  play: (track: PlayerTrack, queue?: PlayerTrack[]) => void;
  toggle: () => void;
  pause: () => void;
  seek: (seconds: number) => void;
  next: () => void;
  prev: () => void;
  setVolume: (v: number) => void;
  isCurrent: (id: number) => boolean;
  updateTrack: (patch: Partial<PlayerTrack> & { generation_id: number }) => void;
};

const PlayerContext = createContext<PlayerState | null>(null);

export function PlayerProvider({ children }: { children: React.ReactNode }) {
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const [current, setCurrent] = useState<PlayerTrack | null>(null);
  const [queue, setQueue] = useState<PlayerTrack[]>([]);
  const [playing, setPlaying] = useState(false);
  const [time, setTime] = useState(0);
  const [duration, setDuration] = useState(0);
  const [volume, setVolumeState] = useState<number>(() => {
    const v = Number(localStorage.getItem("trill.volume"));
    return isNaN(v) || v === 0 ? 0.9 : v;
  });
  const countedRef = useRef<Set<number>>(new Set());

  if (!audioRef.current && typeof window !== "undefined") {
    const el = new Audio();
    el.preload = "metadata";
    audioRef.current = el;
  }

  useEffect(() => {
    const el = audioRef.current!;
    el.volume = volume;
    const onTime = () => setTime(el.currentTime || 0);
    const onMeta = () => setDuration(isFinite(el.duration) ? el.duration : 0);
    const onPlay = () => setPlaying(true);
    const onPause = () => setPlaying(false);
    const onEnded = () => {
      setPlaying(false);
      nextRef.current();
    };
    el.addEventListener("timeupdate", onTime);
    el.addEventListener("loadedmetadata", onMeta);
    el.addEventListener("durationchange", onMeta);
    el.addEventListener("play", onPlay);
    el.addEventListener("pause", onPause);
    el.addEventListener("ended", onEnded);
    return () => {
      el.removeEventListener("timeupdate", onTime);
      el.removeEventListener("loadedmetadata", onMeta);
      el.removeEventListener("durationchange", onMeta);
      el.removeEventListener("play", onPlay);
      el.removeEventListener("pause", onPause);
      el.removeEventListener("ended", onEnded);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const load = useCallback((track: PlayerTrack, autoplay = true) => {
    const el = audioRef.current!;
    if (!track.audio_url) return;
    el.src = api.url(track.audio_url);
    setCurrent(track);
    setTime(0);
    setDuration(track.duration_seconds || 0);
    if (autoplay) {
      el.play().catch(() => setPlaying(false));
      if (!countedRef.current.has(track.generation_id)) {
        countedRef.current.add(track.generation_id);
        api.post(`/api/generate/${track.generation_id}/played`).catch(() => undefined);
      }
    }
  }, []);

  const play = useCallback(
    (track: PlayerTrack, q?: PlayerTrack[]) => {
      if (q) setQueue(q.filter((t) => t.audio_url));
      else setQueue((prev) => (prev.some((t) => t.generation_id === track.generation_id) ? prev : [...prev, track]));
      if (current?.generation_id === track.generation_id) {
        const el = audioRef.current!;
        if (el.paused) el.play().catch(() => undefined);
        else el.pause();
        return;
      }
      load(track, true);
    },
    [current, load]
  );

  const toggle = useCallback(() => {
    const el = audioRef.current!;
    if (!current) return;
    if (el.paused) el.play().catch(() => undefined);
    else el.pause();
  }, [current]);

  const pause = useCallback(() => audioRef.current?.pause(), []);

  const seek = useCallback((seconds: number) => {
    const el = audioRef.current!;
    el.currentTime = Math.max(0, Math.min(seconds, el.duration || seconds));
    setTime(el.currentTime);
  }, []);

  const step = useCallback(
    (dir: 1 | -1) => {
      if (!current || queue.length === 0) return;
      const idx = queue.findIndex((t) => t.generation_id === current.generation_id);
      const nextIdx = idx + dir;
      if (nextIdx < 0 || nextIdx >= queue.length) {
        if (dir === 1) setPlaying(false);
        return;
      }
      load(queue[nextIdx], true);
    },
    [current, queue, load]
  );
  const nextRef = useRef<() => void>(() => undefined);
  nextRef.current = () => step(1);

  const setVolume = useCallback((v: number) => {
    const clamped = Math.max(0, Math.min(1, v));
    setVolumeState(clamped);
    if (audioRef.current) audioRef.current.volume = clamped;
    localStorage.setItem("trill.volume", String(clamped));
  }, []);

  const updateTrack = useCallback((patch: Partial<PlayerTrack> & { generation_id: number }) => {
    setCurrent((c) => (c && c.generation_id === patch.generation_id ? { ...c, ...patch } : c));
    setQueue((q) => q.map((t) => (t.generation_id === patch.generation_id ? { ...t, ...patch } : t)));
  }, []);

  // Space toggles play when not typing
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      const tag = (e.target as HTMLElement)?.tagName;
      if (tag === "INPUT" || tag === "TEXTAREA" || (e.target as HTMLElement)?.isContentEditable) return;
      if (e.code === "Space" && current) {
        e.preventDefault();
        toggle();
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [current, toggle]);

  const value = useMemo<PlayerState>(
    () => ({
      current, queue, playing, time, duration, volume, play, toggle, pause, seek,
      next: () => step(1), prev: () => step(-1), setVolume,
      isCurrent: (id) => current?.generation_id === id,
      updateTrack,
    }),
    [current, queue, playing, time, duration, volume, play, toggle, pause, seek, step, setVolume, updateTrack]
  );

  return <PlayerContext.Provider value={value}>{children}</PlayerContext.Provider>;
}

export function usePlayer(): PlayerState {
  const ctx = useContext(PlayerContext);
  if (!ctx) throw new Error("usePlayer must be used inside PlayerProvider");
  return ctx;
}
