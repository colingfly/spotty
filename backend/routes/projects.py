# backend/routes/projects.py
"""
Producer projects: one song worked on over many versions.

A project groups Generation rows. Each version remembers the version it was made
from (parent_id), so takes, section edits and model swaps form a history tree.
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from flask import Blueprint, g, request

from db import SessionLocal
from models import Generation, Project, SpotifyAccount
from services import plans
from services.auth_tokens import require_user
from services.generation_service import serialize, sync_generation

log = logging.getLogger("spotty.projects")
projects_bp = Blueprint("projects", __name__)


def _guard(db) -> Optional[tuple]:
    acct = db.query(SpotifyAccount).filter_by(spotify_user_id=g.sid).one_or_none()
    return plans.denied(plans.plan_of(acct), "projects")


def _own(db, project_id: int) -> Optional[Project]:
    return db.query(Project).filter_by(id=project_id, spotify_user_id=g.sid).one_or_none()


def _summary(db, p: Project) -> Dict[str, Any]:
    versions = db.query(Generation).filter_by(project_id=p.id, spotify_user_id=g.sid)
    latest = versions.order_by(Generation.created_at.desc()).first()
    return {
        "project_id": p.id,
        "name": p.name,
        "versions": versions.count(),
        "latest": serialize(latest) if latest else None,
        "created_at": p.created_at.isoformat() if p.created_at else None,
        "updated_at": p.updated_at.isoformat() if p.updated_at else None,
    }


@projects_bp.get("/api/projects")
@require_user
def list_projects():
    db = SessionLocal()
    try:
        denied = _guard(db)
        if denied:
            return denied
        rows = db.query(Project).filter_by(spotify_user_id=g.sid).order_by(Project.updated_at.desc()).all()
        return {"items": [_summary(db, p) for p in rows], "count": len(rows)}
    finally:
        db.close()


@projects_bp.post("/api/projects")
@require_user
def create_project():
    """Start a project from one of your tracks. The track becomes version 1."""
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        denied = _guard(db)
        if denied:
            return denied
        try:
            gid = int(data.get("generation_id"))
        except (TypeError, ValueError):
            return {"error": "bad_request", "message": "pick a track to start the project from"}, 400
        gen = db.query(Generation).filter_by(id=gid, spotify_user_id=g.sid).one_or_none()
        if not gen:
            return {"error": "not_found"}, 404
        if gen.project_id:
            existing = _own(db, gen.project_id)
            if existing:
                return _summary(db, existing), 200
        name = (str(data.get("name") or "").strip() or gen.title or "untitled project")[:80]
        p = Project(spotify_user_id=g.sid, name=name)
        db.add(p)
        db.flush()
        gen.project_id = p.id
        db.commit()
        db.refresh(p)
        return _summary(db, p), 201
    finally:
        db.close()


@projects_bp.get("/api/projects/<int:project_id>")
@require_user
def get_project(project_id: int):
    db = SessionLocal()
    try:
        denied = _guard(db)
        if denied:
            return denied
        p = _own(db, project_id)
        if not p:
            return {"error": "not_found"}, 404
        rows = db.query(Generation).filter_by(project_id=p.id, spotify_user_id=g.sid).order_by(Generation.created_at.asc()).all()
        rows = [sync_generation(db, r) for r in rows]
        return {**_summary(db, p), "items": [serialize(r) for r in rows]}
    finally:
        db.close()


@projects_bp.patch("/api/projects/<int:project_id>")
@require_user
def rename_project(project_id: int):
    data = request.get_json(silent=True) or {}
    db = SessionLocal()
    try:
        p = _own(db, project_id)
        if not p:
            return {"error": "not_found"}, 404
        name = str(data.get("name") or "").strip()[:80]
        if not name:
            return {"error": "bad_request", "message": "a project needs a name"}, 400
        p.name = name
        db.commit()
        db.refresh(p)
        return _summary(db, p)
    finally:
        db.close()


@projects_bp.delete("/api/projects/<int:project_id>")
@require_user
def delete_project(project_id: int):
    """Removes the project only. Its tracks stay in the library."""
    db = SessionLocal()
    try:
        p = _own(db, project_id)
        if not p:
            return {"error": "not_found"}, 404
        db.query(Generation).filter_by(project_id=p.id, spotify_user_id=g.sid).update({"project_id": None})
        db.delete(p)
        db.commit()
        return {"ok": True, "deleted": project_id}
    finally:
        db.close()
