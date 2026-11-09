# backend/services/media.py
"""
Post-processing for generated audio: duration and a compact waveform
envelope the player renders without decoding the file client-side.
Every step is best-effort; failures return None rather than raising.
"""
from __future__ import annotations

import logging
from typing import List, Optional, Tuple

log = logging.getLogger("spotty.media")

WAVEFORM_BUCKETS = 96


def mp3_duration(path: str) -> Optional[float]:
    try:
        from mutagen import File as MutagenFile  # type: ignore

        mf = MutagenFile(path)
        if mf is not None and mf.info is not None and getattr(mf.info, "length", None):
            return float(mf.info.length)
    except Exception as e:  # pragma: no cover - depends on local codecs
        log.debug("mutagen duration failed: %s", e)
    return None


def _load_mono(path: str):
    """Return (samples, sr) using soundfile, then librosa as a fallback."""
    try:
        import soundfile as sf  # type: ignore

        data, sr = sf.read(path, dtype="float32", always_2d=True)
        return data.mean(axis=1), sr
    except Exception as e:
        log.debug("soundfile load failed: %s", e)
    try:
        import librosa  # type: ignore

        y, sr = librosa.load(path, sr=11025, mono=True)
        return y, sr
    except Exception as e:
        log.debug("librosa load failed: %s", e)
    return None, None


def waveform_peaks(path: str, buckets: int = WAVEFORM_BUCKETS) -> Optional[List[float]]:
    y, sr = _load_mono(path)
    if y is None or len(y) == 0:
        return None
    try:
        import numpy as np

        n = len(y)
        edges = np.linspace(0, n, buckets + 1, dtype=int)
        peaks = []
        for i in range(buckets):
            seg = y[edges[i]: edges[i + 1]]
            peaks.append(float(np.sqrt(np.mean(np.square(seg)))) if len(seg) else 0.0)
        mx = max(peaks) or 1.0
        return [round(p / mx, 3) for p in peaks]
    except Exception as e:
        log.debug("waveform failed: %s", e)
        return None


def analyze(path: str) -> Tuple[Optional[float], Optional[List[float]]]:
    duration = mp3_duration(path)
    peaks = waveform_peaks(path)
    if duration is None and peaks is not None:
        y, sr = _load_mono(path)
        if y is not None and sr:
            duration = float(len(y) / sr)
    return duration, peaks
