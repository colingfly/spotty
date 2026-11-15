# backend/services/stems.py
"""
Stems for a finished track: vocals, drums, bass and other as WAV files.

Separation runs on a small Modal service (infra/modal_stems.py) that only wakes
when someone asks. It returns a zip; this module unpacks it, keeps the files in
the local cache and in durable storage, and records where they are in the
track's meta_json["stems"]:

    {"status": "processing" | "ready" | "failed", "base": "<file name stem>",
     "started": <unix time>, "error": "...", "files": {"vocals": {"path", "url"}, ...}}
"""
from __future__ import annotations

import logging
import os
import re
import shutil
import tempfile
import threading
import time
import zipfile
from typing import Any, Dict, Optional

import requests

from config import settings
from models import Generation
from services import storage

log = logging.getLogger("spotty.stems")

STEMS = ("vocals", "drums", "bass", "other")
STALE_AFTER_SECONDS = 15 * 60
_SAFE = re.compile(r"[^A-Za-z0-9 _.-]+")


def enabled() -> bool:
    return bool(settings.stems_api_url)


def base_name(gen: Generation) -> str:
    """File name stem a DAW user can read at a glance: title, tempo and key."""
    params = gen.params_json or {}
    meta = gen.meta_json or {}
    parts = [(_SAFE.sub("", gen.title or "") or f"trill-{gen.id}").strip()[:60]]
    if params.get("bpm"):
        parts.append(f"{int(params['bpm'])}bpm")
    key = params.get("key_scale") or meta.get("key_scale")
    if key:
        parts.append(str(key).replace(" major", "maj").replace(" minor", "min").replace("#", "sharp").replace(" ", ""))
    return "_".join(parts)


def state(gen: Generation) -> Optional[Dict[str, Any]]:
    """The stems record, with a job that outlived its worker (a redeploy) reported as failed."""
    s = (gen.meta_json or {}).get("stems")
    if not s:
        return None
    if s.get("status") == "processing" and time.time() - float(s.get("started") or 0) > STALE_AFTER_SECONDS:
        return {**s, "status": "failed", "error": "separation was interrupted; try again"}
    return s


def _dir(gen_id: int) -> str:
    return os.path.join(settings.audio_output_dir, "stems", str(gen_id))


def _save(db, gen: Generation, record: Dict[str, Any]) -> None:
    gen.meta_json = {**(gen.meta_json or {}), "stems": record}  # reassign so the JSON column is marked dirty
    db.add(gen)
    db.commit()


def begin(db, gen: Generation) -> Dict[str, Any]:
    """Mark the track as separating and start the job in the background."""
    record = {"status": "processing", "base": base_name(gen), "started": time.time()}
    _save(db, gen, record)
    threading.Thread(target=_run, args=(gen.id,), name=f"trill-stems-{gen.id}", daemon=True).start()
    return record


def _run(gen_id: int) -> None:
    from db import SessionLocal
    from services.generation_service import local_audio_path

    db = SessionLocal()
    try:
        gen = db.get(Generation, gen_id)
        record = dict((gen.meta_json or {}).get("stems") or {})
        try:
            src = local_audio_path(gen)
            if not src:
                raise RuntimeError("the track's audio is no longer available")
            record["files"] = _separate(gen_id, src, record.get("base") or f"trill-{gen_id}")
            record["status"] = "ready"
        except Exception as e:
            log.warning("Stems failed for %s: %s", gen_id, e)
            record.update({"status": "failed", "error": str(e)[:300]})
        db.refresh(gen)
        _save(db, gen, record)
    finally:
        db.close()


def _separate(gen_id: int, src: str, base: str) -> Dict[str, Dict[str, Optional[str]]]:
    headers = {"Authorization": f"Bearer {settings.acestep_api_key}"} if settings.acestep_api_key else {}
    out_dir = _dir(gen_id)
    os.makedirs(out_dir, exist_ok=True)
    with tempfile.NamedTemporaryFile(suffix=".zip", delete=False) as tmp:
        zip_path = tmp.name
    try:
        with open(src, "rb") as fp:
            # The service may be cold; the request is held while its container starts.
            r = requests.post(
                f"{settings.stems_api_url.rstrip('/')}/separate",
                files={"file": (os.path.basename(src), fp, "audio/mpeg")},
                data={"name": base},
                headers=headers,
                stream=True,
                timeout=(30, 840),
            )
        if r.status_code != 200:
            raise RuntimeError(f"stem service returned {r.status_code}: {r.text[:200]}")
        with open(zip_path, "wb") as fp:
            for chunk in r.iter_content(chunk_size=1 << 20):
                fp.write(chunk)

        files: Dict[str, Dict[str, Optional[str]]] = {}
        with zipfile.ZipFile(zip_path) as z:
            names = {n.rsplit("_", 1)[-1].rsplit(".", 1)[0]: n for n in z.namelist()}
            for stem in STEMS:
                if stem not in names:
                    raise RuntimeError(f"stem service did not return {stem}")
                path = os.path.join(out_dir, f"{stem}.wav")
                with z.open(names[stem]) as src_fp, open(path, "wb") as dst:
                    shutil.copyfileobj(src_fp, dst)
                with open(path, "rb") as fp:
                    url = storage.upload(f"stems/{gen_id}/{stem}.wav", fp.read(), content_type="audio/wav")
                files[stem] = {"path": path, "url": url}
        return files
    finally:
        try:
            os.remove(zip_path)
        except OSError:
            pass


def local_path(gen: Generation, stem: str) -> Optional[str]:
    """A stem's WAV on disk, restored from durable storage if the disk was wiped."""
    s = state(gen)
    info = ((s or {}).get("files") or {}).get(stem)
    if not s or s.get("status") != "ready" or not info:
        return None
    path = os.path.join(_dir(gen.id), f"{stem}.wav")
    if os.path.isfile(path) or (info.get("url") and storage.restore(info["url"], path)):
        return path
    return None


def delete(gen: Generation) -> None:
    for info in (((gen.meta_json or {}).get("stems") or {}).get("files") or {}).values():
        if info.get("url"):
            storage.delete(info["url"])
    shutil.rmtree(_dir(gen.id), ignore_errors=True)


def session_sheet(gen: Generation) -> str:
    """Plain-text notes that travel with the stems: what a producer needs to set up a DAW session."""
    params = gen.params_json or {}
    meta = gen.meta_json or {}
    key = params.get("key_scale") or meta.get("key_scale") or "not set"
    length = gen.duration_seconds or params.get("audio_duration") or 0
    lines = [
        f"title: {gen.title or 'untitled'}",
        f"tempo: {params.get('bpm', 'not set')} bpm",
        f"key: {key}",
        f"time signature: {params.get('time_signature', '4')}/4",
        f"length: {int(length // 60)}:{int(length % 60):02d}",
        f"model: {meta.get('model', 'ace-turbo')}",
        f"seed: {params.get('seed', 'not recorded')}",
        "",
        "files: vocals, drums, bass and other are 44.1 kHz WAV and sum to the mix.",
        "import all four at bar 1 with the session tempo set to the value above.",
        "",
        "caption:",
        gen.caption_used or "",
        "",
        "lyrics:",
        gen.lyrics_used or "[Instrumental]",
        "",
    ]
    return "\r\n".join(lines)  # CRLF so the sheet opens cleanly in Notepad
