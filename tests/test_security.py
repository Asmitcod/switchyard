from fastapi import HTTPException

from app.security import authenticate_and_rate_limit


def test_authentication_is_open_for_local_development(monkeypatch):
    monkeypatch.delenv("ROUTEWISE_API_KEYS", raising=False)
    assert authenticate_and_rate_limit(None) == "local"


def test_invalid_api_key_is_rejected(monkeypatch):
    monkeypatch.setenv("ROUTEWISE_API_KEYS", "valid-key")
    try:
        authenticate_and_rate_limit("Bearer invalid-key")
    except HTTPException as error:
        assert error.status_code == 401
    else:
        raise AssertionError("Invalid API key was accepted")
