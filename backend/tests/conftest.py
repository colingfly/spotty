# backend/tests/conftest.py
"""
Test bootstrap. Environment must be set BEFORE importing config/app because
Settings reads os.environ at import time.
"""
from __future__ import annotations

import os
import sys
import tempfile
import time
import uuid

_TMP = tempfile.mkdtemp(prefix="trill-test-")
os.environ["DATABASE_URL"] = f"sqlite:///{os.path.join(_TMP, 'test.db')}"
os.environ["AUDIO_OUTPUT_DIR"] = os.path.join(_TMP, "audio")
os.environ["WORKER_ENABLED"] = "0"
os.environ["FLASK_SECRET_KEY"] = "test-secret-key-0123456789abcdef0123456789abcdef"
os.environ["ANTHROPIC_API_KEY"] = ""
os.environ["ANTHROPIC_AUTH_TOKEN"] = ""
os.environ["LLM_ENABLED"] = "false"
os.environ["SPOTIFY_CLIENT_ID"] = "cid"
os.environ["SPOTIFY_CLIENT_SECRET"] = "csecret"
os.environ["FRONTEND_URL"] = "http://localhost:5180"

BACKEND_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if BACKEND_DIR not in sys.path:
    sys.path.insert(0, BACKEND_DIR)

import pytest  # noqa: E402

from app import create_app  # noqa: E402
from db import SessionLocal  # noqa: E402
from models import Generation, SpotifyAccount, UserTaste  # noqa: E402
from services.auth_tokens import issue_session_token  # noqa: E402


@pytest.fixture(scope="session")
def app():
    return create_app(testing=True)


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def db():
    s = SessionLocal()
    try:
        yield s
    finally:
        s.close()


def _seed_user(db, sid: str):
    acct = db.query(SpotifyAccount).filter_by(spotify_user_id=sid).one_or_none()
    if not acct:
        acct = SpotifyAccount(
            spotify_user_id=sid,
            display_name=sid.title(),
            access_token="tok",
            refresh_token="rtok",
            expires_at=int(time.time()) + 3600,
        )
        db.add(acct)
    ut = db.query(UserTaste).filter_by(spotify_user_id=sid).one_or_none()
    if not ut:
        ut = UserTaste(
            spotify_user_id=sid,
            danceability=0.72,
            energy=0.66,
            valence=0.41,
            acousticness=0.12,
            instrumentalness=0.03,
            liveness=0.14,
            speechiness=0.26,
            tempo=138,
            genres=["trap", "rap", "hip hop", "rage rap", "plugg"],
            genre_weights=[{"genre": "trap", "weight": 0.4}, {"genre": "rap", "weight": 0.3}, {"genre": "hip hop", "weight": 0.3}],
            top_artists=["Artist A", "Artist B"],
        )
        db.add(ut)
    db.commit()
    return acct, ut


@pytest.fixture()
def user(db):
    acct, ut = _seed_user(db, "alice")
    return {"sid": "alice", "token": issue_session_token("alice"), "acct": acct, "taste": ut}


@pytest.fixture()
def other_user(db):
    acct, ut = _seed_user(db, "mallory")
    return {"sid": "mallory", "token": issue_session_token("mallory"), "acct": acct, "taste": ut}


@pytest.fixture()
def auth(user):
    return {"Authorization": f"Bearer {user['token']}"}


class FakeACEStep:
    """Stands in for the GPU server: completes any task on the first poll."""

    def __init__(self):
        self.base_url = "http://fake-acestep"
        self.submitted = []
        self.healthy = True
        self.fail_next = False

    def health_check(self, max_age: float = 5.0):
        return self.healthy

    def submit_task(self, params):
        self.submitted.append(params)
        return f"task-{uuid.uuid4().hex[:10]}"

    def query_results(self, task_ids):
        out = {}
        for tid in task_ids:
            if self.fail_next:
                out[tid] = {"task_id": tid, "status": 2, "error": "boom"}
            else:
                out[tid] = {"task_id": tid, "status": 1, "result": f'[{{"file": "/v1/audio?path=/tmp/{tid}.mp3", "status": 1}}]'}
        return out

    def query_result(self, task_id):
        return self.query_results([task_id])[task_id]

    @staticmethod
    def extract_file_paths(result):
        from services.acestep_client import ACEStepClient

        return ACEStepClient.extract_file_paths(result)

    @staticmethod
    def extract_error(result):
        from services.acestep_client import ACEStepClient

        return ACEStepClient.extract_error(result)

    def download(self, file_ref):
        return b"ID3" + b"\x00" * 2048


@pytest.fixture()
def fake_acestep(monkeypatch):
    fake = FakeACEStep()
    import routes.auth as auth_routes
    import routes.generate as gen_routes
    import services.generation_service as gsvc

    monkeypatch.setattr(auth_routes, "acestep", fake)
    monkeypatch.setattr(gen_routes, "acestep", fake)
    monkeypatch.setattr(gsvc, "acestep", fake)
    monkeypatch.setattr(gsvc.media, "analyze", lambda path: (60.0, [0.1, 0.5, 1.0]))
    return fake


@pytest.fixture(autouse=True)
def _no_network(monkeypatch):
    """Never hit Spotify or Last.fm from tests."""
    import routes.generate as gen_routes
    import routes.spotify as sp_routes
    import services.spotify_client as sc
    import services.taste as taste

    monkeypatch.setattr(sc, "refresh_if_needed", lambda acct, db: acct)
    monkeypatch.setattr(gen_routes, "refresh_if_needed", lambda acct, db: acct)
    monkeypatch.setattr(sp_routes, "refresh_if_needed", lambda acct, db: acct)

    def _fresh(acct, db, max_age_hours=24):
        return db.query(UserTaste).filter_by(spotify_user_id=acct.spotify_user_id).one()

    monkeypatch.setattr(taste, "update_user_taste_if_stale", _fresh)
    monkeypatch.setattr(gen_routes, "update_user_taste_if_stale", _fresh)
    monkeypatch.setattr(sp_routes, "update_user_taste_if_stale", _fresh)
    monkeypatch.setattr(gen_routes, "get_artists", lambda acct, ids: [{"id": i, "name": f"Artist {i}", "genres": ["house", "techno"], "image": None} for i in ids])
    monkeypatch.setattr(gen_routes, "artist_genres_with_fallback", lambda a: list(a.get("genres") or ["indie rock"]))
    yield
