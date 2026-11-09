from services.caption_engine import (
    MODES,
    PRESETS,
    ComposeRequest,
    apply_adjustments,
    compose,
    preset_catalog,
    taste_to_caption,
)

BASE = {
    "danceability": 0.72, "energy": 0.66, "valence": 0.41, "acousticness": 0.12,
    "instrumentalness": 0.03, "liveness": 0.14, "speechiness": 0.26, "tempo": 138,
}
GENRES = ["trap", "rap", "hip hop", "rage rap"]


def _req(**kw):
    base = dict(mode="taste", features=dict(BASE), genres=list(GENRES), use_llm=False, duration=60)
    base.update(kw)
    return ComposeRequest(**base)


def test_taste_mode_produces_concrete_caption():
    r = compose(_req())
    assert r.engine == "template"
    assert "trap" in r.prompt
    assert "808" in r.prompt  # instrument palette for hip-hop family
    assert r.bpm == 138
    assert r.lyrics == "[Instrumental]" or r.lyrics.startswith("[")
    assert r.key_scale and r.key_scale.endswith("minor")  # valence 0.41 -> minor
    assert r.title


def test_every_mode_composes():
    for mode in MODES:
        kwargs = {}
        if mode == "brief":
            kwargs["brief"] = "rainy 2am drive through Tokyo"
        if mode == "lyrics":
            kwargs["lyrics"] = "I keep driving past your street"
        if mode in ("fusion", "festival"):
            kwargs["fusion_artists"] = [{"name": "A", "genres": ["house"]}, {"name": "B", "genres": ["techno"]}]
        r = compose(_req(mode=mode, **kwargs))
        assert r.prompt and r.mode == mode


def test_overrides_beat_preset():
    feats = apply_adjustments(BASE, {"energy": 0.1}, "gym")
    assert feats["energy"] == 0.1  # explicit slider wins over +0.25 preset delta
    assert feats["tempo"] == 142  # preset tempo applied


def test_preset_tags_and_instrumental_flag():
    r = compose(_req(mode="mood", preset="focus"))
    assert "instrumental" in r.prompt
    assert r.lyrics == "[Instrumental]"
    assert r.preset == "focus"


def test_brief_text_lands_in_caption():
    r = compose(_req(mode="brief", brief="neon-lit rooftop at 3am"))
    assert "neon-lit rooftop at 3am" in r.prompt


def test_lyrics_get_section_tag_when_missing():
    r = compose(_req(mode="lyrics", lyrics="plain lines\nno tags here"))
    assert r.lyrics.startswith("[verse]")


def test_lyrics_theme_generates_structure():
    r = compose(_req(mode="lyrics", lyrics_theme="leaving home"))
    assert "[chorus]" in r.lyrics and "leaving home" in r.lyrics


def test_fusion_blends_artist_genres():
    r = compose(_req(mode="fusion", fusion_artists=[{"name": "A", "genres": ["house"]}, {"name": "B", "genres": ["deep house"]}]))
    assert "house" in r.prompt
    assert "four-on-the-floor" in r.prompt


def test_duration_is_clamped():
    assert compose(_req(duration=5)).duration == 15
    assert compose(_req(duration=99999)).duration <= 240


def test_acestep_params_shape():
    p = compose(_req()).to_acestep_params()
    assert set(p) >= {"prompt", "lyrics", "bpm", "audio_duration", "infer_steps", "batch_size"}
    assert p["batch_size"] == 1


def test_preset_catalog_matches_presets():
    ids = {p["id"] for p in preset_catalog()}
    assert ids == set(PRESETS)


def test_legacy_shim_still_returns_params():
    class T:
        genres = GENRES

        def as_features(self):
            return dict(BASE)

    p = taste_to_caption(T(), overrides={"energy": 0.9, "lyrics": "[verse]\nhi"})
    assert p["lyrics"].startswith("[verse]")
    assert "prompt" in p and p["bpm"] == 138
