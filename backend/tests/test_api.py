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


def test_serverless_engine_queues_until_awake(client, auth, fake_acestep, monkeypatch):
    import dataclasses

    import routes.generate as gen_routes
    import services.generation_service as gsvc

    serverless = dataclasses.replace(gsvc.settings, acestep_serverless=True)
    monkeypatch.setattr(gsvc, "settings", serverless)
    monkeypatch.setattr(gen_routes, "settings", serverless)

    fake_acestep.healthy = False  # container asleep
    r = client.post("/api/generate", headers=auth, json={"mode": "taste"})
    assert r.status_code == 202, r.get_json()
    gid = r.get_json()["items"][0]["generation_id"]
    assert fake_acestep.submitted == []

    st = client.get(f"/api/generate/status/{gid}", headers=auth).get_json()
    assert st["status"] == "pending"
    assert fake_acestep.submitted == []

    fake_acestep.healthy = True  # container answered /health
    client.get(f"/api/generate/status/{gid}", headers=auth)
    assert len(fake_acestep.submitted) == 1
    st = client.get(f"/api/generate/status/{gid}", headers=auth).get_json()
    assert st["status"] == "completed"
    assert len(fake_acestep.submitted) == 1


def test_model_selection_and_tiers(client, auth, fake_acestep, monkeypatch):
    import dataclasses

    import routes.generate as gen_routes

    cat = client.get("/api/generate/presets").get_json()
    assert [m["id"] for m in cat["models"]] == ["ace-turbo", "ace-xl-turbo"]
    assert cat["default_model"] == "ace-turbo"

    r = client.post("/api/generate", headers=auth, json={"mode": "taste"})
    assert r.get_json()["items"][0]["model"] == "ace-turbo"
    assert fake_acestep.submitted[-1]["model"] == "acestep-v15-turbo"

    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "model": "ace-xl-turbo"})
    assert r.status_code == 202, r.get_json()
    assert r.get_json()["items"][0]["model"] == "ace-xl-turbo"
    assert fake_acestep.submitted[-1]["model"] == "acestep-v15-xl-turbo"

    assert client.post("/api/generate", headers=auth, json={"mode": "taste", "model": "nope"}).status_code == 400

    _enforce_plans(monkeypatch)
    assert client.post("/api/generate", headers=auth, json={"mode": "taste", "model": "ace-xl-turbo"}).status_code == 402
    assert client.post("/api/generate", headers=auth, json={"mode": "taste"}).status_code == 202


def test_retake_reuses_brief_and_controls_seed(client, auth, fake_acestep):
    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "seed": 4242, "edits": {"title": "Loop"}})
    first = r.get_json()["items"][0]
    assert first["params"]["seed"] == 4242
    gid = first["generation_id"]

    again = client.post(f"/api/generate/{gid}/retake", headers=auth, json={}).get_json()["items"][0]
    assert again["caption"] == first["caption"]
    assert again["params"]["seed"] != 4242
    assert again["meta"]["retake_of"] == gid

    same = client.post(f"/api/generate/{gid}/retake", headers=auth,
                       json={"same_seed": True, "model": "ace-xl-turbo", "edits": {"bpm": 90}}).get_json()["items"][0]
    assert same["params"]["seed"] == 4242
    assert same["params"]["bpm"] == 90
    assert same["model"] == "ace-xl-turbo"

    assert client.post("/api/generate/999999/retake", headers=auth, json={}).status_code == 404


def test_fusion_weights_shape_the_blend(client, auth, fake_acestep, monkeypatch):
    import routes.generate as gen_routes

    known = {"metallica": ["heavy metal", "metal", "hard rock"], "norah jones": ["jazz", "blues", "singer-songwriter"]}
    monkeypatch.setattr(gen_routes, "artist_genres_with_fallback", lambda a: known[a["name"].lower()])
    body = {"mode": "fusion", "artist_names": ["Metallica", "Norah Jones"]}
    heavy = client.post("/api/generate/preview", headers=auth,
                        json={**body, "artist_weights": {"metallica": 1, "norah jones": 0.1}, "listener_weight": 0}).get_json()
    soft = client.post("/api/generate/preview", headers=auth,
                       json={**body, "artist_weights": {"metallica": 0.1, "norah jones": 1}, "listener_weight": 0}).get_json()
    assert heavy["composed"]["features"]["energy"] > soft["composed"]["features"]["energy"]
    assert [a["name"] for a in heavy["fusion_artists"]] == ["Metallica", "Norah Jones"]

    # Weight 0 removes an artist; fusion still needs two
    r = client.post("/api/generate/preview", headers=auth, json={**body, "artist_weights": {"metallica": 0}})
    assert r.status_code == 400


def test_audio_is_restored_from_durable_storage(client, auth, fake_acestep, monkeypatch):
    import services.generation_service as gsvc

    blobs = {}
    monkeypatch.setattr(gsvc.storage, "upload", lambda name, data, content_type="audio/mpeg": blobs.setdefault(f"blob://{name}", data) and f"blob://{name}")

    def restore(url, path):
        if url not in blobs:
            return False
        with open(path, "wb") as fp:
            fp.write(blobs[url])
        return True

    monkeypatch.setattr(gsvc.storage, "restore", restore)

    r = client.post("/api/generate", headers=auth, json={"mode": "taste"})
    gid = r.get_json()["items"][0]["generation_id"]
    st = client.get(f"/api/generate/status/{gid}", headers=auth).get_json()
    assert st["status"] == "completed"
    assert list(blobs) == [f"blob://audio/{gid}.mp3"]

    # A redeploy wipes the disk: the file is gone but the track still plays.
    os.remove(os.path.join(gsvc.settings.audio_output_dir, f"{gid}.mp3"))
    resp = client.get(st["audio_url"])
    assert resp.status_code == 200
    assert resp.data == blobs[f"blob://audio/{gid}.mp3"]


def test_repaint_sends_the_original_audio_and_range(client, auth, fake_acestep):
    from db import SessionLocal
    from models import Generation

    r = client.post("/api/generate", headers=auth, json={"mode": "taste"})
    gid = r.get_json()["items"][0]["generation_id"]
    client.get(f"/api/generate/status/{gid}", headers=auth)
    # The fake audio has no real duration; give the row one.
    session = SessionLocal()
    session.get(Generation, gid).duration_seconds = 60.0
    session.commit()
    session.close()

    assert client.post(f"/api/generate/{gid}/repaint", headers=auth, json={"start": 10, "end": 11}).status_code == 400

    r = client.post(f"/api/generate/{gid}/repaint", headers=auth, json={"start": 10, "end": 25, "lyrics": "[Chorus] new words"})
    assert r.status_code == 202, r.get_json()
    item = r.get_json()["items"][0]
    sent, files = fake_acestep.submitted[-1], fake_acestep.files[-1]
    assert sent["task_type"] == "repaint" and sent["repainting_start"] == 10 and sent["repainting_end"] == 25
    assert sent["lyrics"] == "[Chorus] new words"
    assert "src_generation_id" not in sent
    assert files["src_audio"][1].startswith(b"ID3")
    assert item["meta"]["edit"] == {"type": "repaint", "of": gid, "start": 10, "end": 25}
    assert item["model"] == "ace-xl-turbo"  # turbo cannot repaint, so the edit moves to a model that can


def test_reference_upload_drives_a_cover(client, auth, fake_acestep):
    import io

    bad = client.post("/api/uploads", headers=auth, data={"file": (io.BytesIO(b"x" * 4096), "notes.txt")}, content_type="multipart/form-data")
    assert bad.status_code == 400
    up = client.post("/api/uploads", headers=auth, data={"file": (io.BytesIO(b"RIFF" + bytes(4096)), "my demo.wav")}, content_type="multipart/form-data")
    assert up.status_code == 200, up.get_json()
    ref = up.get_json()["ref"]

    # The free model cannot follow a reference
    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "reference": {"ref": ref, "strength": 0.4}})
    assert r.status_code == 400
    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "model": "ace-xl-turbo", "reference": {"ref": ref, "strength": 0.4}})
    assert r.status_code == 202, r.get_json()
    sent, files = fake_acestep.submitted[-1], fake_acestep.files[-1]
    assert sent["task_type"] == "cover" and sent["audio_cover_strength"] == 0.4
    assert files["src_audio"][1].startswith(b"RIFF")
    assert r.get_json()["items"][0]["meta"]["reference"]["strength"] == 0.4

    forged = client.post("/api/generate", headers=auth, json={"mode": "taste", "model": "ace-xl-turbo", "reference": {"ref": "not-a-real-ref"}})
    assert forged.status_code == 400


def test_stems_flow(client, auth, fake_acestep, monkeypatch):
    import dataclasses
    import io
    import zipfile

    import routes.generate as gen_routes
    import services.stems as stems_svc

    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "edits": {"title": "Night Ride", "bpm": 120, "key_scale": "F# minor"}})
    gid = r.get_json()["items"][0]["generation_id"]
    done = client.get(f"/api/generate/status/{gid}", headers=auth).get_json()
    assert done["stems"] is None

    assert client.post(f"/api/generate/{gid}/stems", headers=auth).status_code == 503  # not configured

    configured = dataclasses.replace(stems_svc.settings, stems_api_url="http://fake-stems")
    monkeypatch.setattr(stems_svc, "settings", configured)
    monkeypatch.setattr(gen_routes, "settings", configured)

    def fake_separate(gen_id, src, base):
        out = stems_svc._dir(gen_id)
        os.makedirs(out, exist_ok=True)
        files = {}
        for stem in stems_svc.STEMS:
            path = os.path.join(out, f"{stem}.wav")
            with open(path, "wb") as fp:
                fp.write(b"RIFF" + stem.encode())
            files[stem] = {"path": path, "url": None}
        return files

    monkeypatch.setattr(stems_svc, "_separate", fake_separate)
    # Run the job inline instead of on a thread so the test is deterministic.
    monkeypatch.setattr(stems_svc.threading, "Thread", lambda target, args, **kw: type("T", (), {"start": lambda self: target(*args)})())

    r = client.post(f"/api/generate/{gid}/stems", headers=auth)
    assert r.status_code == 202, r.get_json()
    st = client.get(f"/api/generate/status/{gid}", headers=auth).get_json()
    assert st["stems"]["status"] == "ready"
    assert set(st["stems"]["files"]) == {"vocals", "drums", "bass", "other"}
    assert "stems" not in st["meta"]  # storage locations stay server-side

    one = client.get(st["stems"]["files"]["drums"])
    assert one.status_code == 200 and one.data == b"RIFFdrums"
    assert "Night Ride_120bpm_Fsharpmin_drums.wav" in one.headers["Content-Disposition"]
    assert client.get(f"/api/stems/{gid}/drums?t=nope").status_code == 401

    z = zipfile.ZipFile(io.BytesIO(client.get(st["stems"]["zip"]).data))
    names = sorted(z.namelist())
    assert names == sorted([f"Night Ride_120bpm_Fsharpmin_{n}" for n in ("vocals.wav", "drums.wav", "bass.wav", "other.wav", "mix.mp3", "session.txt")])
    sheet = z.read("Night Ride_120bpm_Fsharpmin_session.txt").decode()
    assert "tempo: 120 bpm" in sheet and "key: F# minor" in sheet


def _enforce_plans(monkeypatch):
    import dataclasses

    import services.plans as plans_svc

    monkeypatch.setattr(plans_svc, "settings", dataclasses.replace(plans_svc.settings, pro_unlocked=False))


def _set_plan(plan):
    from db import SessionLocal
    from models import SpotifyAccount

    session = SessionLocal()
    session.query(SpotifyAccount).update({"plan": plan})
    session.commit()
    session.close()


def test_three_plans_gate_features(client, auth, fake_acestep, monkeypatch):
    assert client.get("/api/me", headers=auth).get_json()["plan"]["plan"] == "producer"  # unlocked by default

    _enforce_plans(monkeypatch)
    me = client.get("/api/me", headers=auth).get_json()["plan"]
    assert me["plan"] == "free" and me["enforced"] is True
    assert me["features"] == {f: False for f in me["features"]}

    # Free: fast model only, one take, one minute
    assert client.post("/api/generate", headers=auth, json={"mode": "taste", "model": "ace-xl-turbo"}).status_code == 402
    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "variations": 3, "duration": 200})
    assert r.status_code == 202 and len(r.get_json()["items"]) == 1
    assert fake_acestep.submitted[-1]["audio_duration"] == 60
    gid = r.get_json()["items"][0]["generation_id"]
    client.get(f"/api/generate/status/{gid}", headers=auth)
    assert client.post(f"/api/generate/{gid}/stems", headers=auth).status_code in (402, 503)
    assert client.post("/api/projects", headers=auth, json={"generation_id": gid}).status_code == 402

    # Studio: XL, takes and length, but not the producer tools
    _set_plan("studio")
    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "model": "ace-xl-turbo", "variations": 2, "duration": 200})
    assert r.status_code == 202 and len(r.get_json()["items"]) == 2
    assert fake_acestep.submitted[-1]["audio_duration"] == 200
    resp = client.post("/api/projects", headers=auth, json={"generation_id": gid})
    assert resp.status_code == 402 and resp.get_json()["needs"] == "producer"

    _set_plan("producer")
    assert client.post("/api/projects", headers=auth, json={"generation_id": gid}).status_code == 201


def test_project_keeps_a_version_history(client, auth, fake_acestep):
    r = client.post("/api/generate", headers=auth, json={"mode": "taste", "edits": {"title": "Night Ride"}})
    root = r.get_json()["items"][0]["generation_id"]
    client.get(f"/api/generate/status/{root}", headers=auth)

    p = client.post("/api/projects", headers=auth, json={"generation_id": root})
    assert p.status_code == 201, p.get_json()
    pid = p.get_json()["project_id"]
    assert p.get_json()["name"] == "Night Ride"
    # Opening the same track again returns the same project
    assert client.post("/api/projects", headers=auth, json={"generation_id": root}).get_json()["project_id"] == pid

    take = client.post(f"/api/generate/{root}/retake", headers=auth, json={}).get_json()["items"][0]
    assert take["project_id"] == pid and take["parent_id"] == root
    xl = client.post(f"/api/generate/{take['generation_id']}/retake", headers=auth, json={"same_seed": True, "model": "ace-xl-turbo"}).get_json()["items"][0]
    assert xl["parent_id"] == take["generation_id"]
    fresh = client.post("/api/generate", headers=auth, json={"mode": "taste", "project_id": pid}).get_json()["items"][0]
    assert fresh["project_id"] == pid and fresh["parent_id"] is None

    detail = client.get(f"/api/projects/{pid}", headers=auth).get_json()
    assert [v["generation_id"] for v in detail["items"]] == [root, take["generation_id"], xl["generation_id"], fresh["generation_id"]]
    listed = client.get("/api/projects", headers=auth).get_json()["items"]
    assert listed[0]["project_id"] == pid and listed[0]["versions"] == 4  # most recently worked on comes first

    assert client.patch(f"/api/projects/{pid}", headers=auth, json={"name": "Night Ride v2"}).get_json()["name"] == "Night Ride v2"
    assert client.delete(f"/api/projects/{pid}", headers=auth).status_code == 200
    # Tracks survive the project
    assert client.get(f"/api/generate/status/{root}", headers=auth).get_json()["project_id"] is None
    assert client.get(f"/api/projects/{pid}", headers=auth).status_code == 404


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
