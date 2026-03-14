# backend/services/acestep_client.py
"""
Client for communicating with the ACE-Step 1.5 REST API server.
ACE-Step runs as a separate process on a configurable port (default 8001).
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional
from urllib.parse import quote

import requests

from config import settings

log = logging.getLogger("spotty.acestep")


class ACEStepClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.acestep_api_url).rstrip("/")

    def health_check(self) -> bool:
        try:
            r = requests.get(f"{self.base_url}/health", timeout=3)
            return r.ok
        except Exception:
            return False

    def submit_task(self, params: Dict[str, Any]) -> str:
        """
        Submit a generation task to ACE-Step.

        params should include keys like:
        - prompt (caption)
        - lyrics
        - bpm
        - audio_duration
        - infer_steps
        - batch_size
        - task_type (default: "text2music")

        Returns the task_id string.
        """
        payload = {
            "task_type": params.get("task_type", "text2music"),
            "prompt": params.get("prompt", ""),
            "lyrics": params.get("lyrics", "[Instrumental]"),
            "bpm": params.get("bpm", 120),
            "audio_duration": params.get("audio_duration", 60),
            "inference_steps": params.get("infer_steps", 8),
            "batch_size": params.get("batch_size", 1),
        }

        # Pass through optional fields
        for key in ("key_scale", "time_signature", "src_audio_path",
                     "audio_cover_strength", "seed", "guidance_scale"):
            if key in params:
                payload[key] = params[key]

        log.info("Submitting ACE-Step task: %s", payload.get("prompt", "")[:80])

        r = requests.post(
            f"{self.base_url}/release_task",
            json=payload,
            timeout=30,
        )
        r.raise_for_status()
        data = r.json()

        task_id = data.get("data", {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in ACE-Step response: {data}")
        return task_id

    def query_result(self, task_id: str) -> Dict[str, Any]:
        """
        Poll for task result.

        Returns dict with:
        - status: 0 (pending), 1 (completed), 2 (failed)
        - result: JSON string with audio paths (when completed)
        """
        r = requests.post(
            f"{self.base_url}/query_result",
            json={"task_id_list": [task_id]},
            timeout=10,
        )
        r.raise_for_status()
        data = r.json()

        results = data.get("data", [])
        if not results:
            return {"status": 0, "task_id": task_id}
        return results[0]

    def get_audio_url(self, file_path: str) -> str:
        """Build the download URL for a generated audio file."""
        return f"{self.base_url}/v1/audio?path={quote(file_path)}"

    def download_audio(self, file_path: str) -> bytes:
        """Download a generated audio file as bytes."""
        url = self.get_audio_url(file_path)
        r = requests.get(url, timeout=60)
        r.raise_for_status()
        return r.content


# Module-level singleton
acestep = ACEStepClient()
