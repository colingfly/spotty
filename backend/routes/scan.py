# backend/routes/scan.py
from __future__ import annotations

import time
from typing import Any, Dict, List

from flask import Blueprint, request
from rapidfuzz import fuzz
from sqlalchemy.orm import Session

from db import SessionLocal
from models import SpotifyAccount, ArtistEdge, PosterScan
from services.spotify_client import (
    refresh_if_needed, search_artist, user_top_artists,
)
from services.ocr import ocr_text_from_image, tokenize_candidate_lines, jaccard
from services.taste import update_user_taste_if_stale

scan_bp = Blueprint("scan", __name__)


def _log_cooccurrence(names: List[str], db: Session) -> None:
    norm = [n.strip() for n in names if n and n.strip()]
    seen: set = set()
    uniq = []
    for n in norm:
        low = n.lower()
        if low not in seen:
            seen.add(low)
            uniq.append(n)

    def keypair(a: str, b: str):
        return (a, b) if a.lower() <= b.lower() else (b, a)

    epoch = int(time.time())
    for i in range(len(uniq)):
        for j in range(i + 1, len(uniq)):
            a, b = keypair(uniq[i], uniq[j])
            edge = (
                db.query(ArtistEdge)
                .filter(ArtistEdge.a == a, ArtistEdge.b == b)
                .one_or_none()
            )
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
        a, b = (cand_name, t) if cand_name.lower() <= t.lower() else (t, cand_name)
        edge = (
            db.query(ArtistEdge)
            .filter(ArtistEdge.a == a, ArtistEdge.b == b)
            .one_or_none()
        )
        if edge:
            total += edge.weight
    return min(total / 20.0, 1.0)


@scan_bp.post("/api/scan")
def api_scan():
    f = request.files.get("file")
    sid = request.form.get("spotify_user_id")
    if not f or not sid:
        return {
            "error": "bad_request",
            "message": "file and spotify_user_id required",
        }, 400
    if f.mimetype.split("/")[0] != "image":
        return {"error": "unsupported_media_type"}, 415

    db = SessionLocal()
    try:
        acct = db.query(SpotifyAccount).filter_by(spotify_user_id=sid).one_or_none()
        if not acct:
            return {"error": "not_linked"}, 404

        try:
            acct = refresh_if_needed(acct, db)
        except Exception as e:
            return {"error": "refresh_failed", "detail": str(e)}, 401

        ut = update_user_taste_if_stale(acct, db, max_age_hours=24)

        try:
            text_blob = ocr_text_from_image(f.read())
        except ValueError as bad:
            return {"error": "bad_image", "message": str(bad)}, 400
        except RuntimeError as ocr:
            return {"error": "ocr_unavailable", "message": str(ocr)}, 503

        candidates = tokenize_candidate_lines(text_blob)

        top_artists_long = user_top_artists(acct, "long_term", limit=20)
        top_names = [a.get("name") for a in top_artists_long if a.get("name")]

        results: List[Dict[str, Any]] = []
        for cand in candidates:
            found = search_artist(cand, acct.access_token)
            if not found:
                continue

            found_name = found["name"]
            name_score = fuzz.token_set_ratio(cand.lower(), found_name.lower()) / 100.0
            artist_genres = [g.lower() for g in found.get("genres", [])]
            genre_score = jaccard(artist_genres, ut.genres or [])
            cooc = _cooccur_score(found_name, top_names, db)
            total = 0.55 * name_score + 0.30 * genre_score + 0.15 * cooc

            results.append(
                {
                    "candidate": cand,
                    "resolved_name": found_name,
                    "spotify_artist_id": found["id"],
                    "image": (found.get("images") or [{}])[0].get("url"),
                    "external_url": (found.get("external_urls") or {}).get("spotify"),
                    "genres": sorted(set(artist_genres))[:6],
                    "popularity": found.get("popularity"),
                    "scores": {
                        "name": round(name_score * 100, 1),
                        "genre": round(genre_score, 3),
                        "cooc": round(cooc, 3),
                        "total": round(total, 3),
                    },
                }
            )

        try:
            db.add(
                PosterScan(
                    spotify_user_id=sid,
                    scan_ts=int(time.time()),
                    artists_csv=",".join([r["resolved_name"] for r in results]),
                )
            )
            _log_cooccurrence([r["resolved_name"] for r in results], db)
        except Exception:
            db.rollback()

        results.sort(key=lambda x: x["scores"]["total"], reverse=True)
        pruned = [r for r in results if r["scores"]["total"] >= 0.35][:20]
        return {"count": len(pruned), "items": pruned, "debug": {"candidates": candidates[:40]}}
    finally:
        db.close()
