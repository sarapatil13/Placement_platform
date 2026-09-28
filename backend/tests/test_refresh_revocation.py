"""Refresh token revocation, rotation, and cookie-based refresh.

The server maintains a denylist of revoked refresh tokens. Refreshing rotates
the token (the presented one is revoked), logout revokes it, and cookie-based
refresh is guarded by SameSite=Strict + an X-Requested-With marker header so a
cross-site request cannot rotate or revoke a session.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import jwt
from tests.conftest import TestData

from app.core.config import settings
from app.core.security import create_refresh_token

CSRF = {"X-Requested-With": "XMLHttpRequest"}


def _mint_refresh(seed: TestData):
    _token, user = seed.admin()
    refresh = create_refresh_token(role=user.role, institution_id=user.institution_id, sub=user.id)
    return refresh


def test_login_sets_httponly_samesite_cookie(seed: TestData, client) -> None:
    seed.admin()
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.edu", "password": TestData.ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    assert client.cookies.get("pp_refresh")
    set_cookie = resp.headers.get("set-cookie", "")
    assert "HttpOnly" in set_cookie
    assert "SameSite=strict" in set_cookie


def test_refresh_rotates_token_and_rejects_replay(seed: TestData, client) -> None:
    r0 = _mint_refresh(seed)
    first = client.post("/api/v1/auth/refresh", json={"refresh_token": r0})
    assert first.status_code == 200
    r1 = first.json()["refresh_token"]
    assert r1 != r0

    # replaying the rotated-out token must fail
    replay = client.post("/api/v1/auth/refresh", json={"refresh_token": r0})
    assert replay.status_code == 401
    assert replay.json()["code"] == "refresh_token_revoked"

    # the rotated-in token still works
    second = client.post("/api/v1/auth/refresh", json={"refresh_token": r1})
    assert second.status_code == 200


def test_logout_revokes_body_refresh_token(seed: TestData, client) -> None:
    r0 = _mint_refresh(seed)
    assert client.post("/api/v1/auth/logout", json={"refresh_token": r0}).status_code == 200
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": r0})
    assert resp.status_code == 401
    assert resp.json()["code"] == "refresh_token_revoked"


def test_expired_refresh_token_rejected(seed: TestData, client) -> None:
    _token, user = seed.admin()
    now = datetime.now(UTC)
    expired = jwt.encode(
        {
            "sub": user.id,
            "typ": "refresh",
            "role": user.role,
            "institution_id": user.institution_id,
            "iat": int((now - timedelta(days=2)).timestamp()),
            "exp": int((now - timedelta(days=1)).timestamp()),
            "jti": "expired-jti",
            "iss": settings.institution.identity_issuer,
        },
        settings.secret_key,
        algorithm=settings.jwt_algorithm,
    )
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": expired})
    assert resp.status_code == 401


def test_cookie_refresh_requires_csrf_header(seed: TestData, client) -> None:
    seed.admin()
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.edu", "password": TestData.ADMIN_PASSWORD},
    )
    assert client.cookies.get("pp_refresh")
    # cookie is present but the marker header is not: forged cross-site request
    resp = client.post("/api/v1/auth/refresh", json={})
    assert resp.status_code == 403


def test_cookie_refresh_with_header_rotates(seed: TestData, client) -> None:
    seed.admin()
    login = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.edu", "password": TestData.ADMIN_PASSWORD},
    )
    assert login.status_code == 200
    previous_cookie = client.cookies.get("pp_refresh")
    assert previous_cookie

    resp = client.post("/api/v1/auth/refresh", json={}, headers=CSRF)
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    # cookie was rotated to a fresh value
    assert client.cookies.get("pp_refresh") != previous_cookie


def test_logout_clears_cookie_and_revokes_cookie_token(seed: TestData, client) -> None:
    seed.admin()
    client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.edu", "password": TestData.ADMIN_PASSWORD},
    )
    token_in_cookie = client.cookies.get("pp_refresh")
    assert token_in_cookie

    assert client.post("/api/v1/auth/logout", json={}).status_code == 200
    assert client.cookies.get("pp_refresh") is None

    # the cookie's token value is now denylisted
    reuse = client.post("/api/v1/auth/refresh", json={"refresh_token": token_in_cookie})
    assert reuse.status_code == 401