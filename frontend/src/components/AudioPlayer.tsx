import React, { useRef, useState, useEffect } from "react";
import { API_BASE } from "../config";

type Props = {
  audioUrl: string | null;
  title?: string;
};

export default function AudioPlayer({ audioUrl, title }: Props) {
  const audioRef = useRef<HTMLAudioElement>(null);
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [playing, setPlaying] = useState(false);
  const [currentTime, setCurrent] = useState(0);
  const [duration, setDuration] = useState(0);
  const analyserRef = useRef<AnalyserNode | null>(null);
  const animRef = useRef<number>(0);

  const fullUrl = audioUrl ? `${API_BASE}${audioUrl}` : null;

  useEffect(() => {
    return () => {
      cancelAnimationFrame(animRef.current);
    };
  }, []);

  const togglePlay = () => {
    const audio = audioRef.current;
    if (!audio) return;
    if (playing) {
      audio.pause();
    } else {
      audio.play();
      startVisualization();
    }
    setPlaying(!playing);
  };

  const startVisualization = () => {
    const audio = audioRef.current;
    const canvas = canvasRef.current;
    if (!audio || !canvas) return;

    if (!analyserRef.current) {
      const ctx = new AudioContext();
      const source = ctx.createMediaElementSource(audio);
      const analyser = ctx.createAnalyser();
      analyser.fftSize = 256;
      source.connect(analyser);
      analyser.connect(ctx.destination);
      analyserRef.current = analyser;
    }

    const analyser = analyserRef.current;
    const bufferLength = analyser.frequencyBinCount;
    const dataArray = new Uint8Array(bufferLength);
    const canvasCtx = canvas.getContext("2d")!;
    const WIDTH = canvas.width;
    const HEIGHT = canvas.height;

    const draw = () => {
      animRef.current = requestAnimationFrame(draw);
      analyser.getByteFrequencyData(dataArray);

      canvasCtx.fillStyle = "#111";
      canvasCtx.fillRect(0, 0, WIDTH, HEIGHT);

      const barWidth = (WIDTH / bufferLength) * 2.5;
      let x = 0;

      for (let i = 0; i < bufferLength; i++) {
        const barHeight = (dataArray[i] / 255) * HEIGHT;
        const g = Math.floor((dataArray[i] / 255) * 185 + 70);
        canvasCtx.fillStyle = `rgb(29, ${g}, 84)`;
        canvasCtx.fillRect(x, HEIGHT - barHeight, barWidth, barHeight);
        x += barWidth + 1;
      }
    };
    draw();
  };

  const formatTime = (s: number) => {
    const m = Math.floor(s / 60);
    const sec = Math.floor(s % 60);
    return `${m}:${sec.toString().padStart(2, "0")}`;
  };

  if (!fullUrl) return null;

  return (
    <div
      style={{
        background: "#111",
        borderRadius: 12,
        padding: 16,
        marginTop: 16,
      }}
    >
      {title && (
        <div
          style={{
            color: "#fff",
            fontSize: 14,
            fontWeight: 600,
            marginBottom: 8,
          }}
        >
          {title}
        </div>
      )}

      <canvas
        ref={canvasRef}
        width={500}
        height={80}
        style={{
          width: "100%",
          height: 80,
          borderRadius: 8,
          marginBottom: 8,
        }}
      />

      <div
        style={{
          display: "flex",
          alignItems: "center",
          gap: 12,
        }}
      >
        <button
          onClick={togglePlay}
          style={{
            background: "#1db954",
            border: "none",
            borderRadius: "50%",
            width: 40,
            height: 40,
            cursor: "pointer",
            display: "flex",
            alignItems: "center",
            justifyContent: "center",
            color: "white",
            fontSize: 18,
          }}
        >
          {playing ? "||" : "\u25B6"}
        </button>

        <span style={{ color: "#aaa", fontSize: 13, fontFamily: "monospace" }}>
          {formatTime(currentTime)} / {formatTime(duration)}
        </span>

        <input
          type="range"
          min={0}
          max={duration || 0}
          value={currentTime}
          onChange={(e) => {
            const t = parseFloat(e.target.value);
            if (audioRef.current) audioRef.current.currentTime = t;
            setCurrent(t);
          }}
          style={{ flex: 1, accentColor: "#1db954" }}
        />
      </div>

      <audio
        ref={audioRef}
        src={fullUrl}
        onTimeUpdate={() => setCurrent(audioRef.current?.currentTime || 0)}
        onLoadedMetadata={() => setDuration(audioRef.current?.duration || 0)}
        onEnded={() => {
          setPlaying(false);
          cancelAnimationFrame(animRef.current);
        }}
        crossOrigin="anonymous"
      />
    </div>
  );
}
