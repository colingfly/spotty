# backend/routes/scan.py
from __future__ import annotations

import logging
import time
from typing import Any, Dict, List

from flask import Blueprint, g, request
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from db import SessionLocal
from extensions import limiter
from models import ArtistEdge, PosterScan, SpotifyAccount
from services.auth_tokens import require_user
from services.ocr import jaccard, ocr_text_from_image, tokenize_candidate_lines
from services.spotify_client import artist_genres_with_fallback, refresh_if_needed, search_artist, user_top_artists
from services.taste import update_user_taste_if_stale

log = logging.getLogger("spotty.scan")

scan_bp = Blueprint("scan", __name__)


def _log_cooccurrence(names: List[str], db: Session) -> None:
    seen: set = set()
    uniq: List[str] = []
    for n in names:
        n = (n or "").strip()
        if n and n.lower() not in seen:
            seen.add(n.lower())
            uniq.append(n)

    epoch = int(time.time())
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = sorted((uniq[i], uniq[j]), key=str.lower)
            edge = db.query(ArtistEdge).filter(ArtistEdge.a == a, ArtistEdge.b == b).one_or_none()
            if not edge:
                edge = ArtistEdge(a=a, b=b, weight=1.0, last_seen=epoch)
            else:
                edge.weight = min(edge.weight + 1.0, 20.0)
                edge.last_seen = epoch
            db.add(edge)
    db.commit()


def _cooccur_score(cand_name: str, user_top_names: List[str], db: Session) -> float:
    if not user_top_names:
        return 0.0
    total = 0.0
    for t in user_top_names:
        a, b = sorted((cand_name, t), key=str.lower)
        edge = db.query(ArtistEdge).filter(ArtistEdge.a == a, ArtistEdge.b == b).one_or_none()
        if edge:
            total += edge.weight
    return min(total / 20.0, 1.0)


@scan_bp.post("/api/scan")
@require_user
@limiter.limit("10 per minute")
def api_scan():
    f = request.files.get("file")
    if not f:
        return {"error": "bad_request", "message": "file is required"}, 400
    if (f.mimetype or "").split("/")[0] != "image":
        return {"error": "unsupported_media_type"}, 415

    db = SessionLocal()
    try:
        acct = db.query(SpotifyAccount).filter_by(spotify_user_id=g.sid).one_or_none()
        if not acct:
            return {"error": "not_linked"}, 404
        try:
            acct = refresh_if_needed(acct, db)
        except Exception as e:
            return {"error": "reauth_required", "message": str(e)}, 401

        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)

        try:
            text_blob = ocr_text_from_image(f.read())
        except ValueError as bad:
            return {"error": "bad_image", "message": str(bad)}, 400
        except RuntimeError as ocr:
            return {"error": "ocr_unavailable", "message": str(ocr)}, 503

        candidates = tokenize_candidate_lines(text_blob)[:60]
        top_names = [a["name"] for a in user_top_artists(acct, "long_term", limit=30) if a.get("name")]
        top_lower = {n.lower() for n in top_names}
        user_genres = set(ut.genres or [])

        results: List[Dict[str, Any]] = []
        seen_ids: set = set()
        for cand in candidates:
            found = search_artist(cand, acct)
            if not found or found.get("id") in seen_ids:
                continue
            found_name = found["name"]
            name_score = fuzz.token_set_ratio(cand.lower(), found_name.lower()) / 100.0
            if name_score < 0.6:
                continue
            seen_ids.add(found["id"])
            genres = artist_genres_with_fallback(found)
            genre_score = jaccard(genres, user_genres)
            cooc = _cooccur_score(found_name, top_names, db)
            in_library = found_name.lower() in top_lower
            total = 0.5 * name_score + 0.3 * genre_score + 0.1 * cooc + (0.1 if in_library else 0.0)
            images = found.get("images") or []
            results.append(
                {
                    "candidate": cand,
                    "resolved_name": found_name,
                    "spotify_artist_id": found["id"],
                    "image": images[0].get("url") if images else None,
                    "external_url": (found.get("external_urls") or {}).get("spotify"),
                    "genres": sorted(set(genres))[:6],
                    "popularity": found.get("popularity"),
                    "in_library": in_library,
                    "scores": {
                        "name": round(name_score * 100, 1),
                        "genre": round(genre_score, 3),
                        "cooc": round(cooc, 3),
                        "total": round(total, 3),
                    },
                }
            )

        try:
            db.add(PosterScan(spotify_user_id=g.sid, scan_ts=int(time.time()), artists_csv=",".join(r["resolved_name"] for r in results)))
            _log_cooccurrence([r["resolved_name"] for r in results], db)
        except Exception:
            db.rollback()

        results.sort(key=lambda x: x["scores"]["total"], reverse=True)
        pruned = [r for r in results if r["scores"]["total"] >= 0.35][:20]
        return {"count": len(pruned), "items": pruned, "debug": {"candidates": candidates[:40]}}
    finally:
        db.close()
