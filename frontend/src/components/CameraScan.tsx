import React, { useEffect, useRef, useState } from "react";
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
      setError(e?.message || "camera access failed. use upload instead.");
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
      if (!w || !h) throw new Error("camera not ready. try again.");
      canvas.width = w;
      canvas.height = h;
      const ctx = canvas.getContext("2d");
      if (!ctx) throw new Error("canvas not supported");
      ctx.drawImage(video, 0, 0, w, h);
      const blob: Blob = await new Promise((resolve, reject) => canvas.toBlob((b) => (b ? resolve(b) : reject(new Error("capture failed"))), "image/jpeg", 0.92));
      const form = new FormData();
      form.append("file", blob, "capture.jpg");
      const data = await api.post<any>("/api/scan", form);
      onResults(mapScanResults(data));
    } catch (e: any) {
      setError(e?.message || "capture failed");
    } finally {
      setScanning(false);
    }
  };

  return (
    <div className="stack">
      <video ref={videoRef} playsInline muted style={{ width: "100%", aspectRatio: "4 / 3", objectFit: "cover", border: "1px solid #fff", display: stream ? "block" : "none" }} />
      <canvas ref={canvasRef} style={{ display: "none" }} />
      <div className="actions">
        {!stream ? (
          <button onClick={startCamera} disabled={starting}>{starting ? "starting…" : "start camera"}</button>
        ) : (
          <>
            <button className="primary" onClick={captureAndScan} disabled={scanning}>{scanning ? "reading…" : "capture and scan"}</button>
            <button onClick={stopCamera}>stop camera</button>
          </>
        )}
      </div>
      {error && <p className="small">error: {error}</p>}
      <p className="small">aim straight on and fill the frame with the poster text.</p>
    </div>
  );
}
