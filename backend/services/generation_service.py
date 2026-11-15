# backend/services/generation_service.py
"""
Everything that touches Generation rows: submitting batches to ACE-Step,
syncing their status, saving audio, and serializing for the API.
Shared by the HTTP routes and the background worker so the two never drift.
"""
from __future__ import annotations

import logging
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List, Optional

from sqlalchemy.orm import Session

from config import settings
from models import Generation
from services.acestep_client import STATUS_COMPLETED, STATUS_FAILED, acestep
from services.auth_tokens import audio_url_for
from services.caption_engine import MODE_TO_FEATURE_TYPE, ComposeResult
from services.engines import Engine, SongModel, get_model
from services import media, storage

log = logging.getLogger("spotty.generation")

ACTIVE_STATUSES = ("pending", "processing")
STALE_AFTER = timedelta(minutes=30)

# Render backends by name. Values are looked up at call time so tests can swap the module-level client.
ENGINES: Dict[str, Any] = {"acestep": lambda: acestep}


def engine_for(gen: Generation) -> Engine:
    model = get_model((gen.meta_json or {}).get("model"))
    return ENGINES[model.engine]()


# Rows waiting for a sleeping serverless GPU carry this prefix instead of an ACE-Step task id.
QUEUED_PREFIX = "queued:"


def new_seed() -> int:
    return int.from_bytes(os.urandom(4), "big") >> 1  # 31 bits: safe for every engine


def compose_result_from(gen: Generation) -> ComposeResult:
    """Rebuild the brief a finished row was rendered from, for retakes."""
    params = gen.params_json or {}
    meta = gen.meta_json or {}
    return ComposeResult(
        title=gen.title or "untitled",
        prompt=gen.caption_used or params.get("prompt") or "",
        lyrics=gen.lyrics_used or params.get("lyrics") or "[Instrumental]",
        bpm=int(params.get("bpm") or 120),
        duration=int(params.get("audio_duration") or settings.default_duration_seconds),
        key_scale=params.get("key_scale") or meta.get("key_scale"),
        tags=list(meta.get("tags") or []),
        rationale=meta.get("rationale") or "",
        engine=gen.engine or "template",
        features=dict(meta.get("features") or {}),
        mode=meta.get("mode") or "taste",
        preset=meta.get("preset"),
    )


class SourceAudioMissing(RuntimeError):
    pass


def source_files(db: Session, params: Dict[str, Any]) -> Dict[str, tuple]:
    """
    Audio an edit task needs, loaded at submit time. Rows keep only references
    (a trill track id or a stored upload) so a queued submit can rebuild them later.
    """
    files: Dict[str, tuple] = {}
    src_id = params.get("src_generation_id")
    if src_id:
        src = db.get(Generation, int(src_id))
        path = local_audio_path(src) if src else None
        if not path:
            raise SourceAudioMissing("The original track's audio is no longer available")
        with open(path, "rb") as fp:
            files["src_audio"] = (f"{src_id}.mp3", fp.read())
    upload = params.get("src_upload")
    if upload:
        data = storage.read(upload.get("path") or "", upload.get("url"))
        if data is None:
            raise SourceAudioMissing("The reference track is no longer available; upload it again")
        files["src_audio"] = (upload.get("name") or "reference.mp3", data)
    return files


def _submit(engine: Engine, db: Session, params: Dict[str, Any]) -> str:
    files = source_files(db, params)
    wire = {k: v for k, v in params.items() if k not in ("src_generation_id", "src_upload")}
    return engine.submit_task(wire, files=files) if files else engine.submit_task(wire)


def engine_available() -> bool:
    """Whether a render can be accepted. A serverless engine is always wakeable."""
    return settings.acestep_serverless or acestep.health_check()


def wake_engine() -> None:
    """Any request starts a sleeping serverless container; fire one without blocking the caller."""
    if settings.acestep_serverless:
        threading.Thread(target=acestep.health_check, kwargs={"max_age": 0}, daemon=True).start()


# Per-generation locks so the worker and a client poll never download the same file twice.
_sync_locks: Dict[int, threading.Lock] = {}
_sync_locks_guard = threading.Lock()


def _lock_for(gen_id: int) -> threading.Lock:
    with _sync_locks_guard:
        lock = _sync_locks.get(gen_id)
        if lock is None:
            lock = threading.Lock()
            _sync_locks[gen_id] = lock
        return lock


# --------------------------------------------------------------------------
# Submit
# --------------------------------------------------------------------------

def submit_batch(
    db: Session,
    sid: str,
    composed: ComposeResult,
    variations: int = 1,
    meta: Optional[Dict[str, Any]] = None,
    model: Optional[SongModel] = None,
    seed: Optional[int] = None,
    extra_params: Optional[Dict[str, Any]] = None,
) -> List[Generation]:
    """Submit N independent render tasks for one brief and persist a row per task."""
    model = model or get_model(None)
    engine: Engine = ENGINES[model.engine]()
    variations = max(1, min(settings.max_variations, int(variations or 1)))
    batch_id = uuid.uuid4().hex[:12]
    params = {**composed.to_acestep_params(), **model.engine_params(), **(extra_params or {})}
    params["audio_duration"] = min(int(params["audio_duration"]), model.max_duration)
    rows: List[Generation] = []

    for i in range(variations):
        p = dict(params)
        # Every take records its seed so it can be reproduced or refined later.
        p["seed"] = int(seed) if seed is not None and i == 0 else new_seed()
        if settings.acestep_serverless and not engine.health_check():
            # Submitting into a cold start would hold this request for minutes; the worker submits it instead.
            task_id = f"{QUEUED_PREFIX}{uuid.uuid4().hex}"
        else:
            task_id = _submit(engine, db, p)
        gen = Generation(
            spotify_user_id=sid,
            task_id=task_id,
            status="pending",
            feature_type=MODE_TO_FEATURE_TYPE.get(composed.mode, composed.mode),
            engine=composed.engine,
            batch_id=batch_id,
            variation_index=i,
            caption_used=composed.prompt,
            lyrics_used=composed.lyrics,
            params_json=p,
            meta_json={
                **(meta or {}),
                "mode": composed.mode,
                "model": model.id,
                "preset": composed.preset,
                "tags": composed.tags,
                "rationale": composed.rationale,
                "key_scale": composed.key_scale,
                "features": composed.features,
            },
            title=composed.title if variations == 1 else f"{composed.title} (take {i + 1})",
        )
        db.add(gen)
        rows.append(gen)

    db.commit()
    for gen in rows:
        db.refresh(gen)
    return rows


# --------------------------------------------------------------------------
# Sync
# --------------------------------------------------------------------------

def _is_stale(gen: Generation) -> bool:
    created = gen.created_at
    if created and not created.tzinfo:
        created = created.replace(tzinfo=timezone.utc)
    return bool(created and datetime.now(timezone.utc) - created > STALE_AFTER)


def submit_queued(db: Session, gen: Generation) -> bool:
    """Hand a queued row to ACE-Step once it answers. Returns True if the row changed."""
    if not (gen.task_id or "").startswith(QUEUED_PREFIX) or gen.status not in ACTIVE_STATUSES:
        return False
    # Only submit to a server that just answered: a submit that times out client-side during a
    # cold start may still be delivered later, and the retry would render the track twice.
    engine = engine_for(gen)
    if not engine.health_check(max_age=2.0):
        if not _is_stale(gen):
            return False
        gen.status = "failed"
        gen.error_message = "The GPU server did not start in time"
        gen.completed_at = datetime.now(timezone.utc)
    else:
        try:
            gen.task_id = _submit(engine, db, dict(gen.params_json or {}))
        except SourceAudioMissing as e:
            gen.status = "failed"
            gen.error_message = str(e)
            gen.completed_at = datetime.now(timezone.utc)
        except Exception as e:
            log.warning("Queued submit failed for %s: %s", gen.id, e)
            return False
    db.add(gen)
    db.commit()
    db.refresh(gen)
    return True


def _save_audio(gen: Generation, file_ref: str) -> None:
    audio_bytes = engine_for(gen).download(file_ref)
    os.makedirs(settings.audio_output_dir, exist_ok=True)
    local_path = os.path.join(settings.audio_output_dir, f"{gen.id}.mp3")
    with open(local_path, "wb") as fp:
        fp.write(audio_bytes)
    gen.audio_path = local_path
    gen.audio_blob_url = storage.upload(f"audio/{gen.id}.mp3", audio_bytes)
    log.info("Saved audio for generation %s (%d bytes)", gen.id, len(audio_bytes))
    try:
        duration, peaks = media.analyze(local_path)
        gen.duration_seconds = duration
        gen.waveform_json = peaks
    except Exception as e:  # pragma: no cover
        log.debug("media analysis failed: %s", e)


def apply_result(db: Session, gen: Generation, result: Dict[str, Any]) -> Generation:
    """Apply one ACE-Step poll result to a row. Idempotent."""
    if gen.status in ("completed", "failed"):
        return gen

    status_code = result.get("status", 0)
    if status_code == STATUS_COMPLETED:
        paths = acestep.extract_file_paths(result)
        if paths:
            try:
                _save_audio(gen, paths[0])
                gen.status = "completed"
            except Exception as e:
                log.warning("Audio download failed for %s: %s", gen.id, e)
                gen.status = "failed"
                gen.error_message = f"audio_download_failed: {e}"[:500]
        else:
            gen.status = "failed"
            gen.error_message = "ACE-Step completed without an audio file"
        gen.completed_at = datetime.now(timezone.utc)
    elif status_code == STATUS_FAILED:
        gen.status = "failed"
        gen.error_message = acestep.extract_error(result)
        gen.completed_at = datetime.now(timezone.utc)
    else:
        if gen.status == "pending":
            gen.status = "processing"
        # Give up on tasks ACE-Step never finishes
        created = gen.created_at if gen.created_at and gen.created_at.tzinfo else (gen.created_at.replace(tzinfo=timezone.utc) if gen.created_at else None)
        if created and datetime.now(timezone.utc) - created > STALE_AFTER:
            gen.status = "failed"
            gen.error_message = "Timed out waiting for ACE-Step"
            gen.completed_at = datetime.now(timezone.utc)

    db.add(gen)
    db.commit()
    db.refresh(gen)
    return gen


def sync_generation(db: Session, gen: Generation) -> Generation:
    """Poll ACE-Step for one row if it is still active."""
    if gen.status not in ACTIVE_STATUSES:
        return gen
    lock = _lock_for(gen.id)
    if not lock.acquire(blocking=False):
        return gen  # someone else is syncing it right now
    try:
        db.refresh(gen)
        if gen.status not in ACTIVE_STATUSES:
            return gen
        if gen.task_id.startswith(QUEUED_PREFIX):
            submit_queued(db, gen)
            return gen
        try:
            result = engine_for(gen).query_result(gen.task_id)
        except Exception as e:
            log.debug("ACE-Step poll failed for %s: %s", gen.id, e)
            return gen
        return apply_result(db, gen, result)
    finally:
        lock.release()


def sync_active(db: Session, limit: int = 50) -> int:
    """Used by the worker: batch-poll every active generation. Returns count updated."""
    active = (
        db.query(Generation)
        .filter(Generation.status.in_(ACTIVE_STATUSES))
        .order_by(Generation.created_at.asc())
        .limit(limit)
        .all()
    )
    updated = 0
    for gen in [g for g in active if g.task_id.startswith(QUEUED_PREFIX)]:
        lock = _lock_for(gen.id)
        if lock.acquire(blocking=False):
            try:
                updated += int(submit_queued(db, gen))
            finally:
                lock.release()
    active = [g for g in active if not g.task_id.startswith(QUEUED_PREFIX)]
    if not active:
        return updated
    results: Dict[str, Dict[str, Any]] = {}
    by_engine: Dict[str, List[Generation]] = {}
    for gen in active:
        by_engine.setdefault(get_model((gen.meta_json or {}).get("model")).engine, []).append(gen)
    for name, gens in by_engine.items():
        try:
            results.update(ENGINES[name]().query_results([g.task_id for g in gens]))
        except Exception as e:
            log.debug("Batch poll failed for %s: %s", name, e)
    for gen in active:
        res = results.get(gen.task_id)
        if res is None:
            continue
        lock = _lock_for(gen.id)
        if not lock.acquire(blocking=False):
            continue
        try:
            before = gen.status
            apply_result(db, gen, res)
            if gen.status != before:
                updated += 1
        finally:
            lock.release()
    return updated


def local_audio_path(gen: Generation) -> Optional[str]:
    """Path to the track's audio on disk, restoring it from durable storage if the disk was wiped."""
    if not gen.audio_path:
        return None
    if os.path.isfile(gen.audio_path):
        return gen.audio_path
    # The stored path may be from a previous deploy's filesystem; rebuild it under the current output dir.
    path = os.path.join(settings.audio_output_dir, f"{gen.id}.mp3")
    if os.path.isfile(path) or (gen.audio_blob_url and storage.restore(gen.audio_blob_url, path)):
        return path
    return None


# --------------------------------------------------------------------------
# Serialize
# --------------------------------------------------------------------------

def _stems_view(gen: Generation) -> Optional[Dict[str, Any]]:
    """What the client needs to know about stems: status and download links, never storage locations."""
    from services import stems

    s = stems.state(gen)
    if not s:
        return None
    view: Dict[str, Any] = {"status": s.get("status"), "error": s.get("error")}
    if s.get("status") == "ready":
        token = audio_url_for(gen.id).split("?", 1)[1]
        view["files"] = {name: f"/api/stems/{gen.id}/{name}?{token}" for name in (s.get("files") or {})}
        view["zip"] = f"/api/stems/{gen.id}/all?{token}"
    return view


def serialize(gen: Generation) -> Dict[str, Any]:
    meta = {k: v for k, v in (gen.meta_json or {}).items() if k != "stems"}
    return {
        "generation_id": gen.id,
        "task_id": gen.task_id,
        "status": gen.status,
        "error": gen.error_message,
        "feature_type": gen.feature_type,
        "mode": meta.get("mode"),
        "model": get_model(meta.get("model")).id,
        "stems": _stems_view(gen),
        "engine": gen.engine,
        "batch_id": gen.batch_id,
        "variation_index": gen.variation_index,
        "caption": gen.caption_used,
        "lyrics": gen.lyrics_used,
        "params": gen.params_json,
        "meta": meta,
        "audio_url": audio_url_for(gen.id) if gen.audio_path else None,
        "download_url": f"{audio_url_for(gen.id)}&download=1" if gen.audio_path else None,
        "duration_seconds": gen.duration_seconds,
        "waveform": gen.waveform_json,
        "title": gen.title,
        "is_favorite": bool(gen.is_favorite),
        "play_count": gen.play_count or 0,
        "created_at": gen.created_at.isoformat() if gen.created_at else None,
        "completed_at": gen.completed_at.isoformat() if gen.completed_at else None,
    }
