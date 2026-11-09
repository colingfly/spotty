from services.genre_analyzer import KEYS, infer_audio_features


def test_known_genre_exact():
    f = infer_audio_features(["trap"])
    assert set(f) == set(KEYS)
    assert f["tempo"] == 140
    assert 0.6 < f["danceability"] < 0.75


def test_partial_match_with_modifier():
    dark = infer_audio_features(["dark trap"])
    plain = infer_audio_features(["trap"])
    assert dark["valence"] < plain["valence"]


def test_unknown_genre_uses_baseline():
    f = infer_audio_features(["zorblax core"])
    assert f["tempo"] == 120
    assert 0 <= f["energy"] <= 1


def test_weights_shift_result():
    heavy_metal = infer_audio_features(["metal", "ambient"], [0.95, 0.05])
    heavy_ambient = infer_audio_features(["metal", "ambient"], [0.05, 0.95])
    assert heavy_metal["energy"] > heavy_ambient["energy"]


def test_empty_input():
    assert all(v == 0.0 for v in infer_audio_features([]).values())
