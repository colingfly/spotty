import { useCallback, useRef, useState } from "react";
import { API_BASE } from "../config";
import type { Generation } from "../types";

type GenStatus = "idle" | "submitting" | "generating" | "complete" | "error";

export function useGeneration() {
  const [status, setStatus] = useState<GenStatus>("idle");
  const [generation, setGeneration] = useState<Generation | null>(null);
  const [error, setError] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const stopPolling = useCallback(() => {
    if (pollRef.current) {
      clearInterval(pollRef.current);
      pollRef.current = null;
    }
  }, []);

  const generate = useCallback(
    async (endpoint: string, body: Record<string, any>) => {
      stopPolling();
      setStatus("submitting");
      setError(null);
      setGeneration(null);

      try {
        const res = await fetch(`${API_BASE}${endpoint}`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await res.json();

        if (!res.ok) {
          setError(data?.message || data?.detail || "Generation request failed");
          setStatus("error");
          return;
        }

        setGeneration(data as Generation);
        setStatus("generating");

        // Poll every 3 seconds
        pollRef.current = setInterval(async () => {
          try {
            const pollRes = await fetch(
              `${API_BASE}/api/generate/status/${data.generation_id}`
            );
            const pollData = await pollRes.json();

            if (pollData.status === "completed") {
              setGeneration(pollData as Generation);
              setStatus("complete");
              stopPolling();
            } else if (pollData.status === "failed") {
              setError("Generation failed");
              setStatus("error");
              stopPolling();
            }
          } catch {
            // Silently retry on network error
          }
        }, 3000);
      } catch (e: any) {
        setError(e?.message || "Network error");
        setStatus("error");
      }
    },
    [stopPolling]
  );

  const reset = useCallback(() => {
    stopPolling();
    setStatus("idle");
    setGeneration(null);
    setError(null);
  }, [stopPolling]);

  return { status, generation, error, generate, reset };
}
