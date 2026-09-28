"""Auth endpoint tests: login, refresh, activation, token guards."""

from __future__ import annotations

from tests.conftest import TestData, auth_headers


def test_login_success(seed: TestData, client) -> None:
    seed.admin()
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.edu", "password": TestData.ADMIN_PASSWORD},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["role"] == "placement_admin"
    assert body["user"]["institution_code"] == "KLE"


def test_login_rejects_wrong_password(seed: TestData, client) -> None:
    seed.admin()
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.edu", "password": "Wrong@12345!"},
    )
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_failed"


def test_me_requires_auth(seed: TestData, client) -> None:
    resp = client.get("/api/v1/auth/me")
    assert resp.status_code == 401
    assert resp.json()["code"] == "authentication_failed"


def test_me_with_bearer(seed: TestData, client) -> None:
    token, _user = seed.admin()
    resp = client.get("/api/v1/auth/me", headers=auth_headers(token))
    assert resp.status_code == 200
    assert resp.json()["role"] == "placement_admin"


def test_refresh_mints_new_access(seed: TestData, client) -> None:
    from app.core.security import create_refresh_token

    _token, user = seed.admin()
    refresh = create_refresh_token(
        role=user.role, institution_id=user.institution_id, sub=user.id
    )
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": refresh})
    assert resp.status_code == 200
    body = resp.json()
    assert body["token_type"] == "bearer"
    assert body["access_token"]
    assert body["user"]["email"] == "admin@test.example.edu"


def test_access_token_cannot_be_used_as_refresh(seed: TestData, client) -> None:
    token, _user = seed.admin()
    resp = client.post("/api/v1/auth/refresh", json={"refresh_token": token})
    assert resp.status_code == 401


def test_activation_flow(seed: TestData, client) -> None:
    user, _student, raw_token = seed.pending_student()
    assert user.must_change_password is True

    new_password = "Str0ng!Passw0rd2026"
    resp = client.post(
        "/api/v1/auth/activate",
        json={"token": raw_token, "full_name": "Pending Student", "new_password": new_password},
    )
    assert resp.status_code == 200
    assert resp.json()["access_token"]
    assert resp.json()["user"]["must_change_password"] is False

    login = client.post(
        "/api/v1/auth/login",
        json={"email": user.email, "password": new_password},
    )
    assert login.status_code == 200


def test_activation_token_single_use(seed: TestData, client) -> None:
    _user, _student, raw_token = seed.pending_student()
    body = {"token": raw_token, "full_name": "Pending Student", "new_password": "Str0ng!Passw0rd2026"}
    assert client.post("/api/v1/auth/activate", json=body).status_code == 200
    assert client.post("/api/v1/auth/activate", json=body).status_code == 422


def test_forged_role_mismatch_rejected(seed: TestData, client) -> None:
    from app.core.security import create_access_token

    seed.admin()
    resp = client.post(
        "/api/v1/auth/login",
        json={"email": "admin@test.example.edu", "password": TestData.ADMIN_PASSWORD},
    )
    assert resp.status_code == 200

    bad = create_access_token(
        role="super_admin", institution_id="KLE", extra_claims={"sub": resp.json()["user"]["id"]}
    )
    resp = client.get("/api/v1/auth/me", headers=auth_headers(bad))
    assert resp.status_code == 401