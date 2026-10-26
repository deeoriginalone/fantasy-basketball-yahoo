import asyncio
from datetime import datetime, timedelta, timezone

import httpx
import pytest
from cryptography.fernet import Fernet
from fastapi import HTTPException

from app.core.config import Settings
from app.core.security import decrypt_token, encrypt_token
from app.features.yahoo.models import YahooCredential
from app.features.yahoo.oauth import YahooOAuth
from app.services.yahoo.auth import YahooAuthService


class FakeSession:
    def __init__(self, credential: YahooCredential | None = None):
        self.credential = credential
        self.commits = 0

    async def get(self, model, key):
        return self.credential

    def add(self, credential):
        self.credential = credential

    async def commit(self):
        self.commits += 1


def _settings(key: str) -> Settings:
    return Settings(
        yahoo_client_id="client-id",
        yahoo_client_secret="client-secret",
        yahoo_redirect_uri="http://localhost/api/v1/yahoo/oauth/callback",
        oauth_state_secret="state-secret",
        token_encryption_key=key,
    )


def test_authorization_stores_both_tokens_encrypted() -> None:
    key = Fernet.generate_key().decode("ascii")
    session = FakeSession()
    oauth = YahooOAuth(_settings(key))

    asyncio.run(
        oauth.save_tokens(
            session,
            {
                "access_token": "access-secret",
                "refresh_token": "refresh-secret",
                "expires_in": 3600,
            },
        )
    )

    assert session.credential is not None
    assert session.credential.access_token_encrypted != "access-secret"
    assert session.credential.refresh_token_encrypted != "refresh-secret"
    assert decrypt_token(session.credential.access_token_encrypted, key) == "access-secret"
    assert decrypt_token(session.credential.refresh_token_encrypted, key) == "refresh-secret"
    assert session.commits == 1


def test_expired_access_token_refreshes_and_keeps_encrypted_refresh_token(monkeypatch) -> None:
    key = Fernet.generate_key().decode("ascii")
    refresh_token = "stored-refresh-token"
    credential = YahooCredential(
        id=1,
        access_token_encrypted=encrypt_token("expired-access-token", key),
        refresh_token_encrypted=encrypt_token(refresh_token, key),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    session = FakeSession(credential)
    posted_data = {}

    class FakeResponse:
        is_error = False

        def json(self):
            return {"access_token": "rotated-access-token", "expires_in": 3600}

    class FakeAsyncClient:
        def __init__(self, timeout):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc, traceback):
            return None

        async def post(self, url, auth, data):
            posted_data.update(data)
            return FakeResponse()

    monkeypatch.setattr("app.features.yahoo.oauth.httpx.AsyncClient", FakeAsyncClient)
    oauth = YahooOAuth(_settings(key))

    access_token = asyncio.run(oauth.access_token(session))

    assert access_token == "rotated-access-token"
    assert posted_data["grant_type"] == "refresh_token"
    assert posted_data["refresh_token"] == refresh_token
    assert decrypt_token(credential.access_token_encrypted, key) == "rotated-access-token"
    assert decrypt_token(credential.refresh_token_encrypted, key) == refresh_token


def test_initial_authorization_requires_refresh_token() -> None:
    key = Fernet.generate_key().decode("ascii")
    session = FakeSession()
    oauth = YahooOAuth(_settings(key))

    with pytest.raises(HTTPException) as error:
        asyncio.run(
            oauth.save_tokens(
                session,
                {"access_token": "access-secret", "expires_in": 3600},
            )
        )

    assert error.value.status_code == 502


def test_unexpired_normal_auth_uses_the_same_stored_access_token_without_refresh(monkeypatch) -> None:
    key = Fernet.generate_key().decode("ascii")
    credential = YahooCredential(
        id=1,
        access_token_encrypted=encrypt_token("synthetic-access", key),
        refresh_token_encrypted=encrypt_token("synthetic-refresh", key),
        expires_at=datetime.now(timezone.utc) + timedelta(minutes=10),
    )
    session = FakeSession(credential)

    def forbidden_http(*args, **kwargs):
        pytest.fail("Unexpired acquisition must not refresh")

    monkeypatch.setattr("app.features.yahoo.oauth.httpx.AsyncClient", forbidden_http)
    result = asyncio.run(YahooAuthService(_settings(key)).access_token(session))

    assert result == decrypt_token(credential.access_token_encrypted, key)
    assert session.commits == 0


def test_rejected_refresh_attempts_once_and_preserves_encrypted_credentials(monkeypatch, caplog) -> None:
    key = Fernet.generate_key().decode("ascii")
    credential = YahooCredential(
        id=1,
        access_token_encrypted=encrypt_token("synthetic-access", key),
        refresh_token_encrypted=encrypt_token("synthetic-refresh", key),
        expires_at=datetime.now(timezone.utc) - timedelta(minutes=1),
    )
    before = (
        credential.access_token_encrypted,
        credential.refresh_token_encrypted,
        credential.expires_at,
    )
    session = FakeSession(credential)
    requests = []

    async def reject(request):
        requests.append((request.method, request.url.path))
        return httpx.Response(400, json={"error": "synthetic-private-provider-error"})

    original_client = httpx.AsyncClient

    def fixture_client(*args, **kwargs):
        return original_client(*args, transport=httpx.MockTransport(reject), **kwargs)

    monkeypatch.setattr("app.features.yahoo.oauth.httpx.AsyncClient", fixture_client)
    with pytest.raises(HTTPException) as error:
        asyncio.run(YahooAuthService(_settings(key)).access_token(session))

    assert error.value.status_code == 401
    assert error.value.detail == "Yahoo token refresh failed; reconnect the account"
    assert requests == [("POST", "/oauth2/get_token")]
    assert session.commits == 0
    assert (
        credential.access_token_encrypted,
        credential.refresh_token_encrypted,
        credential.expires_at,
    ) == before
    assert "synthetic-access" not in caplog.text
    assert "synthetic-refresh" not in caplog.text
    assert "synthetic-private-provider-error" not in caplog.text