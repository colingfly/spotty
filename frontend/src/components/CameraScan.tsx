import React, { useEffect, useRef, useState } from "react";
import { Camera, CameraOff, Sparkles } from "lucide-react";
import { api } from "../lib/api";
import type { ScanArtist } from "../types";
import { mapScanResults } from "../pages/ScanPage";

type Props = { onResults: (artists: ScanArtist[]) => void };

export default function CameraScan({ onResults }: Props) {
  const videoRef = useRef<HTMLVideoElement | null>(null);
  const canvasRef = useRef<HTMLCanvasElement | null>(null);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [starting, setStarting] = useState(false);
  const [scanning, setScanning] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const startCamera = async () => {
    if (starting || stream) return;
    setError(null);
    setStarting(true);
    try {
      const media = await navigator.mediaDevices.getUserMedia({ video: { facingMode: { ideal: "environment" } }, audio: false });
      setStream(media);
      if (videoRef.current) {
        videoRef.current.srcObject = media;
        await videoRef.current.play();
      }
    } catch (e: any) {
      setError(e?.message || "Camera access failed. Use upload instead.");
    } finally {
      setStarting(false);
    }
  };

  const stopCamera = () => {
    stream?.getTracks().forEach((t) => t.stop());
    setStream(null);
    if (videoRef.current) videoRef.current.srcObject = null;
  };

  useEffect(() => () => { stream?.getTracks().forEach((t) => t.stop()); }, [stream]);

  const captureAndScan = async () => {
    const video = videoRef.current;
    const canvas = canvasRef.current;
    if (!video || !canvas) return;
    setScanning(true);
    setError(null);
    try {
      const w = video.videoWidth;
      const h = video.videoHeight;
      if (!w || !h) throw new Error("Camera not ready. Try again.");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("Canvas not supported");
      ctx.drawImage(video, 0, 0, w, h);
      const blob: Blob = await new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("Capture failed"))), "image/jpeg", 0.92));
      const form = new FormData();
      form.append("file", blob, "capture.jpg");
      const data = await api.post<any>("/api/scan", form);
      onResults(mapScanResults(data));
    } catch (e: any) {
      setError(e?.message || "Capture failed");
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="stack">
      <div style={{ borderRadius: 14, overflow: "hidden", background: "#000", aspectRatio: "4 / 3", display: "grid", placeItems: "center" }}>
        <video ref={videoRef} playsInline muted style={{ width: "100%", height: "100%", objectFit: "cover", display: stream ? "block" : "none" }} />
        {!stream && <Camera size={28} className="dim" />}
        <canvas ref={canvasRef} style={{ display: "none" }} />
      </div>
      <div className="row">
        {!stream ? (
          <button className="btn btn-secondary" onClick={startCamera} disabled={starting}><Camera size={15} /> {starting ? "Starting…" : "Start camera"}</button>
        ) : (
          <>
            <button className="btn btn-primary" onClick={captureAndScan} disabled={scanning}>{scanning ? <span className="spinner" /> : <Sparkles size={15} />} {scanning ? "Reading…" : "Capture and scan"}</button>
            <button className="btn btn-ghost" onClick={stopCamera}><CameraOff size={15} /> Stop</button>
          </>
        )}
      </div>
      {error && <div className="alert alert-error">{error}</div>}
      <p className="tiny dim">Aim straight on and fill the frame with the poster text. Avoid glare and blur.</p>
    </div>
  );
}
