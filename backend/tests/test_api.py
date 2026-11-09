import os


def test_health(client):
    assert client.get("/api/health/live").get_json() == {"ok": True}
    body = client.get("/api/health/ready").get_json()
    assert body["db"] is True and "llm" in body


def test_requires_auth(client):
    for path in ("/api/me", "/api/me/taste", "/api/generate/history", "/api/me/stats"):
        assert client.get(path).status_code == 401, path
    assert client.post("/api/generate", json={"mode": "taste"}).status_code == 401


def test_me_and_taste(client, auth, fake_acestep):
    me = client.get("/api/me", headers=auth).get_json()
    assert me["spotify_user_id"] == "alice"
    assert me["capabilities"]["acestep"] is True
    taste = client.get("/api/me/taste", headers=auth).get_json()
    assert taste["genres"][0] == "trap"
    assert taste["tempo"] == 138


def test_preview_does_not_submit(client, auth, fake_acestep):
    r = client.post("/api/generate/preview", headers=auth, json={"mode": "mood", "preset": "gym", "overrides": {"valence": 0.9}})
    assert r.status_code == 200, r.get_json()
    composed = r.get_json()["composed"]
    assert composed["engine"] == "template"
    assert composed["features"]["valence"] == 0.9
    assert composed["acestep_params"]["bpm"] == 142
    assert fake_acestep.submitted == []


def test_generate_batch_completes_and_serves_audio(client, auth, fake_acestep, db):
    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "variations": 2, "edits": {"title": "Night Ride"}})
    assert r.status_code == 202, r.get_json()
    body = r.get_json()
    assert len(body["items"]) == 2
    assert len(fake_acestep.submitted) == 2
    assert fake_acestep.submitted[0]["seed"] != fake_acestep.submitted[1]["seed"]
    assert body["items"][0]["title"].startswith("Night Ride")

    batch = client.get(f"/api/generate/batch/{body['batch_id']}", headers=auth).get_json()
    assert batch["done"] is True
    first = batch["items"][0]
    assert first["status"] == "completed"
    assert first["duration_seconds"] == 60.0
    assert first["waveform"] == [0.1, 0.5, 1.0]
    assert first["audio_url"].startswith("/api/audio/")

    audio = client.get(first["audio_url"])
    assert audio.status_code == 200
    assert audio.mimetype == "audio/mpeg"
    audio.close()

    dl = client.get(first["download_url"])
    assert "attachment" in dl.headers.get("Content-Disposition", "")
    dl.close()

    # Wrong token for a real id is rejected
    assert client.get(f"/api/audio/{first['generation_id']}?t=nope").status_code == 401


def test_generate_failure_is_recorded(client, auth, fake_acestep):
    fake_acestep.fail_next = True
    r = client.post("/api/generate", headers=auth, json={"mode": "taste"})
    gid = r.get_json()["items"][0]["generation_id"]
    st = client.get(f"/api/generate/status/{gid}", headers=auth).get_json()
    assert st["status"] == "failed"
    assert "boom" in st["error"]


def test_generate_rejects_when_acestep_down(client, auth, fake_acestep):
    fake_acestep.healthy = False
    r = client.post("/api/generate", headers=auth, json={"mode": "taste"})
    assert r.status_code == 503


def test_validation_errors(client, auth, fake_acestep):
    assert client.post("/api/generate", headers=auth, json={"mode": "nope"}).status_code == 400
    assert client.post("/api/generate", headers=auth, json={"mode": "brief"}).status_code == 400
    assert client.post("/api/generate", headers=auth, json={"mode": "lyrics"}).status_code == 400
    assert client.post("/api/generate", headers=auth, json={"mode": "fusion", "artist_ids": ["a"]}).status_code == 400
    assert client.post("/api/generate", headers=auth, json={"mode": "taste", "preset": "bogus"}).status_code == 400


def test_fusion_mode_uses_artists(client, auth, fake_acestep):
    r = client.post("/api/generate/preview", headers=auth, json={"mode": "fusion", "artist_ids": ["a1", "a2"]})
    assert r.status_code == 200
    body = r.get_json()
    assert len(body["fusion_artists"]) == 2
    assert "house" in body["composed"]["prompt"]


def test_festival_mode_from_names(client, auth, fake_acestep):
    r = client.post("/api/generate/preview", headers=auth, json={"mode": "festival", "artist_names": ["Someone", "Else"]})
    assert r.status_code == 200
    assert "festival" in r.get_json()["composed"]["prompt"]


def test_ownership_enforced(client, auth, other_user, fake_acestep):
    gid = client.post("/api/generate", headers=auth, json={"mode": "taste"}).get_json()["items"][0]["generation_id"]
    other = {"Authorization": f"Bearer {other_user['token']}"}
    assert client.get(f"/api/generate/status/{gid}", headers=other).status_code == 404
    assert client.post(f"/api/generate/{gid}/favorite", headers=other).status_code == 404
    assert client.delete(f"/api/generate/{gid}", headers=other).status_code == 404
    assert client.get("/api/generate/history", headers=other).get_json()["total"] == 0


def test_library_filters_and_mutations(client, auth, fake_acestep, db):
    client.post("/api/generate", headers=auth, json={"mode": "mood", "preset": "party", "edits": {"title": "Confetti"}})
    client.post("/api/generate", headers=auth, json={"mode": "lyrics", "lyrics": "[verse]\nhello"})
    hist = client.get("/api/generate/history", headers=auth).get_json()
    assert hist["total"] >= 2

    mood_only = client.get("/api/generate/history?mode=mood", headers=auth).get_json()
    assert all(i["feature_type"] == "mood_slider" for i in mood_only["items"])

    found = client.get("/api/generate/history?q=confetti", headers=auth).get_json()
    assert found["total"] >= 1
    gid = found["items"][0]["generation_id"]

    fav = client.post(f"/api/generate/{gid}/favorite", headers=auth).get_json()
    assert fav["is_favorite"] is True
    assert client.get("/api/generate/history?favorites=1", headers=auth).get_json()["total"] >= 1

    renamed = client.patch(f"/api/generate/{gid}", headers=auth, json={"title": "Confetti Cannon"}).get_json()
    assert renamed["title"] == "Confetti Cannon"

    played = client.post(f"/api/generate/{gid}/played", headers=auth).get_json()
    assert played["play_count"] == 1

    stats = client.get("/api/me/stats", headers=auth).get_json()
    assert stats["favorites"] >= 1 and stats["plays"] >= 1

    st = client.get(f"/api/generate/status/{gid}", headers=auth).get_json()
    path = None
    from models import Generation

    row = db.query(Generation).get(gid)
    path = row.audio_path
    assert path and os.path.isfile(path)
    assert client.delete(f"/api/generate/{gid}", headers=auth).get_json()["ok"] is True
    assert not os.path.exists(path)
    assert client.get(f"/api/generate/status/{gid}", headers=auth).status_code == 404


def test_legacy_endpoints_still_work(client, auth, fake_acestep):
    r = client.post("/api/generate/taste-to-track", headers=auth, json={})
    assert r.status_code == 202
    r = client.post("/api/generate/custom", headers=auth, json={"overrides": {"energy": 0.9}})
    assert r.status_code == 202
    assert r.get_json()["items"][0]["feature_type"] == "mood_slider"


def test_lyric_writer_requires_llm(client, auth):
    r = client.post("/api/compose/lyrics", headers=auth, json={"theme": "rain"})
    assert r.status_code == 503


def test_insights_without_llm(client, auth):
    body = client.get("/api/me/insights", headers=auth).get_json()
    assert body["available"] is False and body["narrative"] is None
