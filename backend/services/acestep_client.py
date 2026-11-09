# backend/services/acestep_client.py
"""
Client for the ACE-Step 1.5 REST API (separate process, default port 8001).

Endpoints used:
  GET  /health
  POST /release_task      -> {"data": {"task_id": ...}}
  POST /query_result      -> {"data": [{"task_id", "status": 0|1|2, "result": "<json>"}]}
  GET  /v1/audio?path=... -> audio bytes
"""
from __future__ import annotations

import json
import logging
import threading
import time
from typing import Any, Dict, List, Optional
from urllib.parse import quote

import requests

from config import settings

log = logging.getLogger("spotty.acestep")

STATUS_PENDING = 0
STATUS_COMPLETED = 1
STATUS_FAILED = 2


class ACEStepClient:
    def __init__(self, base_url: Optional[str] = None):
        self.base_url = (base_url or settings.acestep_api_url).rstrip("/")
        self._health_cache: Optional[bool] = None
        self._health_checked_at = 0.0
        self._lock = threading.Lock()

    # --- health -----------------------------------------------------------

    def health_check(self, max_age: float = 5.0) -> bool:
        """Cached for a few seconds: the nav pings this every 30s and every submit checks it."""
        with self._lock:
            if self._health_cache is not None and time.time() - self._health_checked_at < max_age:
                return self._health_cache
        ok = False
        try:
            r = requests.get(f"{self.base_url}/health", timeout=3)
            ok = r.ok
        except Exception:
            ok = False
        with self._lock:
            self._health_cache = ok
            self._health_checked_at = time.time()
        return ok

    # --- tasks ------------------------------------------------------------

    def submit_task(self, params: Dict[str, Any]) -> str:
        payload = {
            "task_type": params.get("task_type", "text2music"),
            "prompt": params.get("prompt", ""),
            "lyrics": params.get("lyrics") or "[Instrumental]",
            "bpm": int(params.get("bpm", 120)),
            "audio_duration": int(params.get("audio_duration", settings.default_duration_seconds)),
            "inference_steps": int(params.get("infer_steps", settings.infer_steps)),
            "batch_size": int(params.get("batch_size", 1)),
        }
        for key in ("key_scale", "time_signature", "src_audio_path", "audio_cover_strength", "seed", "guidance_scale"):
            if params.get(key) is not None:
                payload[key] = params[key]

        log.info("ACE-Step submit: %s", payload["prompt"][:100])
        r = requests.post(f"{self.base_url}/release_task", json=payload, timeout=30)
        r.raise_for_status()
        data = r.json()
        task_id = (data.get("data") or {}).get("task_id")
        if not task_id:
            raise RuntimeError(f"No task_id in ACE-Step response: {data}")
        return str(task_id)

    def query_results(self, task_ids: List[str]) -> Dict[str, Dict[str, Any]]:
        """Poll several tasks at once. Returns {task_id: result_dict}."""
        if not task_ids:
            return {}
        r = requests.post(f"{self.base_url}/query_result", json={"task_id_list": task_ids}, timeout=10)
        r.raise_for_status()
        out: Dict[str, Dict[str, Any]] = {}
        for item in r.json().get("data", []) or []:
            tid = str(item.get("task_id") or "")
            if tid:
                out[tid] = item
        return out

    def query_result(self, task_id: str) -> Dict[str, Any]:
        res = self.query_results([task_id])
        return res.get(task_id) or {"status": STATUS_PENDING, "task_id": task_id}

    # --- results ----------------------------------------------------------

    @staticmethod
    def extract_file_paths(result: Dict[str, Any]) -> List[str]:
        """ACE-Step returns `result` as a JSON string: [{"file": "/v1/audio?path=...", ...}]."""
        raw = result.get("result", "")
        data: Any = raw
        if isinstance(raw, str):
            try:
                data = json.loads(raw) if raw else []
            except (json.JSONDecodeError, TypeError):
                log.warning("Could not parse ACE-Step result: %s", raw[:200])
                return []
        paths: List[str] = []
        items = data if isinstance(data, list) else [data]
        for it in items:
            if isinstance(it, dict) and it.get("file"):
                paths.append(str(it["file"]))
            elif isinstance(it, str) and it:
                paths.append(it)
        return paths

    @staticmethod
    def extract_error(result: Dict[str, Any]) -> str:
        for key in ("error", "message", "msg", "detail"):
            if result.get(key):
                return str(result[key])[:500]
        return "ACE-Step reported failure"

    def download(self, file_ref: str) -> bytes:
        """file_ref is either a URL path from the result ("/v1/audio?path=...") or a raw path."""
        if file_ref.startswith("/"):
            url = f"{self.base_url}{file_ref}"
        elif file_ref.startswith("http"):
            url = file_ref
        else:
            url = f"{self.base_url}/v1/audio?path={quote(file_ref)}"
        r = requests.get(url, timeout=120)
        r.raise_for_status()
        return r.content


acestep = ACEStepClient()
