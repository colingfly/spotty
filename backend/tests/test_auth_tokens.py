from services.auth_tokens import (
    audio_url_for,
    issue_oauth_state,
    issue_session_token,
    sign_audio,
    verify_audio,
    verify_oauth_state,
    verify_session_token,
)


def test_session_roundtrip():
    tok = issue_session_token("user-1")
    assert verify_session_token(tok) == "user-1"


def test_session_tamper_rejected():
    tok = issue_session_token("user-1")
    assert verify_session_token(tok[:-3] + "xyz") is None
    assert verify_session_token("") is None
    assert verify_session_token("not.a.token") is None


def test_audio_token_bound_to_generation():
    t = sign_audio(42)
    assert verify_audio(t, 42)
    assert not verify_audio(t, 43)
    assert not verify_audio("garbage", 42)


def test_audio_url_shape():
    url = audio_url_for(7)
    assert url.startswith("/api/audio/7?t=")


def test_oauth_state_roundtrip():
    s = issue_oauth_state("/library")
    data = verify_oauth_state(s)
    assert data and data["next"] == "/library"
    assert verify_oauth_state(s + "x") is None
