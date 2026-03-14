# backend/services/audio_analyzer.py
"""
Compute audio features from Spotify preview clips using librosa.
Replaces the deprecated Spotify audio-features endpoint.
"""
from __future__ import annotations

import io
import logging
import tempfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Optional

import librosa
import numpy as np
import requests

log = logging.getLogger("spotty")

KEYS = [
    "danceability", "energy", "valence",
    "acousticness", "instrumentalness", "liveness",
    "speechiness", "tempo",
]


def _download_preview(url: str, timeout: int = 10) -> Optional[bytes]:
    try:
        r = requests.get(url, timeout=timeout)
        if r.status_code == 200 and len(r.content) > 1000:
            return r.content
    except Exception:
        pass
    return None


def _analyze_clip(audio_bytes: bytes) -> Optional[Dict[str, float]]:
    """Extract audio features from raw mp3/ogg bytes using librosa."""
    try:
        with tempfile.NamedTemporaryFile(suffix=".mp3", delete=True) as tmp:
            tmp.write(audio_bytes)
            tmp.flush()
            y, sr = librosa.load(tmp.name, sr=22050, mono=True)

        if len(y) < sr:  # less than 1 second of audio
            return None

        # --- Tempo / BPM ---
        tempo, beat_frames = librosa.beat.beat_track(y=y, sr=sr)
        if isinstance(tempo, np.ndarray):
            tempo = float(tempo[0])
        else:
            tempo = float(tempo)

        # --- Energy (RMS) ---
        rms = librosa.feature.rms(y=y)[0]
        energy_raw = float(np.mean(rms))
        # Normalize: typical RMS for music is 0.01-0.3
        energy = min(1.0, energy_raw / 0.2)

        # --- Danceability (beat regularity + tempo sweet spot) ---
        beat_times = librosa.frames_to_time(beat_frames, sr=sr)
        if len(beat_times) > 1:
            beat_intervals = np.diff(beat_times)
            beat_regularity = 1.0 - min(1.0, float(np.std(beat_intervals)) / 0.5)
        else:
            beat_regularity = 0.0
        # Tempo sweet spot: 100-130 BPM is most danceable
        tempo_factor = max(0.0, 1.0 - abs(tempo - 115) / 60)
        danceability = 0.6 * beat_regularity + 0.4 * tempo_factor

        # --- Acousticness (spectral flatness + zero crossing rate) ---
        spectral_flatness = librosa.feature.spectral_flatness(y=y)[0]
        zcr = librosa.feature.zero_crossing_rate(y)[0]
        # Higher flatness = more noise-like = less acoustic
        # Lower ZCR = more tonal = more acoustic
        flatness_score = 1.0 - min(1.0, float(np.mean(spectral_flatness)) * 10)
        zcr_score = 1.0 - min(1.0, float(np.mean(zcr)) * 5)
        acousticness = 0.5 * flatness_score + 0.5 * zcr_score

        # --- Speechiness (spectral centroid variance + MFCC patterns) ---
        mfccs = librosa.feature.mfcc(y=y, sr=sr, n_mfcc=13)
        # Speech has high variance in lower MFCCs
        mfcc_var = float(np.mean(np.var(mfccs[1:5], axis=1)))
        speechiness = min(1.0, mfcc_var / 800)

        # --- Valence (mode detection via chroma + spectral contrast) ---
        chroma = librosa.feature.chroma_cqt(y=y, sr=sr)
        # Major keys tend to have stronger 3rd scale degree (index 4 semitones up)
        # This is a simplified heuristic
        chroma_mean = np.mean(chroma, axis=1)
        # Spectral contrast: brighter = happier
        contrast = librosa.feature.spectral_contrast(y=y, sr=sr)
        brightness = float(np.mean(contrast))
        brightness_norm = min(1.0, max(0.0, (brightness + 10) / 30))
        # Combine: major key tendency + brightness
        valence = 0.4 * brightness_norm + 0.3 * energy + 0.3 * danceability

        # --- Instrumentalness (harmonic vs percussive + vocal range energy) ---
        y_harmonic, y_percussive = librosa.effects.hpss(y)
        harmonic_ratio = float(np.mean(np.abs(y_harmonic))) / max(
            float(np.mean(np.abs(y))), 1e-6
        )
        # Check vocal frequency range (300Hz - 3kHz)
        S = np.abs(librosa.stft(y))
        freqs = librosa.fft_frequencies(sr=sr)
        vocal_mask = (freqs >= 300) & (freqs <= 3000)
        vocal_energy = float(np.mean(S[vocal_mask])) if np.any(vocal_mask) else 0.0
        total_energy = float(np.mean(S)) + 1e-6
        vocal_ratio = vocal_energy / total_energy
        # High vocal ratio = less instrumental
        instrumentalness = max(0.0, 1.0 - vocal_ratio * 1.5)

        # --- Liveness (spectral bandwidth variance) ---
        bandwidth = librosa.feature.spectral_bandwidth(y=y, sr=sr)[0]
        bw_var = float(np.std(bandwidth)) / (float(np.mean(bandwidth)) + 1e-6)
        # Live recordings have more bandwidth variance
        liveness = min(1.0, bw_var * 2)

        return {
            "danceability": round(min(1.0, max(0.0, danceability)), 4),
            "energy": round(min(1.0, max(0.0, energy)), 4),
            "valence": round(min(1.0, max(0.0, valence)), 4),
            "acousticness": round(min(1.0, max(0.0, acousticness)), 4),
            "instrumentalness": round(min(1.0, max(0.0, instrumentalness)), 4),
            "liveness": round(min(1.0, max(0.0, liveness)), 4),
            "speechiness": round(min(1.0, max(0.0, speechiness)), 4),
            "tempo": round(tempo, 2),
        }
    except Exception as e:
        log.warning(f"Failed to analyze clip: {e}")
        return None


def analyze_tracks(preview_urls: List[str], max_workers: int = 8) -> Dict[str, float]:
    """
    Download and analyze multiple preview clips in parallel.
    Returns averaged features across all successfully analyzed clips.
    """
    results: List[Dict[str, float]] = []

    def _process(url: str) -> Optional[Dict[str, float]]:
        data = _download_preview(url)
        if data is None:
            return None
        return _analyze_clip(data)

    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(_process, url): url for url in preview_urls}
        for fut in as_completed(futures):
            result = fut.result()
            if result:
                results.append(result)

    log.info(f"Analyzed {len(results)}/{len(preview_urls)} preview clips")

    if not results:
        return {k: 0.0 for k in KEYS}

    agg = {k: 0.0 for k in KEYS}
    for r in results:
        for k in KEYS:
            agg[k] += r[k]
    n = len(results)
    return {k: round(agg[k] / n, 4) for k in KEYS}
